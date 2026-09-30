# Copyright (c) 2026, SBIQC and Contributors
# See license.txt
"""
Integration tests for the tenant provisioning engine.

All `bench`/subprocess-level work is mocked out — these tests exercise the
orchestration logic in engine.py (status transitions, log lifecycle, retry
idempotency, error handling), not actual site creation. Real end-to-end
provisioning was manually verified against a live bench during Phase 1/2
testing (see conversation history) since that requires an actual bench
environment CI doesn't have.

Two things this file works around, both discovered while writing these tests:

1. provision_tenant() calls frappe.init(site=...) + connect() at its very
   start (defensive, in case it's ever run in a fresh worker process) — this
   opens a brand-new DB connection, so any uncommitted work from the test's
   own transaction becomes invisible to it. Real commits are therefore
   unavoidable; cleanup uses explicit deletion instead of transaction
   rollback.

2. Tenant.on_submit() enqueues provision_tenant with
   enqueue_after_commit=True — correct in production, since the job only
   fires once the submit's own transaction (and the row lock it holds) has
   committed. But frappe.enqueue's `now=True` path (which fires whenever
   frappe.in_test is set) bypasses enqueue_after_commit entirely and calls
   provision_tenant() SYNCHRONOUSLY, from inside the still-open submit()
   transaction. Since provision_tenant() then opens a second connection and
   tries to lock the same Tenant row the first connection is still holding,
   calling tenant.submit() directly inside a test self-deadlocks (verified —
   it hangs on `SELECT ... FOR UPDATE` until the query timeout).
   These tests avoid that by committing the submitted state first and then
   calling engine.provision_tenant() directly — which is what actually runs
   in production once the real background worker picks the job up. The
   enqueue *wiring itself* (that on_submit queues the right job) is covered
   separately in test_on_submit_enqueues_provisioning, with frappe.enqueue
   mocked so the real synchronous path is never taken.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sbiqc_provisioning.provisioner import engine

TEST_SUBDOMAIN_PREFIX = "engtest-"


def _make_tenant(subdomain, admin_email="tenant-admin@example.com", apps=("erpnext",)):
	tenant = frappe.new_doc("Tenant")
	tenant.subdomain = subdomain
	tenant.client_name = f"{subdomain} Co"
	tenant.plan = "Starter"
	tenant.admin_email = admin_email
	for app in apps:
		tenant.append("apps_to_install", {"app_name": app})
	tenant.insert(ignore_permissions=True)
	frappe.db.commit()
	return tenant


def _submit_without_running_job(tenant):
	"""Mark the tenant Submitted the same way on_submit() would, and commit —
	mirroring the state a real background worker sees when it picks the job
	up post-commit — without actually going through frappe.enqueue's
	synchronous now=True path (see module docstring, point 2)."""
	with patch("frappe.enqueue"):
		tenant.submit()
	frappe.db.commit()
	tenant.reload()


class IntegrationTestProvisioningEngine(IntegrationTestCase):
	def tearDown(self):
		# Real commits happen inside provision_tenant (see module docstring),
		# so cleanup must explicitly delete rather than rely on rollback.
		# Provisioning Log is a standalone doctype (linked by field, not a
		# child table) so deleting the Tenant does not cascade-delete it —
		# without this it silently accumulates across every test run and can
		# later collide with a len(log) == 1 style assertion on a reused name.
		for log_name in frappe.get_all(
			"Provisioning Log", filters={"tenant": ["like", f"{TEST_SUBDOMAIN_PREFIX}%"]}, pluck="name"
		):
			frappe.delete_doc("Provisioning Log", log_name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Tenant", filters={"name": ["like", f"{TEST_SUBDOMAIN_PREFIX}%"]}, pluck="name"):
			try:
				tenant = frappe.get_doc("Tenant", name)
				if tenant.docstatus == 1:
					tenant.db_set("docstatus", 2)
				frappe.delete_doc("Tenant", name, force=True, ignore_permissions=True)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDown()

	def test_on_submit_enqueues_provisioning_after_commit(self):
		"""Wiring test: submitting a Tenant must queue provision_tenant on the
		'long' queue with enqueue_after_commit=True, and flip status to
		Provisioning — without actually running the job inline."""
		tenant = _make_tenant("engtest-enqueue")

		with patch("frappe.enqueue") as mock_enqueue:
			tenant.submit()

		mock_enqueue.assert_called_once()
		_, kwargs = mock_enqueue.call_args
		self.assertEqual(kwargs["tenant_name"], tenant.name)
		self.assertEqual(kwargs["queue"], "long")
		self.assertTrue(kwargs["enqueue_after_commit"])

		tenant.reload()
		self.assertEqual(tenant.status, "Provisioning")

	@patch.object(engine, "_send_welcome_email")
	@patch.object(engine, "_generate_admin_reset_link", return_value="http://fake/update-password?key=abc")
	@patch.object(engine, "_setup_local_routing")
	@patch("sbiqc_provisioning.provisioner.engine.seed_tenant")
	@patch.object(engine, "_install_app")
	@patch.object(engine, "_get_installed_apps", return_value=set())
	@patch.object(engine, "_clear_stale_locks")
	@patch.object(engine, "_run", return_value="")
	def test_provision_tenant_success_path(
		self, mock_run, mock_clear_locks, mock_installed, mock_install_app,
		mock_seed, mock_local_routing, mock_reset_link, mock_send_email,
	):
		"""Happy path: status walks Pending -> Provisioning -> Active, log completes,
		reset link is generated and handed to the welcome email — never a raw password."""
		tenant = _make_tenant("engtest-success")
		self.assertEqual(tenant.status, "Pending")

		_submit_without_running_job(tenant)
		self.assertEqual(tenant.status, "Provisioning")

		engine.provision_tenant(tenant.name)

		tenant.reload()
		self.assertEqual(tenant.status, "Active")
		self.assertIsNotNone(tenant.provisioned_at)
		self.assertEqual(tenant.error_log, None)

		mock_install_app.assert_called()
		mock_seed.assert_called_once()
		mock_reset_link.assert_called_once_with(tenant.site_name)
		mock_send_email.assert_called_once()
		# the welcome email must receive the reset link, never a plaintext password
		_, call_args, _ = mock_send_email.mock_calls[0]
		self.assertIn("http://fake/update-password?key=abc", call_args)

		log = frappe.get_all(
			"Provisioning Log", filters={"tenant": tenant.name}, fields=["status", "progress"]
		)
		self.assertEqual(len(log), 1)
		self.assertEqual(log[0].status, "Completed")
		self.assertEqual(log[0].progress, 100)

	@patch.object(engine, "_send_welcome_email")
	@patch.object(engine, "_generate_admin_reset_link", return_value=None)
	@patch.object(engine, "_setup_local_routing")
	@patch("sbiqc_provisioning.provisioner.engine.seed_tenant")
	@patch.object(engine, "_install_app", side_effect=RuntimeError("simulated install-app failure"))
	@patch.object(engine, "_get_installed_apps", return_value=set())
	@patch.object(engine, "_clear_stale_locks")
	@patch.object(engine, "_run", return_value="")
	def test_provision_tenant_failure_marks_error_and_records_traceback(
		self, mock_run, mock_clear_locks, mock_installed, mock_install_app,
		mock_seed, mock_local_routing, mock_reset_link, mock_send_email,
	):
		"""If a step raises, the tenant must land in Error with the traceback captured
		(never silently swallowed), and the log must be marked Failed."""
		tenant = _make_tenant("engtest-failure")
		_submit_without_running_job(tenant)

		with self.assertRaises(RuntimeError):
			engine.provision_tenant(tenant.name)

		tenant.reload()
		self.assertEqual(tenant.status, "Error")
		self.assertIn("simulated install-app failure", tenant.error_log)

		log = frappe.get_all(
			"Provisioning Log", filters={"tenant": tenant.name}, fields=["status", "error_traceback"]
		)
		self.assertEqual(len(log), 1)
		self.assertEqual(log[0].status, "Failed")
		self.assertIn("simulated install-app failure", log[0].error_traceback)

		# seed/routing/email must never run once an earlier step failed
		mock_seed.assert_not_called()
		mock_send_email.assert_not_called()

	@patch.object(engine, "_send_welcome_email")
	@patch.object(engine, "_generate_admin_reset_link", return_value="http://fake/update-password?key=xyz")
	@patch.object(engine, "_setup_local_routing")
	@patch("sbiqc_provisioning.provisioner.engine.seed_tenant")
	@patch.object(engine, "_install_app")
	@patch.object(engine, "_clear_stale_locks")
	@patch.object(engine, "_run", return_value="")
	def test_retry_skips_already_installed_apps(
		self, mock_run, mock_clear_locks, mock_install_app, mock_seed,
		mock_local_routing, mock_reset_link, mock_send_email,
	):
		"""Idempotent-resume behaviour: a retry after partial failure must not
		re-install apps that already succeeded. This is the actual safety net for
		a partial `bench new-site` + apps run — engine.py intentionally resumes
		rather than destructively deleting/recreating the site on retry (deleting
		on any failure would also nuke sites that are simply not yet reachable,
		e.g. during DNS propagation for the Phase 2 production health check)."""
		tenant = _make_tenant("engtest-retry", apps=["erpnext", "quality_dms"])
		_submit_without_running_job(tenant)

		with patch.object(engine, "_get_installed_apps", return_value={"erpnext"}):
			engine.provision_tenant(tenant.name)

		tenant.reload()
		self.assertEqual(tenant.status, "Active")
		# only the NOT-yet-installed app should have been installed
		installed_calls = [c.args[1] for c in mock_install_app.call_args_list]
		self.assertEqual(installed_calls, ["quality_dms"])

	def test_admin_password_is_random_not_hardcoded(self):
		"""Regression test for the Phase 1 security fix: no static default password."""
		tenant = _make_tenant("engtest-password")
		_submit_without_running_job(tenant)

		with patch.object(engine, "_run", return_value="") as mock_run, \
			patch.object(engine, "_clear_stale_locks"), \
			patch.object(engine, "_get_installed_apps", return_value=set()), \
			patch.object(engine, "_install_app"), \
			patch("sbiqc_provisioning.provisioner.engine.seed_tenant"), \
			patch.object(engine, "_setup_local_routing"), \
			patch.object(engine, "_generate_admin_reset_link", return_value="http://fake/link"), \
			patch.object(engine, "_send_welcome_email"):

			engine.provision_tenant(tenant.name)

			new_site_call = next(
				c for c in mock_run.call_args_list if "new-site" in c.args[0]
			)
			argv = new_site_call.args[0]
			admin_password = argv[argv.index("--admin-password") + 1]
			self.assertNotEqual(admin_password, "Admin@123")
			self.assertGreaterEqual(len(admin_password), 20)

	def test_redact_values_strips_secrets_from_output(self):
		text = "some stdout\nyour password is: hunter2\nmore text hunter2 again"
		redacted = engine._redact_values(text, ["hunter2"])
		self.assertNotIn("hunter2", redacted)
		self.assertIn("[REDACTED]", redacted)

	def test_production_routing_raises_on_unreachable_site(self):
		"""Phase 2: an unreachable site must fail provisioning loudly (visible as
		tenant status=Error) rather than silently marking the tenant Active."""
		with self.assertRaises(RuntimeError) as ctx:
			engine._setup_production_routing("this-host-does-not-exist.invalid")
		self.assertIn("not reachable", str(ctx.exception))

	def test_production_and_local_routing_are_mutually_exclusive(self):
		"""Guard against the local-dev-only /etc/hosts path ever running when
		is_production=True (Phase 2 requirement)."""
		tenant = _make_tenant("engtest-prodrouting")
		_submit_without_running_job(tenant)

		with patch.object(engine, "_send_welcome_email"), \
			patch.object(engine, "_generate_admin_reset_link", return_value=None), \
			patch.object(engine, "_setup_production_routing") as mock_prod_routing, \
			patch.object(engine, "_setup_local_routing") as mock_local_routing, \
			patch("sbiqc_provisioning.provisioner.engine.seed_tenant"), \
			patch.object(engine, "_install_app"), \
			patch.object(engine, "_get_installed_apps", return_value=set()), \
			patch.object(engine, "_clear_stale_locks"), \
			patch.object(engine, "_run", return_value=""), \
			patch.dict(frappe.conf, {"is_production": True}):

			engine.provision_tenant(tenant.name)

			mock_prod_routing.assert_called_once()
			mock_local_routing.assert_not_called()
