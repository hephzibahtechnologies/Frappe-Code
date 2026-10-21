import frappe


def execute(filters=None):
    filters = filters or {}
    columns = _get_columns()
    data = _get_data(filters)
    summary = _get_summary(data)
    return columns, data, None, None, summary


def _get_columns():
    return [
        {
            "label": "Sr. No.",
            "fieldname": "sr_no",
            "fieldtype": "Int",
            "width": 70,
        },
        {
            "label": "Training ID",
            "fieldname": "training_id",
            "fieldtype": "Link",
            "options": "DMS Training Record",
            "width": 140,
        },
        {
            "label": "Training Title",
            "fieldname": "training_title",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Training Type",
            "fieldname": "training_type",
            "fieldtype": "Link",
            "options": "Document Category",
            "width": 140,
        },
        {
            "label": "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 150,
        },
        {
            "label": "Trainer",
            "fieldname": "trainer",
            "fieldtype": "Link",
            "options": "User",
            "width": 140,
        },
        {
            "label": "Date of completion",
            "fieldname": "date_of_completion",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Attendance (%)",
            "fieldname": "attendance_percentage",
            "fieldtype": "Percent",
            "width": 120,
        },
        {
            "label": "Assessment (Y/N)",
            "fieldname": "assessment_passed",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Average/ Assessment Score",
            "fieldname": "assessment_score",
            "fieldtype": "Float",
            "width": 150,
        },
        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": "Next Due Date",
            "fieldname": "next_due_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Remarks",
            "fieldname": "remarks",
            "fieldtype": "Small Text",
            "width": 180,
        },
        {
            "label": "Employee Signature",
            "fieldname": "employee_signature",
            "fieldtype": "Signature",
            "width": 160,
        },
    ]


def _get_data(filters):
    # Grain: one row per employee-training assignment (Document Acknowledgement
    # row), not per DMS Training Record. Trainer and Attendance (%) are
    # computed with scalar correlated subqueries, never a JOIN, specifically
    # to avoid multiplying each employee's row once per linked session (a
    # training record can have zero or many DMS Training Session rows).
    conditions = ["da.parenttype = 'DMS Training Record'"]
    values = {}

    if filters.get("department"):
        conditions.append("da.department = %(department)s")
        values["department"] = filters["department"]

    if filters.get("status"):
        conditions.append("da.status = %(status)s")
        values["status"] = filters["status"]

    if filters.get("from_date"):
        conditions.append("(da.completion_date >= %(from_date)s OR da.creation >= %(from_date)s)")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("(da.completion_date <= %(to_date)s OR da.creation <= %(to_date)s)")
        values["to_date"] = filters["to_date"]

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            tr.name AS training_id,
            tr.document_title AS training_title,
            tr.category AS training_type,
            da.department AS department,
            (
                SELECT s.trainer
                FROM `tabDMS Training Session` s
                WHERE s.training_record = tr.name
                ORDER BY s.session_datetime DESC, s.creation DESC
                LIMIT 1
            ) AS trainer,
            da.completion_date AS date_of_completion,
            (
                SELECT COUNT(DISTINCT s.name)
                FROM `tabDMS Training Session` s
                WHERE s.training_record = tr.name
            ) AS total_sessions,
            (
                SELECT COUNT(DISTINCT s.name)
                FROM `tabDMS Training Session` s
                INNER JOIN `tabDMS Training Session Attendee` att
                    ON att.parent = s.name AND att.parenttype = 'DMS Training Session'
                WHERE s.training_record = tr.name
                    AND att.employee = da.employee
                    AND att.attended = 1
            ) AS attended_sessions,
            da.assessment_score AS assessment_score,
            da.quiz_passed AS quiz_passed,
            da.status AS status,
            da.expires_on AS next_due_date,
            da.remarks AS remarks,
            da.e_signature AS employee_signature
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabDMS Training Record` tr ON tr.name = da.parent
        WHERE {where}
        ORDER BY da.creation DESC
        """,
        values,
        as_dict=True,
    )

    for i, row in enumerate(rows, start=1):
        row["sr_no"] = i

        total = row.pop("total_sessions", 0) or 0
        attended = row.pop("attended_sessions", 0) or 0
        row["attendance_percentage"] = round(attended / total * 100, 1) if total > 0 else None

        # assessment_score is a DB-level NOT NULL DEFAULT 0 column (verified
        # via SHOW COLUMNS) -- an un-assessed employee stores 0.0, never a
        # real NULL, so "is not None" can never be False here. The existing
        # Document Acknowledgement form already treats a falsy score as "not
        # assessed" (quiz_passed's own depends_on: eval:doc.assessment_score
        # hides that checkbox for a 0 or blank score) -- mirroring that exact
        # convention rather than inventing a different one. A legitimate
        # score of exactly 0/100 is indistinguishable from "not assessed"
        # under this rule, same as it already is in the native form.
        quiz_passed = row.pop("quiz_passed", 0)
        if row.get("assessment_score"):
            row["assessment_passed"] = "Y" if quiz_passed else "N"
        else:
            row["assessment_passed"] = ""

    return rows


def _get_summary(data):
    if not data:
        return []

    total = len(data)
    closed = sum(1 for r in data if r.get("status") == "Completed")
    in_progress = sum(1 for r in data if r.get("status") in ("Pending", "In Progress"))
    overdue = sum(1 for r in data if r.get("status") == "Overdue")
    compliance = round(closed / total * 100, 1) if total > 0 else 0.0

    return [
        {"value": total, "label": "Total Assignments", "datatype": "Int", "indicator": "blue"},
        {"value": in_progress, "label": "In Progress", "datatype": "Int", "indicator": "orange"},
        {
            "value": overdue,
            "label": "Overdue",
            "datatype": "Int",
            "indicator": "red" if overdue > 0 else "green",
        },
        {"value": closed, "label": "Completed", "datatype": "Int", "indicator": "green"},
        {
            "value": compliance,
            "label": "Compliance %",
            "datatype": "Percent",
            "indicator": "green" if compliance >= 80 else "red",
        },
    ]
