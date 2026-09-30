# Copyright (c) 2026, SBIQC and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class IntegrationTestTenant(IntegrationTestCase):
	"""Tests for Tenant.validate() — subdomain rules, forced erpnext inclusion,
	and the Phase 1 admin_email requirement (load-bearing for the password fix:
	without an email, a randomly-generated admin password would be unrecoverable)."""

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _new_tenant(self, **overrides):
		tenant = frappe.new_doc("Tenant")
		tenant.subdomain = overrides.get("subdomain", "validtest")
		tenant.client_name = overrides.get("client_name", "Valid Test Co")
		tenant.plan = overrides.get("plan", "Starter")
		if "admin_email" in overrides:
			tenant.admin_email = overrides["admin_email"]
		for app in overrides.get("apps", ["erpnext"]):
			tenant.append("apps_to_install", {"app_name": app})
		return tenant

	def test_admin_email_is_required(self):
		tenant = self._new_tenant(subdomain="noemailtest")
		with self.assertRaises(frappe.ValidationError):
			tenant.insert(ignore_permissions=True)

	def test_valid_tenant_with_admin_email_inserts(self):
		tenant = self._new_tenant(subdomain="hasemailtest", admin_email="a@example.com")
		tenant.insert(ignore_permissions=True)
		self.assertEqual(tenant.site_name, "hasemailtest.localhost")
		self.assertEqual(tenant.status, "Pending")

	def test_reserved_subdomain_rejected(self):
		tenant = self._new_tenant(subdomain="admin", admin_email="a@example.com")
		with self.assertRaises(frappe.ValidationError):
			tenant.insert(ignore_permissions=True)

	def test_invalid_subdomain_format_rejected(self):
		for bad in ("-leadinghyphen", "trailinghyphen-", "ab", "Has_Underscore"):
			tenant = self._new_tenant(subdomain=bad, admin_email="a@example.com")
			with self.assertRaises(frappe.ValidationError):
				tenant.insert(ignore_permissions=True)

	def test_erpnext_auto_added_when_missing(self):
		tenant = self._new_tenant(
			subdomain="autoerpnext", admin_email="a@example.com", apps=["quality_dms"]
		)
		tenant.insert(ignore_permissions=True)
		app_names = {row.app_name for row in tenant.apps_to_install}
		self.assertIn("erpnext", app_names)
		self.assertIn("quality_dms", app_names)

	def test_duplicate_subdomain_rejected(self):
		tenant1 = self._new_tenant(subdomain="duptest", admin_email="a@example.com")
		tenant1.insert(ignore_permissions=True)

		# Tenant.autoname = "field:subdomain" makes `name` the subdomain itself,
		# so the DB's own primary-key constraint fires as frappe.NameError
		# before validate()'s explicit duplicate-subdomain check is ever reached
		# (that check is effectively dead code) — either way, the outcome this
		# test cares about is that a second identical subdomain is rejected.
		tenant2 = self._new_tenant(subdomain="duptest", admin_email="b@example.com")
		with self.assertRaises(frappe.NameError):
			tenant2.insert(ignore_permissions=True)
