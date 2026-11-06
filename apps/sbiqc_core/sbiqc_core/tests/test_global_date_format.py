"""Global dd-MMM-yyyy date format (05-Nov-2026).

The capital-MMM spelling is deliberate: Frappe's own format_date() turns the
setting into a babel pattern with replace("mm", "MM"), which corrupts a
lowercase "dd-mmm-yyyy" (the stray "m" becomes *minutes* and it crashes).
"""

import os
import tempfile

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import format_date, format_datetime, getdate
from frappe.utils.dateutils import dateformats, parse_date, user_to_str
from frappe.utils.formatters import format_value

from sbiqc_core.date_format import NEW_DATE_FORMAT, NEW_DATE_FORMAT_STRPTIME, register_python_date_format

ORIGINAL_SYSTEM_OPTIONS = ["yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy", "dd.mm.yyyy", "mm/dd/yyyy", "mm-dd-yyyy"]


class TestPythonDateFormatTable(UnitTestCase):
    def test_new_format_is_registered_with_the_python_parser_table(self):
        self.assertEqual(NEW_DATE_FORMAT, "dd-MMM-yyyy")
        self.assertEqual(dateformats[NEW_DATE_FORMAT], "%d-%b-%Y")
        self.assertEqual(NEW_DATE_FORMAT_STRPTIME, "%d-%b-%Y")

    def test_registration_is_idempotent_and_never_overrides_an_existing_entry(self):
        register_python_date_format()
        register_python_date_format()
        self.assertEqual(list(dateformats).count(NEW_DATE_FORMAT), 1)

        original = dateformats[NEW_DATE_FORMAT]
        try:
            dateformats[NEW_DATE_FORMAT] = "%d-%b-%Y-custom"
            register_python_date_format()
            self.assertEqual(dateformats[NEW_DATE_FORMAT], "%d-%b-%Y-custom")
        finally:
            dateformats[NEW_DATE_FORMAT] = original

    def test_all_existing_python_formats_are_untouched(self):
        for name, strptime in {
            "yyyy-mm-dd": "%Y-%m-%d",
            "mm/dd/yyyy": "%m/%d/%Y",
            "mm-dd-yyyy": "%m-%d-%Y",
            "dd-mmm-yyyy": "%d-%b-%Y",
            "dd/mm/yyyy": "%d/%m/%Y",
            "dd.mm.yyyy": "%d.%m.%Y",
            "dd-mm-yyyy": "%d-%m-%Y",
        }.items():
            self.assertEqual(dateformats[name], strptime, name)


class TestGlobalDateFormat(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._saved_user_format = getattr(frappe.local, "user_date_format", None)

    def tearDown(self):
        frappe.local.user_date_format = self._saved_user_format
        super().tearDown()

    # ── the option itself ────────────────────────────────────────────────

    def test_option_is_added_after_the_six_existing_system_settings_options(self):
        options = frappe.get_meta("System Settings", cached=False).get_field("date_format").options.split("\n")
        self.assertEqual(options[:6], ORIGINAL_SYSTEM_OPTIONS)
        self.assertEqual(options[6:], [NEW_DATE_FORMAT])

    def test_option_is_added_to_the_language_field_too(self):
        options = frappe.get_meta("Language", cached=False).get_field("date_format").options.split("\n")
        self.assertEqual(options[0], "")  # the blank "use the system setting" choice stays first
        self.assertEqual(options[1:7], ORIGINAL_SYSTEM_OPTIONS)
        self.assertEqual(options[7:], [NEW_DATE_FORMAT])

    def test_the_app_never_changes_a_default_or_a_stored_format(self):
        # The site's own format is site data (the setup wizard writes it, an administrator may
        # change it), so asserting its value would fail on any site that opted in. What this app
        # guarantees is that it only extends the option list: no default, no value, new entry last.
        owned = frappe.get_all(
            "Property Setter",
            filters={"module": "SBIQC Core"},
            fields=["name", "doc_type", "field_name", "property"],
        )
        self.assertEqual(len(owned), 2, owned)
        for row in owned:
            self.assertEqual(row.field_name, "date_format", row)
            self.assertEqual(row.property, "options", row)
        self.assertFalse(
            frappe.db.exists(
                "Property Setter",
                {"doc_type": "System Settings", "field_name": "date_format", "property": "default"},
            )
        )
        options = frappe.get_meta("System Settings", cached=False).get_field("date_format").options.split("\n")
        self.assertEqual(options[-1], NEW_DATE_FORMAT)
        self.assertEqual(options[:-1], ORIGINAL_SYSTEM_OPTIONS)

    def test_property_setters_are_owned_by_the_sbiqc_core_module(self):
        for name in ("System Settings-date_format-options", "Language-date_format-options"):
            self.assertEqual(frappe.db.get_value("Property Setter", name, "module"), "SBIQC Core", name)

    # ── formatting (server side: forms, reports, print formats, emails) ──

    def test_dates_are_displayed_as_05_nov_2026(self):
        frappe.local.user_date_format = NEW_DATE_FORMAT
        self.assertEqual(format_date("2026-11-05"), "05-Nov-2026")
        self.assertEqual(format_date("2026-01-09"), "09-Jan-2026")
        self.assertEqual(format_datetime("2026-11-05 14:30:00"), "05-Nov-2026 14:30:00")
        self.assertEqual(format_value("2026-11-05", {"fieldtype": "Date"}), "05-Nov-2026")
        self.assertEqual(format_value("2026-11-05 14:30:00", {"fieldtype": "Datetime"}), "05-Nov-2026 14:30:00")

    def test_print_formats_and_emails_render_the_new_format(self):
        # Templates (print formats, email templates) reach the setting through
        # formatdate() and doc.get_formatted(). Note frappe.format_date in Jinja is
        # Frappe's *long* helper ("November 5, 2026") and ignores the setting by design.
        frappe.local.user_date_format = NEW_DATE_FORMAT
        self.assertEqual(frappe.render_template("{{ frappe.utils.formatdate('2026-11-05') }}", {}), "05-Nov-2026")
        todo = frappe.new_doc("ToDo")
        todo.date = "2026-11-05"
        self.assertEqual(frappe.render_template("{{ doc.get_formatted('date') }}", {"doc": todo}), "05-Nov-2026")

    def test_every_existing_format_still_displays_as_before(self):
        expected = {
            "yyyy-mm-dd": "2026-11-05",
            "dd-mm-yyyy": "05-11-2026",
            "dd/mm/yyyy": "05/11/2026",
            "dd.mm.yyyy": "05.11.2026",
            "mm/dd/yyyy": "11/05/2026",
            "mm-dd-yyyy": "11-05-2026",
        }
        for fmt, shown in expected.items():
            frappe.local.user_date_format = fmt
            self.assertEqual(format_date("2026-11-05"), shown, fmt)

    # ── manual entry / parsing ───────────────────────────────────────────

    def test_manual_entry_05_nov_2026_is_understood(self):
        frappe.local.user_date_format = NEW_DATE_FORMAT
        self.assertEqual(user_to_str("05-Nov-2026"), "2026-11-05")
        self.assertEqual(user_to_str("5-Nov-2026"), "2026-11-05")
        self.assertEqual(parse_date("05-Nov-2026"), "2026-11-05")
        self.assertEqual(getdate("05-Nov-2026").isoformat(), "2026-11-05")

    def test_nonsense_dates_are_still_rejected(self):
        frappe.local.user_date_format = NEW_DATE_FORMAT
        with self.assertRaises(ValueError):
            user_to_str("05-Foo-2026")
        with self.assertRaises(ValueError):
            user_to_str("2026-11-05")  # a different format is not silently accepted as this one

    def test_other_formats_still_parse_under_the_old_default(self):
        frappe.local.user_date_format = "dd-mm-yyyy"
        self.assertEqual(user_to_str("05-11-2026"), "2026-11-05")
        self.assertEqual(parse_date("05-Nov-2026"), "2026-11-05")  # also accepted, as before

    # ── data import ──────────────────────────────────────────────────────

    def test_data_import_reads_05_nov_2026_from_a_csv(self):
        from frappe.core.doctype.data_import.importer import Importer

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            # ToDo's date column is labelled "Due Date" (a wrong header would silently fall back
            # to the field default, today), and the dates differ from today and from each other.
            f.write(
                "Description,Due Date\n"
                "Import date probe,15-Dec-2026\n"
                "Second probe,05-Jan-2027\n"
                "Third probe,05-Nov-2026\n"
            )
            path = f.name
        try:
            # console=True is the importer's mode for reading a plain file path
            importer = Importer("ToDo", file_path=path, import_type="Insert New Records", console=True)
            payloads = importer.import_file.get_payloads_for_import()
            dates = [str(p.doc.get("date")) for p in payloads]
            self.assertEqual(dates, ["2026-12-15", "2027-01-05", "2026-11-05"])
        finally:
            os.unlink(path)

    # ── selecting the option as an administrator ─────────────────────────

    def test_system_settings_accepts_the_new_option_and_rejects_unknown_ones(self):
        original = frappe.db.get_single_value("System Settings", "date_format")
        try:
            settings = frappe.get_doc("System Settings")
            settings.date_format = NEW_DATE_FORMAT
            settings.save(ignore_permissions=True)
            frappe.local.user_date_format = None
            self.assertEqual(frappe.db.get_single_value("System Settings", "date_format"), NEW_DATE_FORMAT)
            self.assertEqual(format_date("2026-11-05"), "05-Nov-2026")

            settings = frappe.get_doc("System Settings")
            settings.date_format = "dd-mmm-yyyy"  # the lowercase spelling is not offered (it crashes Frappe)
            with self.assertRaises(frappe.ValidationError):
                settings.save(ignore_permissions=True)
        finally:
            frappe.db.rollback()
            settings = frappe.get_doc("System Settings")
            settings.date_format = original
            settings.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache()
            frappe.local.user_date_format = None
        self.assertEqual(frappe.db.get_single_value("System Settings", "date_format"), original)
