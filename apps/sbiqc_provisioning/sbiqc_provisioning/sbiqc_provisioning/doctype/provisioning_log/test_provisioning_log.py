# Copyright (c) 2026, SBIQC and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from sbiqc_provisioning.sbiqc_provisioning.doctype.provisioning_log.provisioning_log import (
	complete_log,
	create_log,
	update_log_step,
)


class IntegrationTestProvisioningLog(IntegrationTestCase):
	"""Tests for the Provisioning Log lifecycle helpers used by the engine —
	these run independently of the actual provisioning subprocess work."""

	def setUp(self):
		super().setUp()
		# Provisioning Log.tenant is a Link field validated against a real
		# Tenant record, so the helper functions under test need one to exist.
		# Subdomain must be unique per test method — rollback between tests
		# isn't guaranteed to happen before the next setUp runs.
		subdomain = f"logtest{abs(hash(self._testMethodName)) % 100000}"
		tenant = frappe.new_doc("Tenant")
		tenant.subdomain = subdomain
		tenant.client_name = "Log Test Co"
		tenant.plan = "Starter"
		tenant.admin_email = "logtest@example.com"
		tenant.append("apps_to_install", {"app_name": "erpnext"})
		tenant.insert(ignore_permissions=True)
		self.tenant_name = tenant.name
		self.site_name = tenant.site_name

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_create_log_starts_queued(self):
		log_name = create_log(self.tenant_name, self.site_name)
		log = frappe.get_doc("Provisioning Log", log_name)
		self.assertEqual(log.status, "Queued")
		self.assertEqual(log.progress, 0)
		self.assertEqual(log.tenant, self.tenant_name)
		self.assertEqual(log.site_name, self.site_name)

	def test_update_log_step_progresses_and_appends_html(self):
		log_name = create_log(self.tenant_name, self.site_name)
		update_log_step(log_name, "Creating site", 10)
		update_log_step(log_name, "Installing erpnext", 50)

		log = frappe.get_doc("Provisioning Log", log_name)
		self.assertEqual(log.current_step, "Installing erpnext")
		self.assertEqual(log.progress, 50)
		self.assertEqual(log.status, "Running")
		self.assertIsNotNone(log.started_at)
		self.assertIn("Creating site", log.steps_html)
		self.assertIn("Installing erpnext", log.steps_html)

	def test_complete_log_success(self):
		log_name = create_log(self.tenant_name, self.site_name)
		update_log_step(log_name, "Installing erpnext", 50)
		complete_log(log_name)

		log = frappe.get_doc("Provisioning Log", log_name)
		self.assertEqual(log.status, "Completed")
		self.assertEqual(log.progress, 100)
		self.assertIsNotNone(log.completed_at)
		self.assertIn("Provisioning Complete", log.steps_html)

	def test_complete_log_failure_keeps_partial_progress_and_records_error(self):
		log_name = create_log(self.tenant_name, self.site_name)
		update_log_step(log_name, "Installing erpnext", 40)
		complete_log(log_name, failed=True, error="Traceback: boom")

		log = frappe.get_doc("Provisioning Log", log_name)
		self.assertEqual(log.status, "Failed")
		# progress must reflect where it actually stopped, not jump to 100 on failure
		self.assertEqual(log.progress, 40)
		self.assertEqual(log.error_traceback, "Traceback: boom")
		self.assertIn("Provisioning Failed", log.steps_html)
