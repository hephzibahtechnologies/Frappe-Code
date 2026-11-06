import datetime
from io import BytesIO

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from quality_dms.dms.report.training_assessment_results_register import (
    training_assessment_results_register as reg,
)

D = datetime.date
DT = datetime.datetime

COLUMN_LABELS = [
    "Sr. No.", "Assessment ID", "Training Title", "Date of Completion", "Employee ID",
    "Employee Name", "Department", "Trainer", "Maximum Marks", "Marks Obtained",
    "Score (%)", "Pass Mark (%)", "Result (Pass/Fail)", "Remarks",
]


def _assignment(**overrides):
    row = {
        "document": "DOC-2099-0001",
        "training_title": "Policy A",
        "training_quiz": "QZ-A",
        "training_record": "TRN-2099-0001",
        "employee": "EMP-1",
        "employee_name": "Alice Test",
        "department": "IT",
        "status": "Pending",
        "completion_date": None,
        "remarks": None,
    }
    row.update(overrides)
    return row


def _attempt(attempt_id=1, **overrides):
    row = {
        "attempt_id": attempt_id,
        "document": "DOC-2099-0001",
        "training_title": "Policy A",
        "training_quiz": "QZ-A",
        "training_record": "TRN-2099-0001",
        "employee": "EMP-1",
        "employee_name": "Alice Test",
        "department": "IT",
        "score": 80.0,
        "quiz_passed": 1,
        "recorded_on": DT(2099, 1, 10, 9, 0),
    }
    row.update(overrides)
    return row


def _build(assignments=(), attempts=(), include_pending=True):
    return reg.build_rows(
        list(assignments),
        list(attempts),
        trainers={"TRN-2099-0001": "Trainer One"},
        pass_marks={"QZ-A": 70.0},
        default_pass_mark=80.0,
        include_pending=include_pending,
    )


class TestRegisterRules(UnitTestCase):
    def test_assessment_id_is_derived_from_the_stable_document_name(self):
        self.assertEqual(reg.assessment_id_for("DOC-2026-0004"), "QA-2026-0004")
        self.assertEqual(reg.assessment_id_for("DOC-2027-0004"), "QA-2027-0004")
        self.assertEqual(reg.assessment_id_for("CUSTOM-1"), "QA-CUSTOM-1")

    def test_attempt_row_pass_and_fail_follow_the_recorded_result(self):
        rows = _build(
            [_assignment(status="Completed", completion_date=D(2099, 1, 10))],
            [
                _attempt(1, score=50, quiz_passed=0, recorded_on=DT(2099, 1, 5, 10, 0)),
                _attempt(2, score=80, quiz_passed=1),
            ],
        )
        self.assertEqual([r["result"] for r in rows], ["Fail", "Pass"])
        self.assertEqual([r["score_pct"] for r in rows], [50, 80])
        self.assertEqual([r["marks_obtained"] for r in rows], [50, 80])
        self.assertTrue(all(r["maximum_marks"] == 100 for r in rows))

    def test_a_zero_score_attempt_is_a_real_fail_not_pending(self):
        row = _build([_assignment()], [_attempt(score=0, quiz_passed=0)])[0]
        self.assertEqual(row["result"], "Fail")
        self.assertEqual(row["score_pct"], 0)

    def test_attempts_are_never_merged_and_are_numbered_in_remarks(self):
        rows = _build(
            [_assignment()],
            [_attempt(1, recorded_on=DT(2099, 1, 5, 10, 0)), _attempt(2), _attempt(3, recorded_on=DT(2099, 1, 12, 8, 0))],
        )
        self.assertEqual(len(rows), 3)
        self.assertIn("Attempt 1 of 3", rows[0]["remarks"])
        self.assertIn("Attempt 3 of 3", rows[2]["remarks"])

    def test_completion_date_only_on_the_last_attempt_of_a_completed_assignment(self):
        rows = _build(
            [_assignment(status="Completed", completion_date=D(2099, 1, 10))],
            [_attempt(1, score=40, quiz_passed=0, recorded_on=DT(2099, 1, 5, 10, 0)), _attempt(2)],
        )
        self.assertIsNone(rows[0]["date_of_completion"])
        self.assertEqual(rows[1]["date_of_completion"], D(2099, 1, 10))

    def test_not_completed_assignment_has_no_completion_date_even_with_attempts(self):
        rows = _build([_assignment(status="In Progress")], [_attempt(score=40, quiz_passed=0)])
        self.assertIsNone(rows[0]["date_of_completion"])

    def test_employee_without_attempts_is_pending_with_blank_marks(self):
        row = _build([_assignment()], [])[0]
        self.assertEqual(row["result"], "")
        self.assertIsNone(row["marks_obtained"])
        self.assertIsNone(row["score_pct"])
        self.assertIsNone(row["date_of_completion"])
        self.assertEqual(row["maximum_marks"], 100)
        self.assertEqual(row["result_state"], "Pending")
        self.assertIn("Pending", row["remarks"])

    def test_pending_rows_can_be_excluded(self):
        self.assertEqual(_build([_assignment()], [], include_pending=False), [])

    def test_pass_mark_uses_quiz_value_then_settings_default(self):
        with_quiz = _build([_assignment()], [])[0]
        self.assertEqual(with_quiz["pass_mark_pct"], 70.0)
        no_quiz = _build([_assignment(training_quiz=None)], [])[0]
        self.assertEqual(no_quiz["pass_mark_pct"], 80.0)

    def test_attempt_without_a_current_assignment_is_still_listed(self):
        row = _build([], [_attempt()])[0]
        self.assertEqual(row["employee_id"], "EMP-1")
        self.assertEqual(row["result"], "Pass")

    def test_assignment_remarks_are_appended(self):
        row = _build([_assignment(remarks="Retake allowed")], [_attempt()])[0]
        self.assertIn("Retake allowed", row["remarks"])

    def test_each_document_gets_its_own_assessment_id_and_sr_no_is_sequential(self):
        rows = _build(
            [
                _assignment(document="DOC-2099-0002", training_record="TRN-2099-0002", employee="EMP-2"),
                _assignment(),
            ],
            [],
        )
        self.assertEqual([r["assessment_id"] for r in rows], ["QA-2099-0001", "QA-2099-0002"])
        self.assertEqual([r["sr_no"] for r in rows], [1, 2])

    def test_trainer_comes_from_the_training_record(self):
        self.assertEqual(_build([_assignment()], [])[0]["trainer"], "Trainer One")
        other = _build([_assignment(training_record="TRN-OTHER")], [])[0]
        self.assertEqual(other["trainer"], "")

    def test_summary_counts_attempts_passed_failed_and_pending(self):
        rows = _build(
            [_assignment(), _assignment(employee="EMP-2", employee_name="Bob Test")],
            [_attempt(1, score=40, quiz_passed=0, recorded_on=DT(2099, 1, 5, 10, 0)), _attempt(2)],
        )
        by_label = {s["label"]: s["value"] for s in reg._get_summary(rows)}
        self.assertEqual(by_label["Total Attempts"], 2)
        self.assertEqual(by_label["Passed"], 1)
        self.assertEqual(by_label["Failed"], 1)
        self.assertEqual(by_label["Pending Employees"], 1)


class TestRegisterAgainstDatabase(IntegrationTestCase):
    """Inserts synthetic rows with db_insert (no hooks, no commit). The test
    harness rolls the transaction back after every test, so nothing persists."""

    DOC_A = "DOC-2099-0001"
    DOC_B = "DOC-2099-0002"
    DOC_NO_TRAINING = "DOC-2099-0003"

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        # The transaction is only rolled back when the class finishes, so the
        # fixtures are created once and shared by the read-only tests below.
        if not frappe.db.exists("DMS Quiz", "QZ-TEST-A"):
            self._create_fixtures()

    def _create_fixtures(self):
        self._insert("DMS Quiz", name="QZ-TEST-A", title="QZ-TEST-A", pass_percentage=70)
        self._insert("Document Library", name=self.DOC_A, title="Zeta Test Policy", training_quiz="QZ-TEST-A")
        self._insert("Document Library", name=self.DOC_B, title="Alpha Test Policy")
        self._insert("Document Library", name=self.DOC_NO_TRAINING, title="Untrained Policy")
        for i, nm in enumerate(["Alice Test", "Bob Test", "Cara Test"], start=1):
            self._insert("Employee", name=f"TST-EMP-000{i}", employee_name=nm, department="Test Dept")

        self._insert("DMS Training Record", name="TRN-2099-0001", document=self.DOC_A, status="Assigned")
        self._insert("DMS Training Record", name="TRN-2099-0002", document=self.DOC_B, status="Assigned")
        self._ack("TRN-2099-0001", "TST-EMP-0001", status="Completed", completion_date="2099-01-10")
        self._ack("TRN-2099-0001", "TST-EMP-0002", status="Pending")
        self._ack("TRN-2099-0002", "TST-EMP-0001", status="Pending")
        self._ack("TRN-2099-0002", "TST-EMP-0003", status="Completed", completion_date="2099-02-01")

        self._attempt("TST-EMP-0001", "TRN-2099-0001", self.DOC_A, 50, 0, "2099-01-05 10:00:00")
        self._attempt("TST-EMP-0001", "TRN-2099-0001", self.DOC_A, 80, 1, "2099-01-10 09:00:00")
        self._attempt("TST-EMP-0003", "TRN-2099-0002", self.DOC_B, 90, 1, "2099-02-01 09:00:00")

        self._insert(
            "DMS Training Session", name="SESS-2099-0001", training_record="TRN-2099-0001",
            trainer="Administrator", session_datetime="2099-01-04 09:00:00", status="Completed",
        )

    # ── fixtures ──────────────────────────────────────────────────────────

    @staticmethod
    def _insert(doctype, **fields):
        doc = frappe.new_doc(doctype)
        doc.update(fields)
        doc.db_insert()
        return doc

    def _ack(self, record, employee, **fields):
        self._insert(
            "Document Acknowledgement", parent=record, parenttype="DMS Training Record",
            parentfield="employees", employee=employee, **fields,
        )

    def _attempt(self, employee, record, document, score, passed, recorded_on):
        self._insert(
            "DMS Training Score History", employee=employee, training_record=record,
            document=document, score=score, quiz_passed=passed, recorded_on=recorded_on,
        )

    def _rows(self, **filters):
        filters.setdefault("training_document", self.DOC_A)
        return reg.get_register_rows(filters)

    # ── dropdown ──────────────────────────────────────────────────────────

    def test_dropdown_lists_documents_with_training_and_excludes_others(self):
        options = {o["value"]: o["label"] for o in reg.get_training_documents()}
        self.assertIn("Zeta Test Policy", options[self.DOC_A])
        self.assertIn("QA-2099-0001", options[self.DOC_A])
        self.assertIn("Alpha Test Policy", options[self.DOC_B])
        self.assertNotIn(self.DOC_NO_TRAINING, options)

    # ── selecting a document ──────────────────────────────────────────────

    def test_selecting_a_document_never_shows_another_documents_records(self):
        rows = self._rows()
        self.assertEqual({r["document"] for r in rows}, {self.DOC_A})
        self.assertEqual({r["assessment_id"] for r in rows}, {"QA-2099-0001"})
        self.assertEqual({r["training_title"] for r in rows}, {"Zeta Test Policy"})
        other = self._rows(training_document=self.DOC_B)
        self.assertEqual({r["document"] for r in other}, {self.DOC_B})

    def test_assigned_employees_include_those_without_attempts(self):
        rows = self._rows()
        self.assertEqual({r["employee_id"] for r in rows}, {"TST-EMP-0001", "TST-EMP-0002"})
        bob = [r for r in rows if r["employee_id"] == "TST-EMP-0002"]
        self.assertEqual(len(bob), 1)
        self.assertEqual(bob[0]["result"], "")
        self.assertEqual(bob[0]["result_state"], "Pending")
        self.assertIsNone(bob[0]["score_pct"])
        self.assertIn("Pending", bob[0]["remarks"])

    def test_multiple_attempts_are_separate_rows_without_join_duplicates(self):
        alice = [r for r in self._rows() if r["employee_id"] == "TST-EMP-0001"]
        self.assertEqual([r["score_pct"] for r in alice], [50, 80])
        self.assertEqual([r["result"] for r in alice], ["Fail", "Pass"])
        self.assertEqual(len(self._rows()), 3)

    def test_completion_date_only_on_final_attempt_of_completed_assignment(self):
        alice = [r for r in self._rows() if r["employee_id"] == "TST-EMP-0001"]
        self.assertIsNone(alice[0]["date_of_completion"])
        self.assertEqual(alice[1]["date_of_completion"], D(2099, 1, 10))

    def test_employee_name_department_trainer_and_pass_mark_come_from_the_database(self):
        row = self._rows()[0]
        self.assertEqual(row["employee_name"], "Alice Test")
        self.assertEqual(row["department"], "Test Dept")
        self.assertEqual(row["trainer"], frappe.db.get_value("User", "Administrator", "full_name"))
        self.assertEqual(row["pass_mark_pct"], 70)

        from quality_dms.dms.doctype.training_settings.training_settings import get_pass_percentage

        b_row = self._rows(training_document=self.DOC_B)[0]
        self.assertEqual(b_row["pass_mark_pct"], get_pass_percentage())
        self.assertEqual(b_row["trainer"], "")

    # ── filters ───────────────────────────────────────────────────────────

    def test_date_filter_applies_to_attempt_dates_and_drops_pending_rows(self):
        rows = self._rows(from_date="2099-01-08")
        self.assertEqual([r["score_pct"] for r in rows], [80])
        rows = self._rows(to_date="2099-01-07")
        self.assertEqual([r["score_pct"] for r in rows], [50])

    def test_result_filter_pass_fail_pending(self):
        self.assertEqual([r["score_pct"] for r in self._rows(result="Pass")], [80])
        self.assertEqual([r["score_pct"] for r in self._rows(result="Fail")], [50])
        pending = self._rows(result="Pending")
        self.assertEqual([r["employee_id"] for r in pending], ["TST-EMP-0002"])

    def test_include_pending_checkbox_off_hides_employees_without_attempts(self):
        rows = self._rows(include_pending=0)
        self.assertEqual({r["employee_id"] for r in rows}, {"TST-EMP-0001"})

    def test_employee_and_department_filters(self):
        self.assertEqual({r["employee_id"] for r in self._rows(employee="TST-EMP-0002")}, {"TST-EMP-0002"})
        self.assertEqual(self._rows(department="No Such Dept"), [])

    def test_all_documents_returns_each_document_with_its_own_id(self):
        # All Documents also includes whatever real documents the site has.
        rows = [
            r
            for r in self._rows(training_document=reg.ALL_DOCUMENTS)
            if r["document"] in (self.DOC_A, self.DOC_B)
        ]
        ids = {(r["document"], r["assessment_id"]) for r in rows}
        self.assertEqual(ids, {(self.DOC_A, "QA-2099-0001"), (self.DOC_B, "QA-2099-0002")})
        self.assertEqual(len(rows), 5)

    def test_no_document_selected_returns_nothing_with_a_hint(self):
        columns, data, message, _chart, summary = reg.execute({})
        self.assertEqual(data, [])
        self.assertTrue(message)
        self.assertEqual(summary, [])

    def test_columns_are_the_14_template_headers_in_order(self):
        columns = reg.execute({"training_document": self.DOC_A})[0]
        self.assertEqual([c["label"] for c in columns], COLUMN_LABELS)

    # ── excel export ──────────────────────────────────────────────────────

    def _workbook(self, **filters):
        import openpyxl

        filters.setdefault("training_document", self.DOC_A)
        return openpyxl.load_workbook(BytesIO(reg.build_workbook(filters)))

    def test_excel_single_document_has_merged_banner_headers_and_filtered_rows(self):
        wb = self._workbook()
        self.assertEqual(wb.sheetnames, ["QA-2099-0001"])
        ws = wb.active
        merged = {str(r) for r in ws.merged_cells.ranges}
        self.assertIn("A1:N1", merged)
        self.assertIn("A2:N2", merged)
        self.assertEqual(ws["A1"].value, "Hephzibah Technologies Inc/Hephzibah Technologies India Private Ltd.")
        self.assertEqual(ws["A2"].value, "Training Quiz/Assessment Results Register")
        self.assertEqual(ws["A1"].alignment.horizontal, "center")

        header_row = next(r for r in range(1, 8) if ws.cell(r, 1).value == "Sr. No.")
        self.assertEqual([ws.cell(header_row, c).value for c in range(1, 15)], COLUMN_LABELS)
        self.assertEqual(ws.cell(header_row, 1).border.left.style, "thin")
        self.assertTrue(ws.cell(header_row, 1).font.b)
        self.assertGreaterEqual(ws.column_dimensions["C"].width, 20)

        body = [[ws.cell(r, c).value for c in range(1, 15)] for r in range(header_row + 1, ws.max_row + 1)]
        self.assertEqual(len(body), 3)
        self.assertEqual({row[1] for row in body}, {"QA-2099-0001"})
        self.assertEqual([row[0] for row in body], [1, 2, 3])

    def test_excel_all_documents_has_combined_sheet_and_one_sheet_per_document(self):
        wb = self._workbook(training_document=reg.ALL_DOCUMENTS)
        # Real documents on the site get their own sheets too.
        self.assertEqual(wb.sheetnames[0], "All Documents")
        self.assertIn("QA-2099-0001", wb.sheetnames)
        self.assertIn("QA-2099-0002", wb.sheetnames)
        self.assertEqual(len(wb.sheetnames), len(set(wb.sheetnames)))

        def body_rows(ws):
            header_row = next(r for r in range(1, 8) if ws.cell(r, 1).value == "Sr. No.")
            return [[ws.cell(r, c).value for c in range(1, 15)] for r in range(header_row + 1, ws.max_row + 1)]

        combined = body_rows(wb["All Documents"])
        self.assertEqual(len([r for r in combined if r[1] in ("QA-2099-0001", "QA-2099-0002")]), 5)
        per_doc = body_rows(wb["QA-2099-0002"])
        self.assertEqual({row[1] for row in per_doc}, {"QA-2099-0002"})
        self.assertEqual(per_doc[0][0], 1)

    def test_excel_requires_a_document_selection(self):
        with self.assertRaises(frappe.ValidationError):
            reg.build_workbook({})
