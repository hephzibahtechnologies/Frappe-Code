import datetime
from io import BytesIO

import frappe
from frappe.utils import cint

# Select value that means "no single-document restriction".
ALL_DOCUMENTS = "__all__"

# Keep in sync with training_assessment_results_register.html (print view).
BANNER_LINES = (
    "Hephzibah Technologies Inc/Hephzibah Technologies India Private Ltd.",
    "Training Quiz/Assessment Results Register",
)

# The quiz engine only persists a percentage (see api._get_assessment_scores),
# so Maximum Marks is always 100 and Marks Obtained equals Score (%).
MAXIMUM_MARKS = 100

# Same "who sees everyone" set as DMS Training Score History.
ADMIN_ROLES = {"System Manager", "DMS Admin", "DMS Approver", "DMS Reviewer"}

RESULT_STATES = ("Pass", "Fail", "Pending")

# (label, fieldname, fieldtype, report width, excel width)
COLUMNS = [
    ("Sr. No.", "sr_no", "Int", 70, 8),
    ("Assessment ID", "assessment_id", "Data", 130, 16),
    ("Training Title", "training_title", "Data", 240, 34),
    ("Date of Completion", "date_of_completion", "Date", 130, 16),
    ("Employee ID", "employee_id", "Data", 120, 14),
    ("Employee Name", "employee_name", "Data", 170, 22),
    ("Department", "department", "Data", 160, 22),
    ("Trainer", "trainer", "Data", 150, 20),
    ("Maximum Marks", "maximum_marks", "Float", 110, 12),
    ("Marks Obtained", "marks_obtained", "Float", 110, 12),
    ("Score (%)", "score_pct", "Float", 100, 11),
    ("Pass Mark (%)", "pass_mark_pct", "Float", 110, 12),
    ("Result (Pass/Fail)", "result", "Data", 120, 14),
    ("Remarks", "remarks", "Data", 300, 44),
]


def execute(filters=None):
    filters = filters or {}
    if not filters.get("training_document"):
        # The dropdown fills in (and selects) a document right after the page
        # loads; until then there is nothing to show.
        return (
            _get_columns(),
            [],
            "Select a Training Document (or All Documents) to view the assessment register.",
            None,
            [],
        )
    rows = get_register_rows(filters)
    return _get_columns(), rows, None, None, _get_summary(rows)


def _get_columns():
    columns = []
    for label, fieldname, fieldtype, width, _excel_width in COLUMNS:
        column = {"label": label, "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
        if fieldname in ("marks_obtained", "score_pct", "pass_mark_pct", "maximum_marks"):
            column["precision"] = 1
        columns.append(column)
    return columns


def assessment_id_for(document):
    """Document-level ID derived from the Document Library name.

    Names (DOC-YYYY-####) are generated once and never reused, so the ID stays
    the same when other documents are deleted. The year is part of the number
    because the series restarts each year.
    """
    suffix = document[4:] if document.startswith("DOC-") else document
    return f"QA-{suffix}"


def _check_access():
    if frappe.session.user != "Administrator" and not (set(frappe.get_roles()) & ADMIN_ROLES):
        frappe.throw("Not permitted to view the assessment register.", frappe.PermissionError)


@frappe.whitelist()
def get_training_documents():
    """Options for the Training Document dropdown: every document that has at
    least one assigned employee or a recorded quiz attempt (a document whose
    training records have nobody assigned would only open an empty report)."""
    _check_access()
    rows = frappe.db.sql(
        """
        SELECT dl.name, dl.title
        FROM `tabDocument Library` dl
        WHERE dl.name IN (
                SELECT tr.document
                FROM `tabDMS Training Record` tr
                INNER JOIN `tabDocument Acknowledgement` da
                    ON da.parent = tr.name AND da.parenttype = 'DMS Training Record'
                WHERE tr.document IS NOT NULL AND tr.status != 'Cancelled'
            )
            OR dl.name IN (
                SELECT COALESCE(tr.document, sh.document)
                FROM `tabDMS Training Score History` sh
                LEFT JOIN `tabDMS Training Record` tr ON tr.name = sh.training_record
                WHERE COALESCE(tr.document, sh.document) IS NOT NULL
            )
        ORDER BY dl.title, dl.name
        """,
        as_dict=True,
    )
    return [
        {"value": r.name, "label": f"{r.title or r.name} ({assessment_id_for(r.name)})"} for r in rows
    ]


def get_register_rows(filters):
    from quality_dms.dms.doctype.training_settings.training_settings import get_pass_percentage

    document = filters.get("training_document")
    document = None if document in (None, "", ALL_DOCUMENTS) else document
    has_date_filter = bool(filters.get("from_date") or filters.get("to_date"))
    # Employees without an attempt have no attempt date to compare, so a date
    # range can only ever match actual attempts.
    include_pending = bool(cint(filters.get("include_pending", 1))) and not has_date_filter

    assignments = _fetch_assignments(document, filters)
    attempts = _fetch_attempts(document, filters)

    records = sorted({r["training_record"] for r in assignments + attempts if r.get("training_record")})
    quizzes = sorted({r["training_quiz"] for r in assignments + attempts if r.get("training_quiz")})

    rows = build_rows(
        assignments,
        attempts,
        trainers=_fetch_trainers(records),
        pass_marks=_fetch_pass_marks(quizzes),
        default_pass_mark=get_pass_percentage(),
        include_pending=include_pending,
    )

    if filters.get("result"):
        rows = [r for r in rows if r["result_state"] == filters["result"]]
        for i, row in enumerate(rows, start=1):
            row["sr_no"] = i
    return rows


def _fetch_assignments(document, filters):
    # Assigned employees are the Document Acknowledgement child rows of the
    # document's DMS Training Records -- Score History alone never lists an
    # employee who has not attempted the quiz.
    conditions = [
        "da.parenttype = 'DMS Training Record'",
        "tr.status != 'Cancelled'",
        "tr.document IS NOT NULL",
    ]
    values = {}
    if document:
        conditions.append("tr.document = %(document)s")
        values["document"] = document
    if filters.get("employee"):
        conditions.append("da.employee = %(employee)s")
        values["employee"] = filters["employee"]
    if filters.get("department"):
        conditions.append("COALESCE(emp.department, da.department) = %(department)s")
        values["department"] = filters["department"]

    return frappe.db.sql(
        f"""
        SELECT
            tr.name AS training_record,
            tr.document AS document,
            dl.title AS training_title,
            dl.training_quiz AS training_quiz,
            da.employee AS employee,
            COALESCE(emp.employee_name, da.employee_name) AS employee_name,
            COALESCE(emp.department, da.department) AS department,
            da.status AS status,
            da.completion_date AS completion_date,
            da.remarks AS remarks
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabDMS Training Record` tr ON tr.name = da.parent
        LEFT JOIN `tabDocument Library` dl ON dl.name = tr.document
        LEFT JOIN `tabEmployee` emp ON emp.name = da.employee
        WHERE {" AND ".join(conditions)}
        """,
        values,
        as_dict=True,
    )


def _fetch_attempts(document, filters):
    # Older history rows can have no `document`, so the document is resolved
    # through the training record first. Every attempt stays its own row.
    conditions = ["COALESCE(tr.document, sh.document) IS NOT NULL"]
    values = {}
    if document:
        conditions.append("COALESCE(tr.document, sh.document) = %(document)s")
        values["document"] = document
    if filters.get("employee"):
        conditions.append("sh.employee = %(employee)s")
        values["employee"] = filters["employee"]
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        values["department"] = filters["department"]
    if filters.get("from_date"):
        conditions.append("DATE(sh.recorded_on) >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("DATE(sh.recorded_on) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    return frappe.db.sql(
        f"""
        SELECT
            sh.name AS attempt_id,
            sh.training_record AS training_record,
            COALESCE(tr.document, sh.document) AS document,
            dl.title AS training_title,
            dl.training_quiz AS training_quiz,
            sh.employee AS employee,
            COALESCE(emp.employee_name, sh.employee_name) AS employee_name,
            emp.department AS department,
            sh.score AS score,
            sh.quiz_passed AS quiz_passed,
            sh.recorded_on AS recorded_on
        FROM `tabDMS Training Score History` sh
        LEFT JOIN `tabDMS Training Record` tr ON tr.name = sh.training_record
        LEFT JOIN `tabDocument Library` dl ON dl.name = COALESCE(tr.document, sh.document)
        LEFT JOIN `tabEmployee` emp ON emp.name = sh.employee
        WHERE {" AND ".join(conditions)}
        """,
        values,
        as_dict=True,
    )


def _fetch_trainers(records):
    """{training_record: trainer full name} -- the trainer of the latest
    training session, same selection as the Training Analytics table."""
    if not records:
        return {}

    latest = {}
    for s in frappe.db.sql(
        """
        SELECT training_record, trainer FROM `tabDMS Training Session`
        WHERE training_record IN %(records)s
        ORDER BY session_datetime, creation
        """,
        {"records": records},
        as_dict=True,
    ):
        latest[s.training_record] = s.trainer

    users = {t for t in latest.values() if t}
    names = {}
    if users:
        names = dict(
            frappe.get_all(
                "User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"], as_list=True
            )
        )
    return {rec: (names.get(user) or user) for rec, user in latest.items() if user}


def _fetch_pass_marks(quizzes):
    if not quizzes:
        return {}
    return dict(
        frappe.get_all(
            "DMS Quiz", filters={"name": ["in", quizzes]}, fields=["name", "pass_percentage"], as_list=True
        )
    )


def build_rows(assignments, attempts, trainers, pass_marks, default_pass_mark, include_pending=True):
    """One row per quiz attempt, plus one pending row for every assigned
    employee with no attempt. Pure function (no DB access) so the rules can
    be unit-tested."""
    assignment_by_key = {_key(a): a for a in assignments}

    attempts_by_key = {}
    for attempt in sorted(attempts, key=lambda a: (a.get("recorded_on") or datetime.datetime.min, a["attempt_id"])):
        attempts_by_key.setdefault(_key(attempt), []).append(attempt)

    rows = []
    for key in set(assignment_by_key) | set(attempts_by_key):
        document, training_record, _employee = key
        assignment = assignment_by_key.get(key)
        key_attempts = attempts_by_key.get(key, [])
        base = assignment or key_attempts[0]
        common = {
            "document": document,
            "training_record": training_record,
            "assessment_id": assessment_id_for(document),
            "training_title": base.get("training_title") or document,
            "employee_id": base["employee"],
            "employee_name": base.get("employee_name") or "",
            "department": base.get("department") or "Unassigned",
            "trainer": trainers.get(training_record) or "",
            "maximum_marks": MAXIMUM_MARKS,
            "pass_mark_pct": pass_marks.get(base.get("training_quiz")) or default_pass_mark,
        }

        if key_attempts:
            total = len(key_attempts)
            for number, attempt in enumerate(key_attempts, start=1):
                is_last = number == total
                completed = bool(assignment) and assignment["status"] == "Completed"
                rows.append(
                    {
                        **common,
                        "date_of_completion": (
                            assignment.get("completion_date") if completed and is_last else None
                        ),
                        "marks_obtained": attempt["score"],
                        "score_pct": attempt["score"],
                        "result": "Pass" if attempt["quiz_passed"] else "Fail",
                        "result_state": "Pass" if attempt["quiz_passed"] else "Fail",
                        "remarks": _join_remarks(
                            f"Attempt {number} of {total} ({_format_timestamp(attempt.get('recorded_on'))})",
                            assignment.get("remarks") if assignment else None,
                        ),
                        "_order": (attempt.get("recorded_on") or datetime.datetime.min, attempt["attempt_id"]),
                    }
                )
        elif include_pending and assignment:
            completed = assignment["status"] == "Completed"
            rows.append(
                {
                    **common,
                    "date_of_completion": assignment.get("completion_date") if completed else None,
                    "marks_obtained": None,
                    "score_pct": None,
                    "result": "",
                    "result_state": "Pending",
                    "remarks": _join_remarks(
                        "Pending - no assessment attempt recorded"
                        + (" (training completed)" if completed else ""),
                        assignment.get("remarks"),
                    ),
                    "_order": (datetime.datetime.min, 0),
                }
            )

    rows.sort(
        key=lambda r: (
            r["assessment_id"],
            r["employee_name"].lower(),
            r["employee_id"],
            r["training_record"] or "",
            r.pop("_order"),
        )
    )
    for i, row in enumerate(rows, start=1):
        row["sr_no"] = i
    return rows


def _key(row):
    return (row["document"], row.get("training_record"), row["employee"])


def _join_remarks(*parts):
    return "; ".join(p.strip() for p in parts if p and p.strip())


def _format_timestamp(value):
    if hasattr(value, "strftime"):
        return value.strftime("%d-%b-%Y %H:%M")
    return str(value or "")


def _get_summary(rows):
    if not rows:
        return []

    passed = sum(1 for r in rows if r["result_state"] == "Pass")
    failed = sum(1 for r in rows if r["result_state"] == "Fail")
    pending = {(r["document"], r["employee_id"]) for r in rows if r["result_state"] == "Pending"}
    return [
        {"value": passed + failed, "label": "Total Attempts", "datatype": "Int", "indicator": "blue"},
        {"value": passed, "label": "Passed", "datatype": "Int", "indicator": "green"},
        {
            "value": failed,
            "label": "Failed",
            "datatype": "Int",
            "indicator": "red" if failed else "green",
        },
        {
            "value": len(pending),
            "label": "Pending Employees",
            "datatype": "Int",
            "indicator": "orange" if pending else "green",
        },
    ]


# ── Excel export ────────────────────────────────────────────────────────────


def build_workbook(filters):
    """The filtered register as .xlsx bytes. A single document gets one sheet;
    All Documents gets a combined sheet plus one sheet per document."""
    import xlsxwriter

    document = filters.get("training_document")
    if not document:
        frappe.throw("Select a Training Document (or All Documents) to export.")

    rows = get_register_rows(filters)

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    formats = _make_formats(workbook)

    if document == ALL_DOCUMENTS:
        _write_sheet(workbook, formats, "All Documents", rows, renumber=False)
        by_document = {}
        for row in rows:
            by_document.setdefault(row["document"], []).append(row)
        for doc, doc_rows in by_document.items():
            _write_sheet(
                workbook, formats, assessment_id_for(doc), doc_rows, renumber=True,
                document_line=_document_line(doc, doc_rows[0]["training_title"]),
            )
    else:
        title = rows[0]["training_title"] if rows else frappe.db.get_value("Document Library", document, "title")
        _write_sheet(
            workbook, formats, assessment_id_for(document), rows, renumber=True,
            document_line=_document_line(document, title or document),
        )

    workbook.close()
    return buffer.getvalue()


def _document_line(document, title):
    return f"Training Document: {title} ({assessment_id_for(document)})"


def _make_formats(workbook):
    base = {"font_name": "Arial", "font_size": 10}
    return {
        "banner": workbook.add_format({**base, "bold": 1, "font_size": 12, "align": "center", "valign": "vcenter"}),
        "document": workbook.add_format({**base, "bold": 1, "align": "left", "valign": "vcenter"}),
        "header": workbook.add_format(
            {**base, "bold": 1, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": 1}
        ),
        "cell": workbook.add_format({**base, "border": 1, "valign": "top", "text_wrap": 1}),
        # numbers and real dates are centered; every table cell wraps text
        "number": workbook.add_format({**base, "border": 1, "valign": "top", "text_wrap": 1, "align": "center"}),
        "date": workbook.add_format(
            {**base, "border": 1, "valign": "top", "text_wrap": 1, "align": "center", "num_format": "d-mmm-yy"}
        ),
    }


def _write_sheet(workbook, formats, sheet_name, rows, renumber, document_line=None):
    from frappe.utils.xlsxutils import get_sanitized_sheet_name

    sheet = workbook.add_worksheet(get_sanitized_sheet_name(sheet_name))
    last_col = len(COLUMNS) - 1

    for col, (_label, _field, _type, _width, excel_width) in enumerate(COLUMNS):
        sheet.set_column(col, col, excel_width)

    sheet.merge_range(0, 0, 0, last_col, BANNER_LINES[0], formats["banner"])
    sheet.merge_range(1, 0, 1, last_col, BANNER_LINES[1], formats["banner"])
    sheet.set_row(0, 22)
    sheet.set_row(1, 20)
    next_row = 2
    if document_line:
        sheet.merge_range(next_row, 0, next_row, last_col, document_line, formats["document"])
        next_row += 1

    from quality_dms.dms import excel_style

    # sized to the wrapped header text, never shorter than 30 points
    sheet.set_row(
        next_row,
        excel_style.header_row_height([c[0] for c in COLUMNS], [c[4] for c in COLUMNS]),
    )
    for col, (label, *_rest) in enumerate(COLUMNS):
        sheet.write_string(next_row, col, label, formats["header"])

    for index, row in enumerate(rows, start=1):
        excel_row = next_row + index
        for col, (_label, fieldname, *_rest) in enumerate(COLUMNS):
            value = index if (renumber and fieldname == "sr_no") else row.get(fieldname)
            if value is None or value == "":
                sheet.write_blank(excel_row, col, None, formats["cell"])
            elif isinstance(value, (datetime.date, datetime.datetime)):
                sheet.write_datetime(excel_row, col, value, formats["date"])
            elif isinstance(value, (int, float)):
                sheet.write_number(excel_row, col, value, formats["number"])
            else:
                sheet.write_string(excel_row, col, str(value), formats["cell"])
