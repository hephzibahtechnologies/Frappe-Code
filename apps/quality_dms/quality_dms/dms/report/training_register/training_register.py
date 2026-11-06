import frappe

# Fieldnames of the two date columns that the paper register highlights yellow;
# shared with the report JS formatter and the Excel export.
HIGHLIGHT_FIELDS = ("date_of_completion", "next_due_date")

RECURRENCE_LABELS = {12: "Annual", 6: "Half-yearly", 3: "Quarterly", 1: "Monthly"}


def execute(filters=None):
    filters = filters or {}
    rows = get_register_rows(filters)
    return _get_columns(), rows, None, None, _get_summary(rows)


def _get_columns():
    return [
        {"label": "Sr.No.", "fieldname": "sr_no", "fieldtype": "Int", "width": 70},
        {
            "label": "Training ID",
            "fieldname": "training_id",
            "fieldtype": "Link",
            "options": "DMS Training Record",
            "width": 140,
        },
        {"label": "Training Title", "fieldname": "training_title", "fieldtype": "Data", "width": 240},
        {
            "label": "Training Type",
            "fieldname": "training_type",
            "fieldtype": "Link",
            "options": "Document Category",
            "width": 140,
        },
        # Data, not Link: a training spanning several departments is shown as a
        # joined list (or "All"), which is not a valid Department name.
        {"label": "Department", "fieldname": "department", "fieldtype": "Data", "width": 170},
        {"label": "Trainer", "fieldname": "trainer", "fieldtype": "Data", "width": 150},
        {"label": "Date of Completion", "fieldname": "date_of_completion", "fieldtype": "Date", "width": 130},
        {"label": "Attendance (%)", "fieldname": "attendance_percentage", "fieldtype": "Percent", "width": 120},
        {"label": "Assessment (Y/N)", "fieldname": "assessment_passed", "fieldtype": "Data", "width": 120},
        {"label": "Average Assessment Score", "fieldname": "assessment_score", "fieldtype": "Float", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": "Next Due Date", "fieldname": "next_due_date", "fieldtype": "Date", "width": 120},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
    ]


def get_register_rows(filters):
    assignments = _fetch_assignments(filters)
    training_ids = sorted({a["training_id"] for a in assignments})
    sessions = _fetch_session_data(training_ids)
    total_departments = frappe.db.count("Department", {"is_group": 0})

    rows = build_rows(assignments, sessions, total_departments)

    # Status is a rollup, so it is filtered after the rollup rather than in SQL.
    if filters.get("status"):
        rows = [r for r in rows if r["status"] == filters["status"]]
        for i, row in enumerate(rows, start=1):
            row["sr_no"] = i
    return rows


def get_export_rows(filters):
    """Header row followed by one list per register row, in column order."""
    columns = _get_columns()
    rows = get_register_rows(filters)
    data = [[c["label"] for c in columns]]
    for row in rows:
        data.append([_blank_if_none(row.get(c["fieldname"])) for c in columns])
    return data


def _blank_if_none(value):
    return "" if value is None else value


def _fetch_assignments(filters):
    # One row per employee assignment (Document Acknowledgement child row);
    # build_rows() rolls these up to one row per training.
    conditions = ["da.parenttype = 'DMS Training Record'", "tr.status != 'Cancelled'"]
    values = {}

    if filters.get("department"):
        conditions.append("da.department = %(department)s")
        values["department"] = filters["department"]

    if filters.get("training_type"):
        conditions.append("tr.category = %(training_type)s")
        values["training_type"] = filters["training_type"]

    if filters.get("from_date"):
        conditions.append("COALESCE(da.completion_date, DATE(da.creation)) >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("COALESCE(da.completion_date, DATE(da.creation)) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    return frappe.db.sql(
        f"""
        SELECT
            tr.name AS training_id,
            tr.document_title AS training_title,
            tr.category AS training_type,
            tr.retraining_months AS retraining_months,
            da.employee AS employee,
            da.department AS department,
            da.status AS status,
            da.completion_date AS completion_date,
            da.assessment_score AS assessment_score,
            da.quiz_passed AS quiz_passed,
            da.expires_on AS expires_on,
            da.remarks AS remarks
        FROM `tabDocument Acknowledgement` da
        INNER JOIN `tabDMS Training Record` tr ON tr.name = da.parent
        WHERE {" AND ".join(conditions)}
        ORDER BY tr.name, da.creation
        """,
        values,
        as_dict=True,
    )


def _fetch_session_data(training_ids):
    """{training_id: {trainer, total_sessions, attended: {employee: count}}}.

    Aggregated per training so a record with zero or many sessions never
    multiplies the assignment rows.
    """
    if not training_ids:
        return {}

    result = {tid: {"trainer": None, "total_sessions": 0, "attended": {}} for tid in training_ids}

    # Oldest first, so the latest session with a trainer wins.
    for s in frappe.db.sql(
        """
        SELECT training_record, trainer FROM `tabDMS Training Session`
        WHERE training_record IN %(ids)s
        ORDER BY session_datetime, creation
        """,
        {"ids": training_ids},
        as_dict=True,
    ):
        result[s.training_record]["total_sessions"] += 1
        if s.trainer:
            result[s.training_record]["trainer"] = s.trainer

    for a in frappe.db.sql(
        """
        SELECT s.training_record, att.employee, COUNT(DISTINCT s.name) AS attended
        FROM `tabDMS Training Session` s
        INNER JOIN `tabDMS Training Session Attendee` att
            ON att.parent = s.name AND att.parenttype = 'DMS Training Session'
        WHERE s.training_record IN %(ids)s AND att.attended = 1
        GROUP BY s.training_record, att.employee
        """,
        {"ids": training_ids},
        as_dict=True,
    ):
        result[a.training_record]["attended"][a.employee] = a.attended

    trainers = {d["trainer"] for d in result.values() if d["trainer"]}
    names = {}
    if trainers:
        names = dict(
            frappe.get_all(
                "User", filters={"name": ["in", list(trainers)]}, fields=["name", "full_name"], as_list=True
            )
        )
    for d in result.values():
        if d["trainer"]:
            d["trainer"] = names.get(d["trainer"]) or d["trainer"]

    return result


def build_rows(assignments, sessions, total_departments):
    """Roll employee assignments up to one register row per training.

    Pure function (no DB access) so the rollup rules can be unit-tested.
    """
    grouped = {}
    for a in assignments:
        grouped.setdefault(a["training_id"], []).append(a)

    rows = []
    for training_id, group in grouped.items():
        # Excused employees are not required to train, so they never block
        # completion or drag down the averages.
        active = [a for a in group if a["status"] != "Excused"] or group
        session = sessions.get(training_id) or {}
        first = group[0]

        scored = [a for a in active if a.get("assessment_score")]
        expiries = [a["expires_on"] for a in active if a.get("expires_on")]
        status = _rollup_status(active)

        rows.append(
            {
                "sr_no": len(rows) + 1,
                "training_id": training_id,
                "training_title": first["training_title"],
                "training_type": first["training_type"],
                "department": _department_label(
                    {a["department"] for a in group if a.get("department")}, total_departments
                ),
                "trainer": session.get("trainer") or "",
                "date_of_completion": _latest_completion(active) if status == "Completed" else None,
                "attendance_percentage": _average_attendance(active, session),
                "assessment_passed": (
                    "" if not scored else ("Y" if all(a.get("quiz_passed") for a in scored) else "N")
                ),
                "assessment_score": (
                    round(sum(a["assessment_score"] for a in scored) / len(scored), 1) if scored else None
                ),
                "status": status,
                "next_due_date": min(expiries) if expiries else None,
                "remarks": _remarks(first.get("retraining_months"), group),
            }
        )
    return rows


def recurrence_label(months):
    if not months:
        return ""
    return RECURRENCE_LABELS.get(months, f"Every {months} months")


def _department_label(departments, total_departments):
    if not departments:
        return ""
    if len(departments) > 1 and total_departments and len(departments) >= total_departments:
        return "All"
    return " / ".join(sorted(departments))


def _rollup_status(active):
    statuses = {a["status"] for a in active}
    if statuses == {"Completed"}:
        return "Completed"
    if statuses == {"Excused"}:
        return "Excused"
    if "Overdue" in statuses:
        return "Overdue"
    if "Failed" in statuses:
        return "Failed"
    return "In Progress"


def _latest_completion(active):
    dates = [a["completion_date"] for a in active if a.get("completion_date")]
    return max(dates) if dates else None


def _average_attendance(active, session):
    total = session.get("total_sessions") or 0
    if not total:
        return None
    attended = session.get("attended") or {}
    per_employee = [min(attended.get(a["employee"], 0), total) / total * 100 for a in active]
    return round(sum(per_employee) / len(per_employee), 1)


def _remarks(retraining_months, group):
    parts = [recurrence_label(retraining_months)]
    for a in group:
        text = (a.get("remarks") or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "; ".join(p for p in parts if p)


def _get_summary(rows):
    if not rows:
        return []

    def count(*statuses):
        return sum(1 for r in rows if r["status"] in statuses)

    overdue = count("Overdue")
    return [
        {"value": len(rows), "label": "Total Trainings", "datatype": "Int", "indicator": "blue"},
        {"value": count("Completed"), "label": "Completed", "datatype": "Int", "indicator": "green"},
        {"value": count("In Progress", "Failed"), "label": "In Progress", "datatype": "Int", "indicator": "orange"},
        {
            "value": overdue,
            "label": "Overdue",
            "datatype": "Int",
            "indicator": "red" if overdue else "green",
        },
    ]
