import frappe
from frappe.model.document import Document
from frappe.utils import today, now_datetime, getdate, add_months

from quality_dms.dms.doctype.training_settings.training_settings import get_retraining_months


_ALLOWED_TRANSITIONS = {
    "Draft":        {"Assigned", "Cancelled"},
    "Assigned":     {"In Progress", "Overdue", "Cancelled"},
    "In Progress":  {"Completed", "Overdue", "Cancelled"},
    "Overdue":      {"In Progress", "Completed", "Cancelled"},
    "Completed":    {"Verified", "In Progress"},
    "Verified":     {"Closed", "Completed"},
    "Closed":       set(),
    "Cancelled":    set(),
}

_MANAGER_ROLES = frozenset({"System Manager"})

# Roles that may see every employee's row on a training record (mirrors the
# full-visibility role set already used by has_permission/get_permission_query_conditions).
_FULL_VISIBILITY_ROLES = frozenset({"System Manager", "DMS Admin", "DMS Approver", "DMS Reviewer"})


class DMSTrainingRecord(Document):

    def onload(self):
        """Employees must only ever see their own row's status/score when they
        open a training record — other employees' assessment scores are not
        their business. This trims the in-memory `employees` child table sent
        to the client; it is never saved back, so nothing in the database is
        touched and managers/admins/approvers/reviewers keep full visibility."""
        if frappe.session.user == "Administrator":
            return
        if self.owner == frappe.session.user:
            return
        if set(frappe.get_roles(frappe.session.user)) & _FULL_VISIBILITY_ROLES:
            return

        emp = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name", order_by="creation asc"
        )
        self.employees = [row for row in self.employees if emp and row.employee == emp]

    def _restore_stripped_employee_rows(self):
        """Guard against data loss: a non-manager's browser only ever holds
        their own row in `employees` (see onload above). Some whitelisted
        methods (e.g. submit_quiz_and_sign) round-trip that client-side doc
        back to the server and save() it — without this guard, that save
        would silently delete every other employee's assigned row from the
        database. Restore anything present in the DB but missing from the
        in-memory doc whenever the saving user isn't a manager/owner."""
        if self.is_new():
            return
        if frappe.session.user == "Administrator" or self.owner == frappe.session.user:
            return
        if set(frappe.get_roles(frappe.session.user)) & _FULL_VISIBILITY_ROLES:
            return

        existing_rows = frappe.get_all(
            "Document Acknowledgement",
            filters={"parent": self.name, "parenttype": "DMS Training Record"},
            fields="*",
            order_by="idx asc",
        )
        have = {row.employee for row in self.employees}
        for row in existing_rows:
            if row.employee not in have:
                self.append("employees", row)

    def validate(self):
        self._restore_stripped_employee_rows()
        self._prev_status = (
            frappe.db.get_value("DMS Training Record", self.name, "status") or "Draft"
            if not self.is_new() else "Draft"
        )
        self._validate_status_transition()
        self._sync_employee_due_dates()
        self._validate_assessment_scores()
        self._sync_progress()

    def _get_training_quiz(self):
        """Return the DMS Quiz doc attached to this record's document, if any."""
        if not self.document:
            return None
        quiz_name = frappe.db.get_value("Document Library", self.document, "training_quiz")
        if not quiz_name:
            return None
        return frappe.get_cached_doc("DMS Quiz", quiz_name)

    def _validate_assessment_scores(self):
        """When the linked document has a quiz attached, an employee row cannot
        be acknowledged/completed until their assessment_score meets the quiz's
        pass percentage."""
        quiz = self._get_training_quiz()
        for row in self.employees:
            if not quiz or not quiz.active:
                row.quiz_passed = 1 if row.acknowledged else row.quiz_passed
                continue

            pass_pct = quiz.get_effective_pass_percentage()
            score = row.assessment_score or 0

            # Proxy-completed rows (a manager completing on behalf of a departed
            # or non-desk employee who never takes the quiz) are exempt from the
            # pass-score gate — otherwise proxy completion would be impossible
            # for any quiz-backed document.
            if row.acknowledged and score < pass_pct and not row.get("proxy_completed_by"):
                frappe.throw(
                    f"{row.employee_name or row.employee} cannot be marked as acknowledged: "
                    f"assessment score ({score}) is below the required pass percentage "
                    f"({pass_pct}) for quiz '{quiz.title}'."
                )
            row.quiz_passed = 1 if score >= pass_pct else 0

    def on_update(self):
        prev = getattr(self, "_prev_status", self.status)
        if self.status == prev:
            return
        if self.status == "Assigned":
            self._send_assignment_notifications()
        self._log_audit(f"Status changed from {prev} to {self.status}")

    def _validate_status_transition(self):
        if self.is_new():
            return
        prev = self._prev_status
        if prev == self.status:
            return
        allowed = _ALLOWED_TRANSITIONS.get(prev, set())
        if self.status not in allowed:
            frappe.throw(
                f"Cannot transition Training Record from \"{prev}\" to \"{self.status}\". "
                f"Allowed: {', '.join(sorted(allowed)) if allowed else 'none'}."
            )

    def _sync_employee_due_dates(self):
        if not self.due_date:
            return
        for row in self.employees:
            if not row.due_date:
                row.due_date = self.due_date

    def _sync_progress(self):
        today_date = getdate(today())
        # "Suggested" rows are staged (listed by an assignment rule) but not yet
        # actually assigned. "Excused" rows (e.g. departed employees) are a
        # terminal non-completion — both are excluded from the denominator so
        # the record can still reach 100% / Completed. "Failed" rows stay
        # counted because a granted retake can still complete them.
        assigned_rows = [r for r in self.employees if r.status not in ("Suggested", "Excused")]
        total = len(assigned_rows)
        completed = 0

        for row in assigned_rows:
            if row.acknowledged:
                row.status = "Completed"
                if not row.completion_date:
                    row.completion_date = today()
                if not row.expires_on:
                    months = self.retraining_months or get_retraining_months()
                    row.expires_on = add_months(row.completion_date, months)
                completed += 1
            elif row.due_date and getdate(row.due_date) < today_date and row.status not in {"Excused", "Failed"}:
                row.status = "Overdue"

        self.total_assigned = total
        self.total_completed = completed
        self.completion_percentage = round(completed / total * 100, 1) if total > 0 else 0.0

        # If Draft with employees in the table, auto-transition to Assigned
        # (handles rows added manually via Add Row as well as via assign_employees,
        # including the very first save when a manager creates the record with
        # employee rows already added). Auto-created records (from document
        # publish) have only "Suggested" candidates, so total == 0 and they
        # correctly stay Draft.
        if self.status == "Draft" and total > 0:
            self.status = "Assigned"
            if not self.assigned_by:
                self.assigned_by = frappe.session.user
            if not self.assigned_date:
                self.assigned_date = today()

        # Auto-advance parent status within managed states only
        if self.status in {"Assigned", "In Progress"}:
            if total > 0 and completed == total:
                self.status = "Completed"
            elif completed > 0 and self.status == "Assigned":
                self.status = "In Progress"
        elif self.status == "Overdue":
            if total > 0 and completed == total:
                self.status = "Completed"

    def _send_assignment_notifications(self):
        # Only notify rows that are actually assigned — never staged
        # ("Suggested") candidates that a manager hasn't assigned yet.
        self._notify_rows([r for r in self.employees if r.status != "Suggested"])

    def _notify_rows(self, rows):
        doc_title = frappe.db.get_value("Document Library", self.document, "title") or self.document
        due_str = str(self.due_date) if self.due_date else "No due date set"

        for row in rows:
            if not row.employee or row.status == "Suggested":
                continue
            user_id = frappe.db.get_value("Employee", row.employee, "user_id")
            if not user_id:
                continue

            try:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": f"Training Assigned: {doc_title} (v{self.version})",
                    "email_content": (
                        f"You have been assigned to complete training for:<br><br>"
                        f"<b>Document:</b> {doc_title}<br>"
                        f"<b>Version:</b> {self.version}<br>"
                        f"<b>Due Date:</b> {due_str}<br><br>"
                        f"Please open the document, read it carefully, and click "
                        f"<em>Acknowledge</em> to confirm completion."
                    ),
                    "document_type": "DMS Training Record",
                    "document_name": self.name,
                    "for_user": user_id,
                    "type": "Alert",
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DMS Training: in-app notification failed for {user_id}",
                )

            email = frappe.db.get_value("User", user_id, "email")
            if not email:
                continue
            try:
                frappe.sendmail(
                    recipients=[email],
                    subject=f"[DMS Training] {doc_title} — Action Required",
                    message=(
                        f"<p>Dear {row.employee_name or row.employee},</p>"
                        f"<p>You have been assigned to complete training on the following document:</p>"
                        f"<table style='border-collapse:collapse;' cellpadding='6'>"
                        f"<tr><td><strong>Document:</strong></td><td>{doc_title}</td></tr>"
                        f"<tr><td><strong>Version:</strong></td><td>{self.version}</td></tr>"
                        f"<tr><td><strong>Due Date:</strong></td><td>{due_str}</td></tr>"
                        f"<tr><td><strong>Training Record:</strong></td>"
                        f"<td><a href='/app/dms-training-record/{self.name}'>{self.name}</a></td></tr>"
                        f"</table>"
                        f"<p>Please log in, open the document, read it carefully, and "
                        f"click <strong>Acknowledge</strong> to confirm completion.</p>"
                        f"<p><a href='/app/dms-training-record/{self.name}'>Open Training Record</a> | "
                        f"<a href='/app/document-library/{self.document}'>Open Document</a></p>"
                    ),
                    delayed=True,
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DMS Training: email notification failed for {email}",
                )

    def _send_overdue_notifications(self):
        doc_title = frappe.db.get_value("Document Library", self.document, "title") or self.document
        for row in self.employees:
            if row.acknowledged or row.status != "Overdue" or not row.employee:
                continue
            user_id = frappe.db.get_value("Employee", row.employee, "user_id")
            if not user_id:
                continue
            email = frappe.db.get_value("User", user_id, "email")
            if not email:
                continue
            try:
                frappe.sendmail(
                    recipients=[email],
                    subject=f"[DMS Training OVERDUE] {doc_title}",
                    message=(
                        f"<p>Dear {row.employee_name or row.employee},</p>"
                        f"<p><strong>Your training is overdue.</strong></p>"
                        f"<p>The due date for <em>{doc_title} (v{self.version})</em> has passed. "
                        f"Please complete and acknowledge this document as soon as possible.</p>"
                        f"<p><a href='/app/dms-training-record/{self.name}'>Open Training Record</a> | "
                        f"<a href='/app/document-library/{self.document}'>Open Document</a></p>"
                    ),
                    delayed=True,
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DMS Training: overdue email failed for {email}",
                )

    def _log_audit(self, action):
        try:
            frappe.get_doc({
                "doctype": "DMS Audit Log",
                "document": self.document,
                "action": f"[Training {self.name}] {action}",
                "user": frappe.session.user,
                "timestamp": now_datetime(),
                "ip_address": getattr(frappe.local, "request_ip", ""),
            }).insert(ignore_permissions=True)
        except Exception:
            pass

    @frappe.whitelist()
    def assign_employees(self, employee_ids, due_date=None):
        """Assign employees; transitions status Draft → Assigned and sends notifications."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can assign employees to training records.")
        return self._assign_employees(employee_ids, due_date)

    def _assign_employees(self, employee_ids, due_date=None, assigned_by=None):
        """Core assignment logic shared by the whitelisted user-facing method and
        system automation (e.g. DMS Training Assignment Rule) that must bypass the
        manager-role check above since it is not a direct user action."""
        if self.status not in {"Draft", "Assigned"}:
            frappe.throw(
                f"Cannot assign employees to a '{self.status}' training record. "
                f"Only Draft or Assigned records accept new assignments."
            )

        if isinstance(employee_ids, str):
            import json
            employee_ids = json.loads(employee_ids)

        # Rows already actually assigned (anything other than "Suggested") are
        # skipped. A "Suggested" row for a selected employee is *promoted* to
        # "Pending" — this is how the manager turns a staged suggestion into a
        # real assignment.
        rows_by_emp = {row.employee: row for row in self.employees}
        newly_assigned = []

        for emp_id in employee_ids:
            row = rows_by_emp.get(emp_id)
            if row is not None:
                if row.status == "Suggested":
                    row.status = "Pending"
                    if not row.due_date:
                        row.due_date = due_date or self.due_date
                    newly_assigned.append(row)
                continue
            emp_name = frappe.db.get_value("Employee", emp_id, "employee_name") or emp_id
            row = self.append("employees", {
                "employee": emp_id,
                "employee_name": emp_name,
                "status": "Pending",
                "due_date": due_date or self.due_date,
            })
            newly_assigned.append(row)

        if due_date:
            self.due_date = due_date
        if newly_assigned and not self.assigned_by:
            self.assigned_by = assigned_by or frappe.session.user
        if newly_assigned and not self.assigned_date:
            self.assigned_date = today()

        was_draft = self.status == "Draft"
        if was_draft and newly_assigned:
            self.status = "Assigned"

        self.save(ignore_permissions=True)

        # When the record was already Assigned, on_update's Draft→Assigned hook
        # won't fire, so notify this fresh batch directly. (A Draft→Assigned
        # transition is handled by _send_assignment_notifications via on_update.)
        if not was_draft and newly_assigned:
            self._notify_rows(newly_assigned)

        # Give each newly-assigned employee read access to the document (and thus
        # its attached file) so they can actually open and read it before the quiz.
        self._share_document_with_rows(newly_assigned)

        assigned_total = len([r for r in self.employees if r.status != "Suggested"])
        return {"added": len(newly_assigned), "total": assigned_total}

    def _share_document_with_rows(self, rows):
        """Share the linked Document Library record (read-only) with the users of
        the given assignment rows. Private files attached to that document then
        become viewable to those employees. Idempotent — re-sharing is a no-op."""
        if not self.document or not rows:
            return
        for row in rows:
            if not row.employee:
                continue
            user_id = frappe.db.get_value("Employee", row.employee, "user_id")
            if not user_id:
                continue
            try:
                frappe.share.add_docshare(
                    "Document Library", self.document, user_id,
                    read=1, flags={"ignore_share_permission": True},
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DMS Training: failed to share document {self.document} with {user_id}",
                )

    def _stage_employees(self, employee_ids):
        """Add employees to the record as *staged* suggestions (status
        "Suggested") without assigning or notifying them and without leaving
        Draft. Used by DMS Training Assignment Rules so a manager sees the full
        candidate list on the record, then assigns the ones they choose."""
        if self.status not in {"Draft", "Assigned"}:
            return {"staged": 0}
        if isinstance(employee_ids, str):
            import json
            employee_ids = json.loads(employee_ids)

        existing = {row.employee for row in self.employees}
        staged = 0
        for emp_id in employee_ids:
            if emp_id in existing:
                continue
            emp_name = frappe.db.get_value("Employee", emp_id, "employee_name") or emp_id
            self.append("employees", {
                "employee": emp_id,
                "employee_name": emp_name,
                "status": "Suggested",
            })
            staged += 1

        if staged:
            self.save(ignore_permissions=True)
        return {"staged": staged}

    @frappe.whitelist()
    def sign_acknowledgement(self, row_name, password, assessment_score=None):
        """Employee electronically signs off their own training row, using the
        same password-reauthentication + immutable CFR Part 11 Signature Log
        pattern already used for Document Library approvals
        (see api.verify_and_log_signature). Stronger than the old bare
        Signature field: requires the employee's current password and logs a
        tamper-evident record with a meaning-of-signature statement."""
        row = next((r for r in self.employees if r.name == row_name), None)
        if not row:
            frappe.throw("Training row not found on this record.")
        if row.status == "Suggested":
            frappe.throw("This employee is only a suggested candidate and has not been assigned yet.")

        # When the linked document has an active quiz, the score must be produced
        # by the server-graded quiz flow (submit_quiz_and_sign), never supplied
        # by the client — otherwise an employee could pass a fake perfect score
        # and skip the quiz entirely.
        quiz = self._get_training_quiz()
        if quiz and quiz.active:
            frappe.throw(
                "This training requires passing its quiz. Use 'Sign My Acknowledgement' "
                "to take the quiz — it is graded and signed by the system."
            )

        self._do_sign_acknowledgement(row, password, assessment_score)

    def _do_sign_acknowledgement(self, row, password, assessment_score=None):
        """Core e-signature + acknowledgement writer. Callable internally by the
        server-graded quiz flow with a trusted score; the public
        sign_acknowledgement wraps this and blocks client scores on quiz docs."""
        if row.status == "Suggested":
            frappe.throw("This employee is only a suggested candidate and has not been assigned yet.")
        # Never re-sign an already-acknowledged row: it would create a second
        # CFR Part 11 signature-log entry and corrupt the tamper-evident history.
        if row.acknowledged:
            frappe.throw(f"{row.employee_name or row.employee} has already signed this acknowledgement.")

        user_id = frappe.db.get_value("Employee", row.employee, "user_id")
        is_manager = bool(set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES)
        if frappe.session.user != user_id and not is_manager:
            frappe.throw("You can only sign your own training acknowledgement.")

        doc_title = frappe.db.get_value("Document Library", self.document, "title") or self.document
        meaning = (
            f"I attest that I have read, understood, and completed training on "
            f"'{doc_title}' (version {self.version})."
        )

        from quality_dms.dms.api import verify_and_log_signature
        verify_and_log_signature(
            "DMS Training Record", self.name, password, meaning, position=row.employee_name
        )

        row.acknowledged = 1
        row.acknowledged_on = now_datetime()
        if assessment_score is not None:
            row.assessment_score = assessment_score
        self.save(ignore_permissions=True)

        if assessment_score is not None:
            from quality_dms.dms.doctype.dms_training_score_history.dms_training_score_history import record_score
            record_score(row.employee, self.name, assessment_score, row.quiz_passed, self.document)

    def _row_for_current_user(self, row_name):
        """Resolve a training row and enforce that the caller may act on it —
        either it's their own row, or they're a manager. Shared by the quiz
        attempt/submit flow."""
        row = next((r for r in self.employees if str(r.name) == str(row_name)), None)
        if not row:
            frappe.throw("Training row not found on this record.")
        if row.status == "Suggested":
            frappe.throw("This employee is only a suggested candidate and has not been assigned yet.")
        user_id = frappe.db.get_value("Employee", row.employee, "user_id")
        is_manager = bool(set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES)
        if frappe.session.user != user_id and not is_manager:
            frappe.throw("You can only take the quiz for your own training row.")
        return row

    @frappe.whitelist()
    def get_my_acknowledgement_context(self):
        """Resolve the *current logged-in user's own* training row on this record
        and, if the linked document has an active quiz, its questions. The server
        (not the browser) picks the row, so an employee never has to choose from
        other people's rows and can only ever sign their own."""
        emp = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name", order_by="creation asc"
        )
        if not emp:
            frappe.throw(
                "Your login is not linked to an Employee record, so you have no "
                "training row to sign here."
            )
        row = next(
            (r for r in self.employees
             if r.employee == emp and r.status != "Suggested" and not r.acknowledged),
            None,
        )
        if not row:
            frappe.throw("You have no pending training row to sign on this record.")

        quiz = self._get_training_quiz()
        quiz_data = None
        if quiz and quiz.active:
            quiz_data = {
                "title": quiz.title,
                "pass_percentage": quiz.get_effective_pass_percentage(),
                "questions": quiz.get_questions_for_display(),
            }
        # A failed attempt locks the quiz until a manager grants a retake.
        retake_locked = bool(row.quiz_attempts and not row.acknowledged and not row.retake_allowed)
        return {
            "row_name": row.name,
            "quiz": quiz_data,
            "retake_locked": retake_locked,
            "last_score": row.assessment_score,
            "attempts": row.quiz_attempts,
        }

    @frappe.whitelist()
    def get_quiz_for_attempt(self, row_name):
        """Return the quiz questions (no answer key) for the employee to attempt,
        or None when the linked document has no active quiz."""
        self._row_for_current_user(row_name)
        quiz = self._get_training_quiz()
        if not quiz or not quiz.active:
            return None
        return {
            "title": quiz.title,
            "pass_percentage": quiz.get_effective_pass_percentage(),
            "questions": quiz.get_questions_for_display(),
        }

    @frappe.whitelist()
    def submit_quiz_and_sign(self, row_name, answers, password):
        """Grade the employee's quiz answers and record the attempt whether they
        pass or fail. On a passing score, the acknowledgement is e-signed and the
        row completes. On a failing score, the attempt (score + attempt count) is
        recorded but nothing is signed — the employee cannot retake until a
        manager grants a retake (retake_allowed)."""
        row = self._row_for_current_user(row_name)

        # Already completed — do not regrade, bump the attempt count, or re-sign.
        if row.acknowledged:
            frappe.throw("You have already completed and signed this training.")

        # A failed attempt locks the row: no re-attempt until a manager allows a
        # retake. The very first attempt (quiz_attempts == 0) is always allowed.
        if row.quiz_attempts and not row.acknowledged and not row.retake_allowed:
            frappe.throw(
                "You have already used your quiz attempt and did not pass. "
                "Ask your manager to allow a retake before trying again."
            )

        quiz = self._get_training_quiz()
        if not quiz or not quiz.active:
            frappe.throw("No active quiz is attached to this training's document.")

        if isinstance(answers, str):
            import json
            answers = json.loads(answers)

        score = quiz.grade(answers)
        pass_pct = quiz.get_effective_pass_percentage()
        passed = score >= pass_pct

        # Record the attempt regardless of outcome.
        row.quiz_attempts = (row.quiz_attempts or 0) + 1
        # A granted retake is consumed by this submission.
        row.retake_allowed = 0

        if passed:
            # Server-graded score — write it through the internal signer (the
            # public sign_acknowledgement blocks client-supplied scores on quizzes).
            self._do_sign_acknowledgement(row, password, assessment_score=score)
            return {"passed": True, "score": score, "pass_percentage": pass_pct,
                    "attempts": row.quiz_attempts}

        # Failed — record the score/attempt but do not acknowledge or sign.
        row.assessment_score = score
        row.quiz_passed = 0
        row.status = "Failed"
        self.save(ignore_permissions=True)

        from quality_dms.dms.doctype.dms_training_score_history.dms_training_score_history import record_score
        record_score(row.employee, self.name, score, False, self.document)

        return {
            "passed": False,
            "score": score,
            "pass_percentage": pass_pct,
            "attempts": row.quiz_attempts,
            "message": (
                f"You scored {score:.1f}%. The passing score is {pass_pct:.1f}%. "
                f"Your attempt has been recorded. A manager must allow a retake "
                f"before you can try again."
            ),
        }

    @frappe.whitelist()
    def allow_quiz_retake(self, row_name):
        """Manager/admin grants a single quiz retake to an employee whose last
        attempt failed. The grant is consumed on the employee's next submission."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only a manager can allow a quiz retake.", frappe.PermissionError)
        row = next((r for r in self.employees if str(r.name) == str(row_name)), None)
        if not row:
            frappe.throw("Training row not found on this record.")
        if row.acknowledged:
            frappe.throw("This employee has already completed the training — no retake needed.")
        if not row.quiz_attempts:
            frappe.throw("This employee has not attempted the quiz yet.")
        row.retake_allowed = 1
        # Reopen the row for the retake (clear the "Failed" state).
        if row.status == "Failed":
            row.status = "In Progress"
        self.save(ignore_permissions=True)
        return {"row_name": row_name, "employee": row.employee_name or row.employee}

    def _category_requires_dual_signoff(self):
        if not self.category:
            return False
        return bool(frappe.db.get_value("Document Category", self.category, "requires_dual_signoff"))

    @frappe.whitelist()
    def verify_completion(self, notes=None):
        """Manager verifies a Completed training record. When the linked
        document's Category requires dual sign-off, this only records the
        primary signature and leaves status at 'Completed' until a different
        manager calls countersign_completion()."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can verify training completion.")
        if self.status != "Completed":
            frappe.throw(
                f"Training record must be 'Completed' before it can be Verified. "
                f"Current status: '{self.status}'."
            )
        # Segregation of duties: a verifier may not verify their own training row.
        own_emp = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name", order_by="creation asc"
        )
        if own_emp and any(r.employee == own_emp for r in self.employees):
            frappe.throw("You cannot verify a training record that you are assigned to.")
        # Do not silently overwrite an already-recorded primary verification —
        # a second, different manager must use Countersign, not Verify.
        if self.verified_by and self.verified_by != frappe.session.user:
            frappe.throw(
                f"This record's primary verification was already recorded by {self.verified_by}. "
                f"A second manager should use 'Countersign Completion' instead."
            )
        self.verified_by = frappe.session.user
        self.verified_date = today()
        if notes:
            self.verification_notes = notes

        if self._category_requires_dual_signoff():
            self.save(ignore_permissions=True)
            frappe.msgprint(
                "Primary sign-off recorded. This document's category requires a second "
                "manager to countersign before the record moves to Verified."
            )
            return

        self.status = "Verified"
        self._mark_all_rows_verified()
        self.save(ignore_permissions=True)
        self._attach_certificate()

    @frappe.whitelist()
    def countersign_completion(self, notes=None):
        """Second manager's sign-off, required only when the linked document's
        Category has Requires Dual Sign-off checked."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can countersign training verification.")
        if not self._category_requires_dual_signoff():
            frappe.throw("This training record's document category does not require dual sign-off.")
        if not self.verified_by:
            frappe.throw("A primary verification must be recorded first (Verify Completion).")
        if frappe.session.user == self.verified_by:
            frappe.throw("The countersignature must come from a different manager than the primary verifier.")
        if self.status != "Completed":
            frappe.throw(f"Training record must be 'Completed' before it can be countersigned. Current status: '{self.status}'.")

        self.secondary_verified_by = frappe.session.user
        self.secondary_verified_date = today()
        if notes:
            self.secondary_verification_notes = notes
        self.status = "Verified"
        self._mark_all_rows_verified()
        self.save(ignore_permissions=True)
        self._attach_certificate()

    def _mark_all_rows_verified(self):
        """Whole-record verification implicitly verifies every completed row —
        stamp any row an individual verify_employee() call hasn't already
        covered, so per-row verification data is always complete once the
        record itself reaches Verified."""
        for row in self.employees:
            if row.acknowledged and not row.employee_verified_by:
                row.employee_verified_by = frappe.session.user
                row.employee_verified_date = today()

    @frappe.whitelist()
    def verify_employee(self, row_name, notes=None):
        """Manager verifies a single employee's completed training row,
        independently of the whole record. Lets a manager sign off employees
        as they finish rather than waiting for every assignee to complete —
        generates that employee's certificate immediately."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can verify individual training rows.")
        if self.status in {"Closed", "Cancelled"}:
            frappe.throw(f"Cannot verify a row on a '{self.status}' training record.")

        row = next((r for r in self.employees if str(r.name) == str(row_name)), None)
        if not row:
            frappe.throw("Training row not found on this record.")
        if not row.acknowledged:
            frappe.throw("This employee has not completed their training yet.")

        # Segregation of duties: a verifier may not verify their own row.
        own_emp = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name", order_by="creation asc"
        )
        if own_emp and row.employee == own_emp:
            frappe.throw("You cannot verify your own training row.")

        if row.employee_verified_by:
            frappe.throw(f"This row was already verified by {row.employee_verified_by}.")

        row.employee_verified_by = frappe.session.user
        row.employee_verified_date = today()
        if notes:
            row.employee_verification_notes = notes
        self.save(ignore_permissions=True)
        self._attach_employee_certificate(row)

    def _attach_certificate(self):
        """Generate one personal Training Certificate PDF per completed
        employee, attached to that employee's acknowledgement row so only they
        (and managers) can see it. Best-effort — a PDF rendering failure
        (e.g. wkhtmltopdf unavailable) must not block verification, which has
        already been saved at this point."""
        for row in self.employees:
            if not (row.acknowledged or row.completion_date):
                continue
            try:
                self._attach_employee_certificate(row)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DMS Training: failed to attach certificate for {self.name}/{row.employee}",
                )

    def _attach_employee_certificate(self, row):
        """Render the certificate for a single acknowledgement row as a private
        file OWNED by that employee (deliberately not attached to this record:
        the private-file route grants download to anyone who can read the
        attached document, which would expose certificates to co-assignees).
        Idempotent — skips if already generated."""
        if row.certificate_file:
            return
        file_name = f"{self.name}-{row.employee}-certificate.pdf"
        # Render the record with only this employee's row so the print format
        # produces a personal certificate.
        doc = frappe.get_doc(self.doctype, self.name)
        doc.employees = [r for r in doc.employees if r.name == row.name]
        pdf_content = frappe.get_print(
            self.doctype, self.name, print_format="Training Certificate", doc=doc, as_pdf=True
        )
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "content": pdf_content,
            "is_private": 1,
        })
        file_doc.save(ignore_permissions=True)
        employee_user = frappe.db.get_value("Employee", row.employee, "user_id")
        if employee_user:
            frappe.db.set_value("File", file_doc.name, "owner", employee_user, update_modified=False)
        frappe.db.set_value("Document Acknowledgement", row.name, "certificate_file",
                            file_doc.file_url, update_modified=False)
        row.certificate_file = file_doc.file_url

    @frappe.whitelist()
    def get_my_certificate(self):
        """Return the logged-in employee's own certificate file URL (or None)."""
        employee = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name", order_by="creation asc"
        )
        if not employee:
            return None
        row = next((r for r in self.employees if r.employee == employee), None)
        return row.certificate_file if row else None

    @frappe.whitelist()
    def close_record(self, notes=None):
        """Manager/Admin closes a Verified training record."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can close training records.")
        if self.status != "Verified":
            frappe.throw(
                f"Training record must be 'Verified' before it can be Closed. "
                f"Current status: '{self.status}'."
            )
        self.closed_by = frappe.session.user
        self.closed_date = today()
        if notes:
            self.closure_notes = notes
        self.status = "Closed"
        self.save(ignore_permissions=True)

    @frappe.whitelist()
    def cancel_record(self, reason=None):
        """Manager/Admin cancels a training record at any active stage."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can cancel training records.")
        if self.status in {"Closed", "Cancelled"}:
            frappe.throw(f"Cannot cancel a record that is already '{self.status}'.")
        if reason:
            self.closure_notes = reason
        self.status = "Cancelled"
        self.save(ignore_permissions=True)

    @frappe.whitelist()
    def verify_effectiveness(self, rating, notes=None):
        """Manager records a follow-up effectiveness check — confirming the
        employee is actually applying the training on the job, distinct from
        the earlier document-read acknowledgement/verification."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can record a training effectiveness check.")
        if self.status not in {"Verified", "Closed"}:
            frappe.throw(
                f"An effectiveness check can only be recorded once a record is 'Verified' or 'Closed'. "
                f"Current status: '{self.status}'."
            )
        if rating not in {"Effective", "Partially Effective", "Not Effective"}:
            frappe.throw("Invalid effectiveness rating.")

        self.effectiveness_rating = rating
        self.effectiveness_verified_by = frappe.session.user
        self.effectiveness_verified_date = today()
        if notes:
            self.effectiveness_notes = notes
        self.save(ignore_permissions=True)
        self._log_audit(f"Effectiveness check recorded: {rating}")

    @frappe.whitelist()
    def proxy_complete_acknowledgement(self, row_name, reason):
        """Manager completes a training row on behalf of an employee who
        cannot self-sign (e.g. departed, no system access, non-desk user).
        Distinct from sign_acknowledgement — no password/e-signature is taken
        from the employee since they aren't the one completing this action;
        the manager's identity and reason are recorded instead for audit
        traceability."""
        if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
            frappe.throw("Only System Managers can complete training on behalf of an employee.")
        if not reason:
            frappe.throw("A reason is required to complete training on an employee's behalf.")

        row = next((r for r in self.employees if str(r.name) == str(row_name)), None)
        if not row:
            frappe.throw("Training row not found on this record.")
        if row.status == "Suggested":
            frappe.throw("This employee is only a suggested candidate and has not been assigned yet.")
        if row.acknowledged:
            frappe.throw(f"{row.employee_name or row.employee} has already completed this training.")

        row.acknowledged = 1
        row.acknowledged_on = now_datetime()
        row.proxy_completed_by = frappe.session.user
        row.proxy_reason = reason
        self.save(ignore_permissions=True)
        self._log_audit(
            f"Proxy completion for {row.employee_name or row.employee} by "
            f"{frappe.session.user} — reason: {reason}"
        )


# ── Module-level functions ────────────────────────────────────────────────────


def mark_overdue_training_records():
    """Scheduler: daily job to mark active training records Overdue when past due date."""
    today_date = getdate(today())

    overdue_names = frappe.get_all(
        "DMS Training Record",
        filters={
            "status": ("in", ("Assigned", "In Progress")),
            "due_date": ("<", today_date),
        },
        pluck="name",
    )

    for name in overdue_names:
        try:
            doc = frappe.get_doc("DMS Training Record", name)
            doc.status = "Overdue"
            doc.save(ignore_permissions=True)
            doc._send_overdue_notifications()
            # Skip commit in test mode — committing inside a test transaction
            # permanently leaks records by breaking the post-test rollback.
            if not frappe.flags.in_test:
                frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"DMS Training: failed to mark {name} as Overdue",
            )


def escalate_overdue_training():
    """Scheduler: daily job. Once an unacknowledged row has been overdue for
    Training Settings.escalation_days, email the employee's manager
    (Employee.reports_to) in addition to the employee. Fires once per row via
    the `escalated` flag."""
    from quality_dms.dms.doctype.training_settings.training_settings import get_escalation_days

    escalation_days = get_escalation_days()
    cutoff = frappe.utils.add_days(getdate(today()), -escalation_days)

    rows = frappe.get_all(
        "Document Acknowledgement",
        filters={
            "parenttype": "DMS Training Record",
            "acknowledged": 0,
            "status": "Overdue",
            "escalated": 0,
            "due_date": ("<", cutoff),
        },
        fields=["name", "parent", "employee", "employee_name"],
    )
    if not rows:
        return

    for row in rows:
        try:
            # Don't escalate rows inside records that are no longer active.
            if frappe.db.get_value("DMS Training Record", row.parent, "status") in (
                "Cancelled", "Closed", "Verified"
            ):
                frappe.db.set_value("Document Acknowledgement", row.name, "escalated", 1, update_modified=False)
                continue
            manager_employee = frappe.db.get_value("Employee", row.employee, "reports_to")
            if not manager_employee:
                frappe.db.set_value("Document Acknowledgement", row.name, "escalated", 1, update_modified=False)
                continue

            manager_user = frappe.db.get_value("Employee", manager_employee, "user_id")
            manager_email = frappe.db.get_value("User", manager_user, "email") if manager_user else None
            if not manager_email:
                frappe.db.set_value("Document Acknowledgement", row.name, "escalated", 1, update_modified=False)
                continue

            doc_title = frappe.db.get_value(
                "DMS Training Record", row.parent, "document_title"
            ) or row.parent

            frappe.sendmail(
                recipients=[manager_email],
                subject=f"[DMS Training ESCALATION] {row.employee_name} — {doc_title}",
                message=(
                    f"<p>Dear Manager,</p>"
                    f"<p>Your direct report <strong>{row.employee_name}</strong> has not completed "
                    f"the following training, which is now more than {escalation_days} day(s) overdue:</p>"
                    f"<p><strong>Training Record:</strong> {row.parent}<br>"
                    f"<strong>Document:</strong> {doc_title}</p>"
                    f"<p>Please follow up to ensure this is completed as soon as possible.</p>"
                ),
                delayed=True,
            )
            frappe.db.set_value("Document Acknowledgement", row.name, "escalated", 1, update_modified=False)
            if not frappe.flags.in_test:
                frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"DMS Training: escalation failed for row {row.name}",
            )


def send_manager_training_digest():
    """Scheduler: weekly job. One summary email per manager listing their
    direct reports' pending/overdue training counts."""
    open_rows = frappe.get_all(
        "Document Acknowledgement",
        filters={
            "parenttype": "DMS Training Record",
            "acknowledged": 0,
            "status": ("in", ("Pending", "In Progress", "Overdue")),
        },
        fields=["employee", "employee_name", "status"],
    )
    if not open_rows:
        return

    employee_ids = {r.employee for r in open_rows if r.employee}
    reports_to = {
        e.name: e.reports_to
        for e in frappe.get_all("Employee", filters={"name": ("in", list(employee_ids))}, fields=["name", "reports_to"])
    }

    by_manager = {}
    for row in open_rows:
        manager_employee = reports_to.get(row.employee)
        if not manager_employee:
            continue
        bucket = by_manager.setdefault(manager_employee, {"pending": 0, "overdue": 0, "names": set()})
        bucket["names"].add(row.employee_name)
        if row.status == "Overdue":
            bucket["overdue"] += 1
        else:
            bucket["pending"] += 1

    for manager_employee, stats in by_manager.items():
        try:
            manager_user = frappe.db.get_value("Employee", manager_employee, "user_id")
            manager_email = frappe.db.get_value("User", manager_user, "email") if manager_user else None
            if not manager_email:
                continue

            frappe.sendmail(
                recipients=[manager_email],
                subject="[DMS Training] Weekly team training summary",
                message=(
                    f"<p>Dear Manager,</p>"
                    f"<p>Summary of pending training for your team "
                    f"({', '.join(sorted(stats['names']))}):</p>"
                    f"<ul>"
                    f"<li>Pending/In Progress assignments: {stats['pending']}</li>"
                    f"<li>Overdue assignments: {stats['overdue']}</li>"
                    f"</ul>"
                    f"<p>Please check in with your team to help close these out.</p>"
                ),
                delayed=True,
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"DMS Training: manager digest failed for {manager_employee}",
            )


def excuse_departed_employee(employee_name):
	"""Mark an employee's open (unacknowledged) training rows as Excused when
	they leave the company, so they stop counting against compliance and stop
	receiving overdue reminders. Called from Employee.on_update (see hooks.py)
	when status transitions to a non-Active value."""
	open_rows = frappe.get_all(
		"Document Acknowledgement",
		filters={
			"parenttype": "DMS Training Record",
			"employee": employee_name,
			"acknowledged": 0,
			"status": ("!=", "Excused"),
		},
		fields=["name", "parent"],
	)
	if not open_rows:
		return

	affected_parents = set()
	for row in open_rows:
		frappe.db.set_value(
			"Document Acknowledgement", row.name, "status", "Excused", update_modified=False
		)
		affected_parents.add(row.parent)

	for parent in affected_parents:
		try:
			doc = frappe.get_doc("DMS Training Record", parent)
			doc.save(ignore_permissions=True)
			if not frappe.flags.in_test:
				frappe.db.commit()
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"DMS Training: failed to recompute {parent} after excusing {employee_name}",
			)


def check_training_expiry():
	"""Scheduler: daily job that reopens training rows whose retraining cycle
	has expired. Resets the row to Pending and, for records that had reached a
	terminal state, reopens the parent so the employee is re-notified via the
	normal Assigned-status flow."""
	today_date = getdate(today())

	expired_rows = frappe.get_all(
		"Document Acknowledgement",
		filters={
			"parenttype": "DMS Training Record",
			"acknowledged": 1,
			"expires_on": ("<", today_date),
		},
		fields=["name", "parent"],
	)
	if not expired_rows:
		return

	# Cancelled records must not be reopened; skip their rows entirely.
	parent_status = {
		p: frappe.db.get_value("DMS Training Record", p, "status")
		for p in {r.parent for r in expired_rows}
	}

	affected_parents = set()
	reset_rows_by_parent = {}
	for row in expired_rows:
		if parent_status.get(row.parent) == "Cancelled":
			continue
		# Delete the previous cycle's certificate and clear the pointer so a fresh
		# certificate is generated when the employee re-completes; otherwise
		# _attach_employee_certificate would skip the row (stale cert kept forever).
		old_cert = frappe.db.get_value("Document Acknowledgement", row.name, "certificate_file")
		if old_cert:
			old_file = frappe.db.get_value("File", {"file_url": old_cert}, "name")
			if old_file:
				frappe.delete_doc("File", old_file, ignore_permissions=True, force=1, delete_permanently=True)
		frappe.db.set_value(
			"Document Acknowledgement",
			row.name,
			{
				"acknowledged": 0,
				"status": "Pending",
				"completion_date": None,
				"expires_on": None,
				"quiz_passed": 0,
				"certificate_file": None,
			},
			update_modified=False,
		)
		affected_parents.add(row.parent)
		reset_rows_by_parent.setdefault(row.parent, set()).add(row.name)

	for parent in affected_parents:
		try:
			parent_status_now = frappe.db.get_value("DMS Training Record", parent, "status")
			if parent_status_now == "Cancelled":
				continue

			doc = frappe.get_doc("DMS Training Record", parent)
			# Recompute the parent aggregates from the freshly-reset rows so
			# dashboards / compliance reports don't keep showing the record as
			# fully complete after a row has been reopened for retraining.
			assigned_rows = [r for r in doc.employees if r.status not in ("Suggested", "Excused")]
			total = len(assigned_rows)
			completed = sum(1 for r in assigned_rows if r.acknowledged)
			frappe.db.set_value(
				"DMS Training Record",
				parent,
				{
					"status": "In Progress" if completed > 0 else "Assigned",
					"total_assigned": total,
					"total_completed": completed,
					"completion_percentage": round(completed / total * 100, 1) if total else 0.0,
				},
				update_modified=False,
			)
			doc.reload()
			doc._log_audit("Reopened for retraining — one or more assignments expired")
			# Notify ONLY the employees whose training actually expired this
			# cycle — never the co-assignees whose training is still valid.
			reset_names = reset_rows_by_parent.get(parent, set())
			doc._notify_rows([r for r in doc.employees if r.name in reset_names])
			if not frappe.flags.in_test:
				frappe.db.commit()
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"DMS Training: failed to process expiry for {parent}",
			)


_SCOPE_TYPES = frozenset({"Employee", "Department", "Employee Group", "Company"})


def _resolve_employee_ids_for_scope(scope_type, scope_value, include_subdepartments=False):
	"""Resolve a targeting scope down to a flat list of active Employee IDs.
	Shared by the count-preview and the actual bulk-assign endpoint so the
	two can never disagree about who's included."""
	if scope_type not in _SCOPE_TYPES:
		frappe.throw(f"Invalid scope_type '{scope_type}'. Must be one of: {', '.join(sorted(_SCOPE_TYPES))}.")
	if not scope_value:
		frappe.throw("scope_value is required.")

	if scope_type == "Employee":
		# Accept either a single employee id or a JSON-encoded list, so this
		# scope can also serve the plain "pick individuals" case.
		if isinstance(scope_value, str) and scope_value.strip().startswith("["):
			import json
			return json.loads(scope_value)
		return [scope_value] if isinstance(scope_value, str) else list(scope_value)

	if scope_type == "Department":
		departments = [scope_value]
		if include_subdepartments:
			from frappe.utils.nestedset import get_descendants_of
			departments += get_descendants_of("Department", scope_value, ignore_permissions=True)
		return frappe.get_all(
			"Employee",
			filters={"status": "Active", "department": ("in", departments)},
			pluck="name",
		)

	if scope_type == "Company":
		return frappe.get_all(
			"Employee",
			filters={"status": "Active", "company": scope_value},
			pluck="name",
		)

	# Employee Group: the group's own child table is a static, curated list —
	# still filtered to currently-Active employees so someone who left after
	# being added to the group doesn't get re-assigned training.
	group_employee_ids = frappe.get_all(
		"Employee Group Table",
		filters={"parenttype": "Employee Group", "parent": scope_value},
		pluck="employee",
	)
	if not group_employee_ids:
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "name": ("in", group_employee_ids)},
		pluck="name",
	)


@frappe.whitelist()
def count_employees_for_scope(scope_type, scope_value, include_subdepartments=False):
	"""Preview how many employees a scope would resolve to, before committing
	to the actual bulk assignment — assigning to a whole department/company is
	hard to casually undo, so the caller should see the number first."""
	if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
		frappe.throw("Only System Managers can preview training assignment scopes.")

	employee_ids = _resolve_employee_ids_for_scope(
		scope_type, scope_value, frappe.utils.cint(include_subdepartments)
	)
	return {"count": len(employee_ids)}


@frappe.whitelist()
def assign_by_scope(training_record, scope_type, scope_value, due_date=None, include_subdepartments=False):
	"""Assign training to every (active) employee matching a scope — a whole
	Department (optionally including sub-departments), an Employee Group, an
	entire Company, or a plain list of individual employees — instead of
	requiring the caller to already have every employee id in hand. Resolves
	the scope, then delegates to the exact same core assignment method the
	single-employee and bulk-employee-list flows already use, so status
	guards, dedup-against-existing-rows, and notifications all behave
	identically regardless of how the employee list was produced."""
	if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
		frappe.throw("Only System Managers can assign training by scope.")

	employee_ids = _resolve_employee_ids_for_scope(
		scope_type, scope_value, frappe.utils.cint(include_subdepartments)
	)
	if not employee_ids:
		frappe.throw(f"No active employees matched this {scope_type} scope.")

	doc = frappe.get_doc("DMS Training Record", training_record)
	result = doc._assign_employees(employee_ids, due_date)
	result["scope_type"] = scope_type
	result["scope_value"] = scope_value
	result["matched"] = len(employee_ids)

	if doc.document:
		from quality_dms.dms.file_manager import log_file_event
		log_file_event(
			doc.document,
			f"Training assigned by scope ({scope_type}: {scope_value}, {result['added']} employee(s) newly added)",
		)

	return result


@frappe.whitelist()
def bulk_assign_employees(training_record_names, employee_ids, due_date=None):
	"""Assign the same set of employees to many Training Records at once
	(e.g. a new cohort that needs several existing SOPs). Reuses the same
	per-record assignment logic as the single-record flow, so all the usual
	rules (status guard, dedup, notifications) apply per record."""
	if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
		frappe.throw("Only System Managers can bulk-assign employees.")

	import json
	if isinstance(training_record_names, str):
		training_record_names = json.loads(training_record_names)
	if isinstance(employee_ids, str):
		employee_ids = json.loads(employee_ids)

	results = {}
	for name in training_record_names:
		try:
			doc = frappe.get_doc("DMS Training Record", name)
			results[name] = doc._assign_employees(employee_ids, due_date)
		except Exception as e:
			results[name] = {"error": str(e)}
	return results


@frappe.whitelist()
def bulk_verify_completion(training_record_names, notes=None):
	"""Verify many Completed training records at once (e.g. end of a training
	cycle). Records not in 'Completed' status are skipped and reported, not
	silently dropped."""
	if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
		frappe.throw("Only System Managers can bulk-verify training records.")

	import json
	if isinstance(training_record_names, str):
		training_record_names = json.loads(training_record_names)

	results = {}
	for name in training_record_names:
		try:
			doc = frappe.get_doc("DMS Training Record", name)
			doc.verify_completion(notes=notes)
			results[name] = "verified" if doc.status == "Verified" else doc.status
		except Exception as e:
			results[name] = f"error: {e}"
	return results


@frappe.whitelist()
def bulk_close_records(training_record_names, notes=None):
	"""Close many Verified training records at once."""
	if not (set(frappe.get_roles(frappe.session.user)) & _MANAGER_ROLES):
		frappe.throw("Only System Managers can bulk-close training records.")

	import json
	if isinstance(training_record_names, str):
		training_record_names = json.loads(training_record_names)

	results = {}
	for name in training_record_names:
		try:
			doc = frappe.get_doc("DMS Training Record", name)
			doc.close_record(notes=notes)
			results[name] = "closed"
		except Exception as e:
			results[name] = f"error: {e}"
	return results


def get_permission_query_conditions(user):
    """Row-level permission filter for DMS Training Record list views."""
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))

    # Approvers/reviewers publish documents (which auto-creates training
    # records), so they need full visibility to manage the training rollout.
    if roles & {"System Manager", "DMS Admin", "DMS Approver", "DMS Reviewer"}:
        return ""

    escaped_user = frappe.db.escape(user)

    # Join tabEmployee directly so the condition works even when the Python-side
    # user_id lookup returns None (e.g. Employee record exists but user_id not set).
    assigned_condition = (
        f"EXISTS ("
        f"SELECT 1 FROM `tabDocument Acknowledgement` da "
        f"INNER JOIN `tabEmployee` emp ON emp.name = da.employee "
        f"WHERE da.parent = `tabDMS Training Record`.name "
        f"AND emp.user_id = {escaped_user} "
        f"AND da.parenttype = 'DMS Training Record'"
        f")"
    )

    # Owners always see records they created (e.g. auto-created on publish),
    # regardless of which roles they hold.
    return f"({assigned_condition} OR `tabDMS Training Record`.owner = {escaped_user})"


def has_permission(doc, user=None, ptype="read"):
    """Per-document check mirroring get_permission_query_conditions: employees
    may only read training records they are assigned to (or created)."""
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return True

    roles = set(frappe.get_roles(user))
    if roles & {"System Manager", "DMS Admin", "DMS Approver", "DMS Reviewer"}:
        return True

    # Only restrict reads; writes are governed by DocPerm / controller checks.
    if not doc or ptype != "read":
        return True

    if doc.owner == user:
        return True

    return bool(
        frappe.db.sql(
            """
            SELECT 1 FROM `tabDocument Acknowledgement` da
            INNER JOIN `tabEmployee` emp ON emp.name = da.employee
            WHERE da.parent = %s AND da.parenttype = 'DMS Training Record'
                AND emp.user_id = %s
            LIMIT 1
            """,
            (doc.name, user),
        )
    )
