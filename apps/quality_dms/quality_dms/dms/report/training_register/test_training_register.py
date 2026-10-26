import datetime

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from quality_dms.dms.report.training_register import training_register as tr

D = datetime.date


def _assignment(training_id="TRN-2026-0001", **overrides):
    row = {
        "training_id": training_id,
        "training_title": "Information Security Policy",
        "training_type": "Mandatory",
        "retraining_months": 12,
        "employee": "EMP-1",
        "department": "IT",
        "status": "Completed",
        "completion_date": D(2026, 1, 6),
        "assessment_score": 0,
        "quiz_passed": 0,
        "expires_on": D(2027, 1, 6),
        "remarks": None,
    }
    row.update(overrides)
    return row


def _sessions(training_id="TRN-2026-0001", trainer="HR Manager", total=1, attended=None):
    return {training_id: {"trainer": trainer, "total_sessions": total, "attended": attended or {}}}


class TestTrainingRegisterRollup(UnitTestCase):
    def test_one_row_per_training_with_sequential_sr_no(self):
        assignments = [
            _assignment("TRN-2026-0001", employee="EMP-1"),
            _assignment("TRN-2026-0001", employee="EMP-2"),
            _assignment("TRN-2026-0002", employee="EMP-1"),
        ]
        rows = tr.build_rows(assignments, {}, total_departments=5)
        self.assertEqual([r["training_id"] for r in rows], ["TRN-2026-0001", "TRN-2026-0002"])
        self.assertEqual([r["sr_no"] for r in rows], [1, 2])

    def test_department_single_multiple_and_all(self):
        one = tr.build_rows([_assignment(department="IT")], {}, total_departments=3)[0]
        self.assertEqual(one["department"], "IT")

        two = tr.build_rows(
            [_assignment(employee="E1", department="IT"), _assignment(employee="E2", department="Development")],
            {},
            total_departments=3,
        )[0]
        self.assertEqual(two["department"], "Development / IT")

        everyone = tr.build_rows(
            [_assignment(employee=f"E{i}", department=d) for i, d in enumerate(["IT", "HR", "QA"])],
            {},
            total_departments=3,
        )[0]
        self.assertEqual(everyone["department"], "All")

    def test_department_blank_when_assignees_have_none(self):
        row = tr.build_rows([_assignment(department=None)], {}, total_departments=3)[0]
        self.assertEqual(row["department"], "")

    def test_trainer_comes_from_latest_session(self):
        row = tr.build_rows([_assignment()], _sessions(trainer="System Admin"), 3)[0]
        self.assertEqual(row["trainer"], "System Admin")

    def test_trainer_blank_without_sessions(self):
        row = tr.build_rows([_assignment()], {}, 3)[0]
        self.assertEqual(row["trainer"], "")

    def test_attendance_is_average_across_assignees(self):
        assignments = [_assignment(employee="E1"), _assignment(employee="E2")]
        sessions = _sessions(total=4, attended={"E1": 4, "E2": 2})
        row = tr.build_rows(assignments, sessions, 3)[0]
        self.assertEqual(row["attendance_percentage"], 75.0)

    def test_attendance_none_without_sessions(self):
        row = tr.build_rows([_assignment()], {}, 3)[0]
        self.assertIsNone(row["attendance_percentage"])

    def test_assessment_blank_when_nobody_scored(self):
        row = tr.build_rows([_assignment(assessment_score=0)], {}, 3)[0]
        self.assertEqual(row["assessment_passed"], "")
        self.assertIsNone(row["assessment_score"])

    def test_assessment_y_when_all_scored_passed_and_average_ignores_unscored(self):
        assignments = [
            _assignment(employee="E1", assessment_score=80, quiz_passed=1),
            _assignment(employee="E2", assessment_score=90, quiz_passed=1),
            _assignment(employee="E3", assessment_score=0, quiz_passed=0),
        ]
        row = tr.build_rows(assignments, {}, 3)[0]
        self.assertEqual(row["assessment_passed"], "Y")
        self.assertEqual(row["assessment_score"], 85.0)

    def test_assessment_n_when_any_scored_failed(self):
        assignments = [
            _assignment(employee="E1", assessment_score=80, quiz_passed=1),
            _assignment(employee="E2", assessment_score=40, quiz_passed=0),
        ]
        self.assertEqual(tr.build_rows(assignments, {}, 3)[0]["assessment_passed"], "N")

    def test_status_completed_only_when_everyone_completed(self):
        done = tr.build_rows([_assignment(employee="E1"), _assignment(employee="E2")], {}, 3)[0]
        self.assertEqual(done["status"], "Completed")

        mixed = tr.build_rows(
            [_assignment(employee="E1"), _assignment(employee="E2", status="Pending", completion_date=None)],
            {},
            3,
        )[0]
        self.assertEqual(mixed["status"], "In Progress")

    def test_status_overdue_beats_in_progress_and_failed_beats_in_progress(self):
        overdue = tr.build_rows(
            [
                _assignment(employee="E1", status="Overdue", completion_date=None),
                _assignment(employee="E2", status="Pending", completion_date=None),
            ],
            {},
            3,
        )[0]
        self.assertEqual(overdue["status"], "Overdue")

        failed = tr.build_rows(
            [
                _assignment(employee="E1", status="Failed", completion_date=None),
                _assignment(employee="E2", status="Pending", completion_date=None),
            ],
            {},
            3,
        )[0]
        self.assertEqual(failed["status"], "Failed")

    def test_excused_assignees_do_not_block_completion(self):
        row = tr.build_rows(
            [_assignment(employee="E1"), _assignment(employee="E2", status="Excused", completion_date=None)],
            {},
            3,
        )[0]
        self.assertEqual(row["status"], "Completed")

    def test_date_of_completion_is_latest_and_blank_until_all_complete(self):
        done = tr.build_rows(
            [
                _assignment(employee="E1", completion_date=D(2026, 1, 6)),
                _assignment(employee="E2", completion_date=D(2026, 1, 9)),
            ],
            {},
            3,
        )[0]
        self.assertEqual(done["date_of_completion"], D(2026, 1, 9))

        pending = tr.build_rows(
            [_assignment(employee="E1"), _assignment(employee="E2", status="Pending", completion_date=None)],
            {},
            3,
        )[0]
        self.assertIsNone(pending["date_of_completion"])

    def test_next_due_date_is_earliest_expiry(self):
        row = tr.build_rows(
            [
                _assignment(employee="E1", expires_on=D(2027, 3, 1)),
                _assignment(employee="E2", expires_on=D(2027, 1, 6)),
                _assignment(employee="E3", expires_on=None),
            ],
            {},
            3,
        )[0]
        self.assertEqual(row["next_due_date"], D(2027, 1, 6))

    def test_remarks_combine_recurrence_and_distinct_assignee_remarks(self):
        row = tr.build_rows(
            [
                _assignment(employee="E1", remarks="SOC 2 awareness"),
                _assignment(employee="E2", remarks="SOC 2 awareness"),
                _assignment(employee="E3", remarks=""),
            ],
            {},
            3,
        )[0]
        self.assertEqual(row["remarks"], "Annual; SOC 2 awareness")

    def test_recurrence_labels(self):
        self.assertEqual(tr.recurrence_label(12), "Annual")
        self.assertEqual(tr.recurrence_label(6), "Half-yearly")
        self.assertEqual(tr.recurrence_label(3), "Quarterly")
        self.assertEqual(tr.recurrence_label(1), "Monthly")
        self.assertEqual(tr.recurrence_label(18), "Every 18 months")
        self.assertEqual(tr.recurrence_label(None), "")
        self.assertEqual(tr.recurrence_label(0), "")

    def test_no_assignments_gives_no_rows(self):
        self.assertEqual(tr.build_rows([], {}, 3), [])


class TestTrainingRegisterReport(IntegrationTestCase):
    """Read-only smoke tests against the real schema (no data is written)."""

    def test_columns_match_the_register_template(self):
        columns = tr.execute({})[0]
        self.assertEqual(
            [c["label"] for c in columns],
            [
                "Sr.No.", "Training ID", "Training Title", "Training Type", "Department",
                "Trainer", "Date of Completion", "Attendance (%)", "Assessment (Y/N)",
                "Average Assessment Score", "Status", "Next Due Date", "Remarks",
            ],
        )
        self.assertEqual(len({c["fieldname"] for c in columns}), 13)

    def test_query_runs_with_every_filter(self):
        frappe.set_user("Administrator")
        data = tr.execute(
            {
                "department": "Nonexistent Dept",
                "status": "Completed",
                "training_type": "Nonexistent Type",
                "from_date": "2020-01-01",
                "to_date": "2030-01-01",
            }
        )[1]
        self.assertEqual(data, [])

    def test_export_rows_use_report_headers(self):
        rows = tr.get_export_rows({})
        self.assertEqual(rows[0][0], "Sr.No.")
        self.assertEqual(len(rows[0]), 13)
