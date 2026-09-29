import frappe
from frappe.utils import now_datetime

_ALLOWED_SIGN_DOCTYPES = {"Document Library", "DMS Training Record"}

# Minimum permission needed to apply an electronic signature, per doctype.
# Document Library approval signatures require write (a read-only user must not
# be able to fabricate one); training self-acknowledgement is identity-gated by
# the training controller, so read is sufficient there.
_SIGN_REQUIRED_PTYPE = {
    "Document Library": "write",
    "DMS Training Record": "read",
}


def _require_document_read(document):
    """Guard shared by the whitelisted document endpoints: the document must
    exist AND the caller must be allowed to read it. Prevents non-permitted
    users from using these endpoints as an existence oracle or to pollute the
    audit / signature trail for documents they cannot see."""
    if not frappe.db.exists("Document Library", document):
        frappe.throw("Document not found")
    if not frappe.has_permission("Document Library", doc=document, ptype="read"):
        raise frappe.PermissionError(f"Not permitted to access {document}")


@frappe.whitelist()
def log_file_download(document):
    """Log a file download event for the audit trail."""
    if not frappe.db.exists("Document Library", document):
        return
    if not frappe.has_permission("Document Library", doc=document, ptype="read"):
        return
    version = frappe.db.get_value("Document Library", document, "version")
    try:
        frappe.get_doc({
            "doctype": "DMS Audit Log",
            "document": document,
            "action": f"File Downloaded (v{version})" if version else "File Downloaded",
            "user": frappe.session.user,
            "timestamp": now_datetime(),
            "ip_address": getattr(frappe.local, "request_ip", ""),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "DMS: Failed to log file download")


@frappe.whitelist()
def log_file_preview(document):
    """Log a file preview event for the audit trail."""
    if not frappe.db.exists("Document Library", document):
        return
    if not frappe.has_permission("Document Library", doc=document, ptype="read"):
        return
    version = frappe.db.get_value("Document Library", document, "version")
    try:
        frappe.get_doc({
            "doctype": "DMS Audit Log",
            "document": document,
            "action": f"File Previewed (v{version})" if version else "File Previewed",
            "user": frappe.session.user,
            "timestamp": now_datetime(),
            "ip_address": getattr(frappe.local, "request_ip", ""),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "DMS: Failed to log file preview")

@frappe.whitelist()
def acknowledge_document(document, e_signature=None):
    # Must exist and be readable by the caller (i.e. actually assigned to them).
    _require_document_read(document)

    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw("User is not linked to any Employee record. Cannot acknowledge.")

    doc_version = frappe.db.get_value("Document Library", document, "version")

    training_record = frappe.db.get_value(
        "DMS Training Record", {"document": document, "version": doc_version}, "name"
    )
    # No self-service creation of training records and no self-append of rows:
    # an employee can only acknowledge a training that was actually assigned to
    # them. Otherwise anyone could fabricate a completed compliance record.
    if not training_record:
        frappe.throw(
            "No training has been assigned to you for this document. "
            "Please contact your DMS administrator."
        )

    training_record_doc = frappe.get_doc("DMS Training Record", training_record)
    row = next((r for r in training_record_doc.employees
                if r.employee == employee and r.status != "Suggested"), None)
    if not row:
        frappe.throw("This document's training has not been assigned to you.")

    if row.acknowledged:
        frappe.msgprint("You have already acknowledged this document.")
        return True

    row.acknowledged = 1
    row.acknowledged_on = now_datetime()
    row.status = "Completed"
    row.completion_date = now_datetime().date()
    if e_signature:
        row.e_signature = e_signature
    training_record_doc.save(ignore_permissions=True)
    return True


def _insert_audit_log(action, document=None, request=None, document_snapshot=None):
    """Single insertion point for all DMS Audit Log entries.

    document_snapshot captures the document's own descriptive fields (title,
    department, category, version, document_number, file) as plain text at
    the time of the event -- not Links, so this row stays fully readable even
    after the document itself is deleted (the one event this audit trail
    exists to record, and the one moment the source document can no longer
    answer for itself)."""
    try:
        doc_fields = {
            f"document_{k}": v for k, v in (document_snapshot or {}).items()
        }
        frappe.get_doc({
            "doctype": "DMS Audit Log",
            "document": document,
            "request": request,
            "action": action,
            "user": frappe.session.user,
            "timestamp": now_datetime(),
            "ip_address": getattr(frappe.local, "request_ip", ""),
            **doc_fields,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "DMS: Failed to write audit log")


def log_audit_event(doc, method):
    if doc.is_new():
        return

    if method == "on_trash":
        action = "Deleted"
    elif method == "on_cancel":
        action = "Cancelled"
    elif method == "on_submit":
        action = f"Submitted / Published (v{doc.version})" if doc.version else "Submitted / Published"
    elif doc.has_value_changed("status"):
        action = f"Status changed to {doc.status}"
    else:
        action = "Updated"

    # Captured from the live doc on every event (cheap, always available) so
    # the snapshot is already in place well before a later deletion, rather
    # than something that only gets populated specially for on_trash.
    snapshot = {
        "title": doc.title,
        "department": doc.department,
        "category": doc.category,
        "version": doc.version,
        "number": doc.document_number,
        "file": doc.file,
    }

    _insert_audit_log(action=action, document=doc.name, document_snapshot=snapshot)


def log_request_audit_event(doc, method):
    if doc.is_new():
        return

    if method == "on_trash":
        action = "Deleted"
    elif doc.has_value_changed("status"):
        action = f"Status changed to {doc.status}"
    else:
        action = "Updated"

    _insert_audit_log(action=action, request=doc.name)


_INACTIVE_EMPLOYEE_STATUSES = frozenset({"Left", "Inactive", "Suspended"})

# Only System Manager (IT / central oversight) sees every department's
# documents unconditionally. DMS Admin/Approver/Reviewer/Employee are all
# department-scoped below — a document's own "Applies to All Departments"
# checkbox is the only other way past that restriction.
_DMS_UNRESTRICTED_ROLES = {"System Manager"}


def _user_department_scope(user):
    """Resolve the department names a user's own department-scoped access
    should include: their own Employee.department plus any sub-departments
    under it (mirrors the department+subdepartment scoping already used for
    bulk training assignment). Returns None if the user has no linked
    Employee/department, meaning they get no department-based access at all
    (only documents explicitly marked "Applies to All Departments", or —
    for the Employee role — documents they own or are directly assigned)."""
    department = frappe.db.get_value(
        "Employee", {"user_id": user}, "department", order_by="creation asc"
    )
    if not department:
        return None
    from frappe.utils.nestedset import get_descendants_of
    return [department] + get_descendants_of("Department", department, ignore_permissions=True)


def handle_employee_status_change(doc, method):
    """Excuse an Employee's open training assignments once they leave the
    company, so departed staff stop counting against compliance reports and
    stop receiving overdue reminders."""
    if doc.is_new() or not doc.has_value_changed("status"):
        return
    if doc.status not in _INACTIVE_EMPLOYEE_STATUSES:
        return

    from quality_dms.dms.doctype.dms_training_record.dms_training_record import (
        excuse_departed_employee,
    )
    excuse_departed_employee(doc.name)


def notify_upcoming_reviews():
    # Lower bound (today) prevents repeat emails for already-overdue documents.
    today = frappe.utils.today()
    docs = frappe.get_all("Document Library", filters={
        "status": "Published",
        "review_date": ("between", [today, frappe.utils.add_days(today, 30)]),
    }, fields=["name", "title", "review_date", "owner"])

    if not docs:
        return

    owners = list({d.owner for d in docs})
    email_map = {
        row.name: row.email
        for row in frappe.get_all("User", filters={"name": ("in", owners)}, fields=["name", "email"])
        if row.email
    }

    for d in docs:
        email = email_map.get(d.owner)
        if not email:
            continue
        frappe.sendmail(
            recipients=[email],
            subject=f"Upcoming Review for Document: {d.title}",
            message=f"The document {d.title} is due for review on {d.review_date}. Please initiate a revision request if needed.",
            delayed=True
        )


_DMS_ROLES = {"DMS Admin", "DMS Approver", "DMS Reviewer", "Employee"}


def get_permission_query_conditions(user):
    if not user: user = frappe.session.user
    if user == "Administrator": return ""

    roles = frappe.get_roles(user)
    if set(roles) & _DMS_UNRESTRICTED_ROLES:
        return ""

    if not set(roles) & _DMS_ROLES:
        # Authenticated user holds no DMS role — deny list access entirely.
        # Returning "" (no filter) would grant full read access; "1=0" returns an empty list.
        return "1=0"

    conditions = []

    # Every DMS role (Admin/Approver/Reviewer/Employee) is scoped to their own
    # department (+ sub-departments) unless the document applies to all
    # departments — reviewers/approvers can no longer see other departments'
    # documents just by holding the role.
    departments = _user_department_scope(user)
    if departments:
        escaped_depts = ", ".join(frappe.db.escape(d) for d in departments)
        conditions.append(
            f"(`tabDocument Library`.applies_to_all_departments = 1 "
            f"OR `tabDocument Library`.department IN ({escaped_depts}))"
        )
    else:
        conditions.append("`tabDocument Library`.applies_to_all_departments = 1")

    if "Employee" in roles:
        escaped_user = frappe.db.escape(user)
        # On top of department scoping, an employee also always sees documents
        # assigned to them through a DMS Training Record, documents they
        # created themselves, or documents created from a Document Request
        # they raised or that was raised for them — even outside their own
        # department (e.g. cross-department training).
        assigned_via_training = (
            "EXISTS ("
            "SELECT 1 FROM `tabDMS Training Record` tr "
            "INNER JOIN `tabDocument Acknowledgement` da "
            "ON da.parent = tr.name AND da.parenttype = 'DMS Training Record' "
            "INNER JOIN `tabEmployee` emp ON emp.name = da.employee "
            f"WHERE tr.document = `tabDocument Library`.name AND emp.user_id = {escaped_user}"
            ")"
        )
        via_request = (
            "EXISTS ("
            "SELECT 1 FROM `tabDocument Request` dr "
            "WHERE dr.linked_document = `tabDocument Library`.name "
            f"AND (dr.requested_for = {escaped_user} OR dr.requested_by = {escaped_user})"
            ")"
        )
        conditions.append(
            f"(`tabDocument Library`.owner = {escaped_user} "
            f"OR {assigned_via_training} "
            f"OR {via_request})"
        )

    return "(" + " OR ".join(conditions) + ")"


def has_permission(doc, user=None, ptype="read"):
    if not user: user = frappe.session.user
    if user == "Administrator": return True

    roles = frappe.get_roles(user)
    if set(roles) & _DMS_UNRESTRICTED_ROLES:
        return True

    # A controller has_permission hook can only DENY; it must return a truthy
    # value to defer to the doctype's role permissions. Returning None is treated
    # as denial by Frappe's has_controller_permissions, so return True to defer.
    if not doc:
        return True

    # Row-level restrictions below apply to reads only. Create/write/delete are
    # governed by DocPerm — defer to it rather than denying here.
    if ptype != "read":
        return True

    if not set(roles) & _DMS_ROLES:
        return False

    if doc.applies_to_all_departments:
        return True

    departments = _user_department_scope(user)
    if departments and doc.department in departments:
        return True

    if "Employee" in roles:
        if doc.owner == user:
            return True
        if _is_assigned_via_training(doc.name, user):
            return True
        if _is_linked_via_request(doc.name, user):
            return True

    return False


def _is_linked_via_request(document, user):
    """True if this document was created from a Document Request the user
    raised, or that was raised on their behalf (requested_for)."""
    return bool(
        frappe.db.exists(
            "Document Request",
            {
                "linked_document": document,
                "requested_for": user,
            },
        )
        or frappe.db.exists(
            "Document Request",
            {
                "linked_document": document,
                "requested_by": user,
            },
        )
    )


def _is_assigned_via_training(document, user):
    """True if the user is assigned to this document through a DMS Training Record."""
    return bool(
        frappe.db.sql(
            """
            SELECT 1 FROM `tabDMS Training Record` tr
            INNER JOIN `tabDocument Acknowledgement` da
                ON da.parent = tr.name AND da.parenttype = 'DMS Training Record'
            INNER JOIN `tabEmployee` emp ON emp.name = da.employee
            WHERE tr.document = %s AND emp.user_id = %s
            LIMIT 1
            """,
            (document, user),
        )
    )


# Only System Manager sees the whole File list unconditionally. DMS Admin/
# Approver/Reviewer are department-scoped like everywhere else in this app —
# see _user_department_scope. Personal training certificates stay private to
# the employee they belong to regardless of role.
_FILE_UNRESTRICTED_ROLES = {"System Manager"}
_FILE_REVIEW_ROLES = {"DMS Admin", "DMS Approver", "DMS Reviewer"}
_CERT_SUFFIX = "-certificate.pdf"


def file_permission_query_conditions(user):
    """Restrict the File list: employees see only their own uploads and files on
    their assigned documents/training; admins/approvers/reviewers see every
    file on a document/training record in their own department (+ sub-
    departments) or marked Applies to All Departments, except other
    employees' personal certificates."""
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))
    if roles & _FILE_UNRESTRICTED_ROLES:
        return ""

    escaped_user = frappe.db.escape(user)

    if roles & _FILE_REVIEW_ROLES:
        is_cert = "RIGHT(`tabFile`.file_name, 16) = '-certificate.pdf'"
        emp_id = frappe.db.get_value("Employee", {"user_id": user}, "name")
        if emp_id:
            own_cert_frag = frappe.db.escape(f"-{emp_id}-certificate.pdf")
            cert_scope = f"(NOT {is_cert} OR INSTR(`tabFile`.file_name, {own_cert_frag}) > 0)"
        else:
            cert_scope = f"(NOT {is_cert})"

        departments = _user_department_scope(user)
        dept_condition = (
            "`dl`.applies_to_all_departments = 1"
            + (f" OR `dl`.department IN ({', '.join(frappe.db.escape(d) for d in departments)})" if departments else "")
        )
        in_scope_doc_files = (
            "(`tabFile`.attached_to_doctype = 'Document Library' AND EXISTS ("
            "SELECT 1 FROM `tabDocument Library` dl "
            f"WHERE dl.name = `tabFile`.attached_to_name AND ({dept_condition})"
            "))"
        )
        in_scope_training_files = (
            "(`tabFile`.attached_to_doctype = 'DMS Training Record' AND EXISTS ("
            "SELECT 1 FROM `tabDMS Training Record` tr "
            "INNER JOIN `tabDocument Library` dl ON dl.name = tr.document "
            f"WHERE tr.name = `tabFile`.attached_to_name AND ({dept_condition})"
            "))"
        )
        return f"(({in_scope_doc_files} OR {in_scope_training_files}) AND {cert_scope})"

    assigned_doc_files = (
        "(`tabFile`.attached_to_doctype = 'Document Library' AND EXISTS ("
        "SELECT 1 FROM `tabDMS Training Record` tr "
        "INNER JOIN `tabDocument Acknowledgement` da "
        "ON da.parent = tr.name AND da.parenttype = 'DMS Training Record' "
        "INNER JOIN `tabEmployee` emp ON emp.name = da.employee "
        f"WHERE tr.document = `tabFile`.attached_to_name AND emp.user_id = {escaped_user}"
        "))"
    )
    # Files on the employee's own training records — but personal certificates
    # (…-<employee>-certificate.pdf) are only visible to the employee they name.
    emp_id = frappe.db.get_value("Employee", {"user_id": user}, "name")
    # (avoid LIKE/% here: permission conditions go through %-string formatting)
    is_cert = "RIGHT(`tabFile`.file_name, 16) = '-certificate.pdf'"
    if emp_id:
        own_cert_frag = frappe.db.escape(f"-{emp_id}-certificate.pdf")
        cert_scope = f"(NOT {is_cert} OR INSTR(`tabFile`.file_name, {own_cert_frag}) > 0)"
    else:
        cert_scope = f"NOT {is_cert}"
    my_training_files = (
        "(`tabFile`.attached_to_doctype = 'DMS Training Record' AND EXISTS ("
        "SELECT 1 FROM `tabDocument Acknowledgement` da "
        "INNER JOIN `tabEmployee` emp ON emp.name = da.employee "
        "WHERE da.parent = `tabFile`.attached_to_name "
        "AND da.parenttype = 'DMS Training Record' "
        f"AND emp.user_id = {escaped_user}"
        f") AND {cert_scope})"
    )
    return (
        f"(`tabFile`.owner = {escaped_user} "
        f"OR {assigned_doc_files} "
        f"OR {my_training_files})"
    )


def file_has_permission(doc, user=None, ptype="read"):
    """Deny employees direct access to files outside their own uploads and
    their assigned documents / training records. Defers (returns True) for
    privileged roles and for non-read permission types."""
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return True

    roles = set(frappe.get_roles(user))
    if roles & _FILE_UNRESTRICTED_ROLES:
        return True

    if not doc or ptype != "read":
        return True

    if doc.owner == user:
        return True

    is_certificate = (doc.file_name or "").endswith(_CERT_SUFFIX)

    if is_certificate:
        # personal training certificate: only the employee it names may read it
        emp_id = frappe.db.get_value("Employee", {"user_id": user}, "name")
        return bool(emp_id) and f"-{emp_id}{_CERT_SUFFIX}" in doc.file_name

    if doc.attached_to_doctype and doc.attached_to_name:
        # visible if the employee can read the document the file belongs to
        return bool(
            frappe.has_permission(doc.attached_to_doctype, doc=doc.attached_to_name, ptype="read", user=user)
        )

    return False


@frappe.whitelist()
def get_current_user_info():
    user = frappe.session.user
    full_name = frappe.db.get_value("User", user, "full_name") or user
    employee = frappe.db.get_value(
        "Employee", {"user_id": user}, ["designation", "employee_name"], as_dict=True
    )
    return {
        "full_name": full_name,
        "designation": employee.designation if employee else ""
    }


@frappe.whitelist()
def verify_and_log_signature(doctype, docname, password, meaning, position=None):
    import hashlib
    import json
    from frappe.utils.password import check_password

    # Validate the target and the caller's authorization BEFORE the password
    # path, so an unauthorized / non-existent-document request can't use this
    # endpoint as a password or existence oracle.
    if doctype not in _ALLOWED_SIGN_DOCTYPES:
        frappe.throw(f"Electronic signatures are not supported for {doctype}.")

    if not frappe.db.exists(doctype, docname):
        frappe.throw(f"Document {docname} of type {doctype} not found.")

    # A read-only user must not be able to fabricate an approval signature on a
    # controlled document. Signing a Document Library requires write (reviewers/
    # approvers/admins) — plain read is not enough. Training self-acknowledgement
    # signs the DMS Training Record and is separately gated by the training
    # controller (it verifies the caller owns the row), so read suffices there.
    required_ptype = _SIGN_REQUIRED_PTYPE.get(doctype, "write")
    if not frappe.has_permission(doctype, required_ptype, docname):
        frappe.throw("Not permitted", frappe.PermissionError)

    # Re-authenticate the signer last.
    try:
        check_password(frappe.session.user, password)
    except Exception:
        frappe.throw("Invalid password. Electronic signature verification failed.")

    doc = frappe.get_doc(doctype, docname)

    # docstatus is intentionally INCLUDED in the checksum so the signature binds
    # the document's lifecycle state (Draft vs Submitted vs Cancelled) — a
    # signature captured in Draft must not validate against the same doc later
    # Submitted with otherwise-identical field values.
    exclude_fields = {"modified", "modified_by", "creation", "owner", "_user_tags", "_comments", "_liked_by", "idx"}
    doc_dict = {k: v for k, v in doc.as_dict().items() if k not in exclude_fields}
    doc_json = json.dumps(doc_dict, sort_keys=True, default=str)
    checksum = hashlib.sha256(doc_json.encode('utf-8')).hexdigest()

    user_fullname = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    signer_email = frappe.db.get_value("User", frappe.session.user, "email") or ""

    log_doc = frappe.get_doc({
        "doctype": "CFR Part 11 Signature Log",
        "reference_doctype": doctype,
        "reference_name": docname,
        "signer": frappe.session.user,
        "signer_name": user_fullname,
        "signer_email": signer_email,
        "position": position or "",
        "timestamp": now_datetime(),
        "meaning": meaning,
        "ip_address": getattr(frappe.local, "request_ip", ""),
        "document_checksum": checksum
    })
    log_doc.insert(ignore_permissions=True)
    # No explicit commit — Frappe commits after the request completes. An explicit
    # commit here would permanently flush any other dirty state in the same transaction
    # even if a later step fails, leaving the DB in a partial state.

    return {"status": "success", "message": "Electronic signature verified and logged successfully."}


# ---- My Training Dashboard ----
# Self-service dashboard (score gauge, pending trainings, completion %,
# leaderboard) shown to the logged-in employee. Admin roles get an
# `employee` param to preview any employee's own gauge/todo/completion --
# the leaderboard is always company-wide (ranking is the point of a
# leaderboard; it doesn't leak individual course-level scores).
_SCORE_BAND_THRESHOLDS = (60, 80)  # < 60 Poor, 60-79 Fair, >= 80 Good


def _score_band(score):
    if score is None:
        return None
    if score >= _SCORE_BAND_THRESHOLDS[1]:
        return "Good"
    if score >= _SCORE_BAND_THRESHOLDS[0]:
        return "Fair"
    return "Poor"


def _is_admin_user(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(
        set(frappe.get_roles(user)) & {"System Manager", "DMS Admin", "DMS Approver", "DMS Reviewer"}
    )


def _resolve_dashboard_employee(employee=None):
    """Which employee's own data to show: admins may pass `employee` to look
    up anyone; everyone else is locked to their own linked Employee record."""
    user = frappe.session.user
    if _is_admin_user(user) and employee:
        return employee
    return frappe.db.get_value("Employee", {"user_id": user}, "name")


@frappe.whitelist()
def get_my_training_dashboard(employee=None):
    target_employee = _resolve_dashboard_employee(employee)

    all_trainings = []
    completed_scores = []
    total_assigned = 0
    total_completed = 0

    if target_employee:
        rows = frappe.db.sql(
            """
            SELECT
                da.name AS name,
                da.status AS status,
                da.assessment_score AS assessment_score,
                da.due_date AS due_date,
                da.completion_date AS completion_date,
                trn.document AS document,
                trn.name AS training_record
            FROM `tabDocument Acknowledgement` da
            INNER JOIN `tabDMS Training Record` trn ON trn.name = da.parent AND da.parenttype = 'DMS Training Record'
            WHERE da.employee = %(employee)s
                AND da.status NOT IN ('Suggested', 'Excused')
            ORDER BY da.due_date ASC
            """,
            {"employee": target_employee},
            as_dict=True,
        )

        total_assigned = len(rows)
        for row in rows:
            if row.status == "Completed":
                total_completed += 1
                if row.assessment_score is not None:
                    completed_scores.append(row.assessment_score)
            all_trainings.append({
                "document": row.document,
                "status": row.status,
                "due_date": frappe.utils.format_date(row.due_date) if row.due_date else None,
                "completion_date": frappe.utils.format_date(row.completion_date) if row.completion_date else None,
                "assessment_score": row.assessment_score,
                "training_record": row.training_record,
            })

    overall_score = round(sum(completed_scores) / len(completed_scores), 1) if completed_scores else None
    completion_pct = round(total_completed / total_assigned * 100, 1) if total_assigned else 0.0

    # Leaderboard: every employee's own average completed-training score,
    # ranked highest to lowest. Company-wide by design (see docstring above).
    leaderboard_rows = frappe.db.sql(
        """
        SELECT
            da.employee AS employee,
            emp.employee_name AS employee_name,
            da.assessment_score AS assessment_score
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE da.status = 'Completed' AND da.assessment_score IS NOT NULL
        """,
        as_dict=True,
    )
    by_employee = {}
    for row in leaderboard_rows:
        bucket = by_employee.setdefault(row.employee, {"employee_name": row.employee_name, "scores": []})
        bucket["scores"].append(row.assessment_score)

    leaderboard = [
        {
            "employee": emp,
            "employee_name": data["employee_name"],
            "score": round(sum(data["scores"]) / len(data["scores"]), 1),
        }
        for emp, data in by_employee.items()
    ]
    leaderboard.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(leaderboard, start=1):
        row["rank"] = i

    return {
        "employee": target_employee,
        "overall_score": overall_score,
        "score_band": _score_band(overall_score),
        "completion_pct": completion_pct,
        "total_assigned": total_assigned,
        "total_completed": total_completed,
        "all_trainings": all_trainings,
        "leaderboard": leaderboard[:20],
    }


# ---- Employee Training Transcript ----
# A single consolidated PDF of every training an employee has ever completed
# (across all DMS Training Records), for audit/inspection requests -- the
# certificate PDF is per-training; this is the "whole history" document.
# Built as ad-hoc HTML -> PDF (not a bound Print Format) because the source
# rows span many different DMS Training Record parents, which a Print Format
# tied to one doctype record can't aggregate across.


@frappe.whitelist()
def generate_training_transcript(employee=None):
    """Render and save (as a private file owned by the employee) a PDF
    listing every Completed training for that employee. Self-service: a
    non-admin caller may only ever generate their own. Idempotent per call --
    always regenerates, so it reflects training completed since the last run."""
    # _resolve_dashboard_employee already enforces the self-service boundary:
    # a non-admin's `employee` argument is ignored outright, always resolving
    # to their own linked Employee record (same guarantee get_my_training_dashboard
    # relies on) -- no separate check is reachable or needed here.
    target_employee = _resolve_dashboard_employee(employee)
    if not target_employee:
        frappe.throw("No Employee record is linked to your user account.")

    employee_doc = frappe.db.get_value(
        "Employee", target_employee, ["employee_name", "department", "designation"], as_dict=True
    )
    if not employee_doc:
        frappe.throw("Employee record not found.")

    rows = frappe.db.sql(
        """
        SELECT
            trn.name AS training_record,
            trn.document AS document,
            doc.title AS document_title,
            trn.version AS version,
            da.status AS status,
            da.assessment_score AS assessment_score,
            da.quiz_passed AS quiz_passed,
            da.completion_date AS completion_date,
            da.acknowledged_on AS acknowledged_on
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabDMS Training Record` trn ON trn.name = da.parent AND da.parenttype = 'DMS Training Record'
        LEFT JOIN `tabDocument Library` doc ON doc.name = trn.document
        WHERE da.employee = %(employee)s AND da.status = 'Completed'
        ORDER BY da.completion_date ASC, trn.name ASC
        """,
        {"employee": target_employee},
        as_dict=True,
    )

    html = _render_transcript_html(employee_doc, target_employee, rows)

    from frappe.utils.pdf import get_pdf
    pdf_content = get_pdf(html)

    file_name = f"{target_employee}-training-transcript.pdf"
    # Idempotent: replace any previous transcript file for this employee
    # rather than accumulating one per generation.
    existing = frappe.db.get_value(
        "File", {"attached_to_doctype": "Employee", "attached_to_name": target_employee,
                 "file_name": file_name},
        "name",
    )
    if existing:
        frappe.delete_doc("File", existing, force=True, ignore_permissions=True)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": pdf_content,
        "is_private": 1,
        "attached_to_doctype": "Employee",
        "attached_to_name": target_employee,
    })
    file_doc.save(ignore_permissions=True)

    employee_user = frappe.db.get_value("Employee", target_employee, "user_id")
    if employee_user:
        frappe.db.set_value("File", file_doc.name, "owner", employee_user, update_modified=False)

    frappe.db.commit()
    return {"file_url": file_doc.file_url, "training_count": len(rows)}


def _render_transcript_html(employee_doc, employee_id, rows):
    generated_on = frappe.utils.now_datetime().strftime("%d-%b-%Y %H:%M")
    row_html = "".join(
        f"""
        <tr>
            <td>{frappe.utils.escape_html(r.document_title or r.document or "")}</td>
            <td>{frappe.utils.escape_html(r.version or "")}</td>
            <td>{frappe.utils.escape_html(str(r.assessment_score) if r.assessment_score is not None else "-")}</td>
            <td>{"Yes" if r.quiz_passed else "-"}</td>
            <td>{frappe.utils.format_date(r.completion_date) if r.completion_date else "-"}</td>
        </tr>
        """
        for r in rows
    )
    if not rows:
        row_html = '<tr><td colspan="5" style="text-align:center;color:#888;">No completed trainings on record.</td></tr>'

    return f"""
    <html>
    <head>
    <style>
        body {{ font-family: Arial, sans-serif; font-size: 12px; color: #17212b; }}
        h1 {{ font-size: 18px; margin-bottom: 2px; }}
        .meta {{ color: #52514e; font-size: 11px; margin-bottom: 18px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; font-size: 11px; }}
        th {{ background: #f4f6f9; }}
    </style>
    </head>
    <body>
        <h1>Employee Training Transcript</h1>
        <div class="meta">
            Employee: {frappe.utils.escape_html(employee_doc.employee_name or employee_id)} ({frappe.utils.escape_html(employee_id)})<br>
            Department: {frappe.utils.escape_html(employee_doc.department or "-")} &nbsp;|&nbsp;
            Designation: {frappe.utils.escape_html(employee_doc.designation or "-")}<br>
            Generated: {generated_on}
        </div>
        <table>
            <thead>
                <tr>
                    <th>Document / Course</th>
                    <th>Version</th>
                    <th>Score</th>
                    <th>Passed</th>
                    <th>Completion Date</th>
                </tr>
            </thead>
            <tbody>
                {row_html}
            </tbody>
        </table>
    </body>
    </html>
    """


# ---- Score trend ----
# Backed by DMS Training Score History -- one immutable row per grading event
# (pass or fail), written by DMSTrainingRecord._do_sign_acknowledgement /
# submit_quiz_and_sign. Powers the trend chart on My Training Dashboard.


@frappe.whitelist()
def get_my_score_trend(employee=None, limit=20):
    """Chronological list of {date, score, passed} for the employee's last
    `limit` graded attempts (pass or fail) -- self-service, same boundary as
    the rest of My Training Dashboard."""
    target_employee = _resolve_dashboard_employee(employee)
    if not target_employee:
        return {"employee": None, "trend": []}

    rows = frappe.db.sql(
        """
        SELECT recorded_on, score, quiz_passed
        FROM `tabDMS Training Score History`
        WHERE employee = %(employee)s
        ORDER BY recorded_on DESC
        LIMIT %(limit)s
        """,
        {"employee": target_employee, "limit": int(limit)},
        as_dict=True,
    )
    rows.reverse()  # chronological (oldest first) for a left-to-right chart

    return {
        "employee": target_employee,
        "trend": [
            {
                "date": frappe.utils.format_date(r.recorded_on),
                "score": r.score,
                "passed": bool(r.quiz_passed),
            }
            for r in rows
        ],
    }


# ---- Manager Training Analytics ----
# Org-level counterpart to My Training Dashboard: score trend over time
# (monthly average, across everyone), score distribution buckets, and
# completion rate by department. Admin-only -- this is aggregate data, not
# self-service, so it doesn't need a per-employee resolve step.

_SCORE_BUCKETS = [
    ("0-59", 0, 60),
    ("60-69", 60, 70),
    ("70-79", 70, 80),
    ("80-89", 80, 90),
    ("90-100", 90, 101),
]


@frappe.whitelist()
def get_training_analytics(from_date=None, to_date=None, department=None):
    if not _is_admin_user():
        frappe.throw("Only managers can view training analytics.", frappe.PermissionError)

    # ---- shared filter fragments ----
    score_conditions = ["1=1"]
    score_values = {}
    if from_date:
        score_conditions.append("sh.recorded_on >= %(from_date)s")
        score_values["from_date"] = from_date
    if to_date:
        score_conditions.append("sh.recorded_on <= %(to_date)s")
        score_values["to_date"] = to_date
    if department:
        score_conditions.append("emp.department = %(department)s")
        score_values["department"] = department
    score_where = " AND ".join(score_conditions)
    # Score History join to Employee is only needed when filtering by department.
    score_join = "INNER JOIN `tabEmployee` emp ON emp.name = sh.employee" if department else ""

    # Monthly average score trend, across every graded attempt (respects filters).
    monthly_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(sh.recorded_on, '%%Y-%%m') AS month,
            AVG(sh.score) AS avg_score,
            COUNT(*) AS attempts,
            SUM(CASE WHEN sh.quiz_passed THEN 1 ELSE 0 END) AS passed
        FROM `tabDMS Training Score History` sh
        {score_join}
        WHERE {score_where}
        GROUP BY month
        ORDER BY month ASC
        """,
        score_values,
        as_dict=True,
    )
    score_trend = [
        {"month": r.month, "avg_score": round(r.avg_score, 1), "attempts": r.attempts}
        for r in monthly_rows
    ]
    # Pass rate as its own trend -- a flat/rising average score can mask a
    # falling pass rate (many scores barely scraping by), so track separately.
    pass_rate_trend = [
        {
            "month": r.month,
            "pass_rate": round(r.passed / r.attempts * 100, 1) if r.attempts else 0.0,
            "attempts": r.attempts,
        }
        for r in monthly_rows
    ]

    # Score distribution across every graded attempt matching the filters.
    all_scores = [
        r.score for r in frappe.db.sql(
            f"SELECT sh.score FROM `tabDMS Training Score History` sh {score_join} WHERE {score_where}",
            score_values,
            as_dict=True,
        )
    ]
    distribution = []
    for label, lo, hi in _SCORE_BUCKETS:
        count = sum(1 for s in all_scores if lo <= s < hi)
        distribution.append({"label": label, "count": count})

    # ---- Document Acknowledgement based metrics (completion + overdue) ----
    ack_conditions = ["da.status NOT IN ('Suggested', 'Excused')"]
    ack_values = {}
    if department:
        ack_conditions.append("emp.department = %(department)s")
        ack_values["department"] = department
    if from_date:
        ack_conditions.append("(da.due_date IS NULL OR da.due_date >= %(from_date)s)")
        ack_values["from_date"] = from_date
    if to_date:
        ack_conditions.append("(da.due_date IS NULL OR da.due_date <= %(to_date)s)")
        ack_values["to_date"] = to_date
    ack_where = " AND ".join(ack_conditions)

    dept_rows = frappe.db.sql(
        f"""
        SELECT
            emp.department AS department,
            da.status AS status
        FROM `tabDocument Acknowledgement` da
        LEFT JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE {ack_where}
        """,
        ack_values,
        as_dict=True,
    )
    by_dept = {}
    for row in dept_rows:
        dept = row.department or "Unassigned"
        bucket = by_dept.setdefault(dept, {"total": 0, "completed": 0})
        bucket["total"] += 1
        if row.status == "Completed":
            bucket["completed"] += 1

    completion_by_department = [
        {
            "department": dept,
            "total": data["total"],
            "completed": data["completed"],
            "completion_pct": round(data["completed"] / data["total"] * 100, 1) if data["total"] else 0.0,
        }
        for dept, data in by_dept.items()
    ]
    completion_by_department.sort(key=lambda r: r["completion_pct"], reverse=True)

    # Overdue trainings grouped by the month they were due -- shows whether
    # overdue risk is concentrated in old, long-stale due dates or is a
    # recent spike, rather than just a single current overdue count.
    overdue_conditions = ["da.status = 'Overdue'"]
    overdue_values = {}
    if department:
        overdue_conditions.append("emp.department = %(department)s")
        overdue_values["department"] = department
    if from_date:
        overdue_conditions.append("da.due_date >= %(from_date)s")
        overdue_values["from_date"] = from_date
    if to_date:
        overdue_conditions.append("da.due_date <= %(to_date)s")
        overdue_values["to_date"] = to_date
    overdue_where = " AND ".join(overdue_conditions)

    overdue_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(da.due_date, '%%Y-%%m') AS month, COUNT(*) AS overdue_count
        FROM `tabDocument Acknowledgement` da
        LEFT JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE {overdue_where}
        GROUP BY month
        ORDER BY month ASC
        """,
        overdue_values,
        as_dict=True,
    )
    overdue_trend = [{"month": r.month, "overdue_count": r.overdue_count} for r in overdue_rows]

    # ---- Per-employee scores (every employee, not just a top-N leaderboard) ----
    # Own copy of the department/due_date filter (same shape as ack_where/
    # ack_values above, intentionally not the same variables) so an edit to
    # one query's filter can't silently change the other's.
    emp_conditions = ["da.status NOT IN ('Suggested', 'Excused')"]
    emp_values = {}
    if department:
        emp_conditions.append("emp.department = %(department)s")
        emp_values["department"] = department
    if from_date:
        emp_conditions.append("(da.due_date IS NULL OR da.due_date >= %(from_date)s)")
        emp_values["from_date"] = from_date
    if to_date:
        emp_conditions.append("(da.due_date IS NULL OR da.due_date <= %(to_date)s)")
        emp_values["to_date"] = to_date
    emp_where = " AND ".join(emp_conditions)

    emp_rows = frappe.db.sql(
        f"""
        SELECT
            da.employee AS employee,
            emp.employee_name AS employee_name,
            emp.department AS department,
            da.status AS status,
            da.assessment_score AS assessment_score
        FROM `tabDocument Acknowledgement` da
        LEFT JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE {emp_where}
        """,
        emp_values,
        as_dict=True,
    )
    by_employee = {}
    for row in emp_rows:
        if not row.employee:
            continue
        bucket = by_employee.setdefault(row.employee, {
            "employee": row.employee,
            "employee_name": row.employee_name,
            "department": row.department or "Unassigned",
            "total": 0,
            "completed": 0,
            "scores": [],
        })
        bucket["total"] += 1
        if row.status == "Completed":
            bucket["completed"] += 1
            if row.assessment_score is not None:
                bucket["scores"].append(row.assessment_score)

    employee_scores = []
    for data in by_employee.values():
        scores = data.pop("scores")
        employee_scores.append({
            **data,
            "overall_score": round(sum(scores) / len(scores), 1) if scores else None,
            "completion_pct": round(data["completed"] / data["total"] * 100, 1) if data["total"] else 0.0,
        })
    employee_scores.sort(key=lambda r: (r["overall_score"] is None, -(r["overall_score"] or 0)))

    # ---- Every employee's pending/overdue trainings, org-wide (managers need
    # to see everyone's outstanding items, not just the aggregate rate) ----
    pending_conditions = ["da.status IN ('Pending', 'Overdue', 'In Progress', 'Failed')"]
    pending_values = {}
    if department:
        pending_conditions.append("emp.department = %(department)s")
        pending_values["department"] = department
    if from_date:
        pending_conditions.append("(da.due_date IS NULL OR da.due_date >= %(from_date)s)")
        pending_values["from_date"] = from_date
    if to_date:
        pending_conditions.append("(da.due_date IS NULL OR da.due_date <= %(to_date)s)")
        pending_values["to_date"] = to_date
    pending_where = " AND ".join(pending_conditions)

    pending_rows = frappe.db.sql(
        f"""
        SELECT
            emp.employee_name AS employee_name,
            emp.department AS department,
            trn.document AS document,
            da.status AS status,
            da.due_date AS due_date,
            trn.name AS training_record
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabDMS Training Record` trn ON trn.name = da.parent AND da.parenttype = 'DMS Training Record'
        LEFT JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE {pending_where}
        ORDER BY da.due_date ASC
        """,
        pending_values,
        as_dict=True,
    )
    pending_trainings = [
        {
            "employee_name": r.employee_name,
            "department": r.department or "Unassigned",
            "document": r.document,
            "status": r.status,
            "due_date": frappe.utils.format_date(r.due_date) if r.due_date else None,
            "due_date_raw": str(r.due_date) if r.due_date else None,
            "training_record": r.training_record,
        }
        for r in pending_rows
    ]

    return {
        "score_trend": score_trend,
        "pass_rate_trend": pass_rate_trend,
        "distribution": distribution,
        "completion_by_department": completion_by_department,
        "overdue_trend": overdue_trend,
        "employee_scores": employee_scores,
        "pending_trainings": pending_trainings,
        "total_attempts": len(all_scores),
    }


@frappe.whitelist()
def get_departments_for_filter():
    if not _is_admin_user():
        frappe.throw("Only managers can view training analytics.", frappe.PermissionError)
    return frappe.get_all("Department", filters={"disabled": 0}, pluck="name", order_by="name asc")
