"""The mandatory apps (sbiqc_core) must be on every tenant site.

Pure unit tests: bench subprocesses, the job queue and the database are all mocked,
so nothing is installed anywhere and no Tenant record is created.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from sbiqc_provisioning.provisioner import engine

LIST_APPS_OUTPUT = (
	"\n"
	"frappe             16.23.0 UNVERSIONED\n"
	"erpnext            16.23.1 UNVERSIONED\n"
	"quality_dms        0.0.1   UNVERSIONED\n"
)


class TestRequiredAppsList(UnitTestCase):
	def test_sbiqc_core_is_mandatory(self):
		self.assertIn("sbiqc_core", engine.ALWAYS_INSTALL_APPS)

	def test_with_required_apps_adds_them_once_and_keeps_the_order(self):
		self.assertEqual(engine.with_required_apps(["quality_dms", "hrms"]), ["quality_dms", "hrms", "sbiqc_core"])
		self.assertEqual(engine.with_required_apps([]), ["sbiqc_core"])
		self.assertEqual(engine.with_required_apps(["sbiqc_core", "hrms"]), ["sbiqc_core", "hrms"])

	def test_install_order_is_erpnext_first_then_sorted_including_the_required_app(self):
		self.assertEqual(
			engine.get_install_order(["quality_dms", "crm_unify", "erpnext"]),
			["erpnext", "crm_unify", "quality_dms", "sbiqc_core"],
		)
		# a tenant that picked nothing still gets erpnext and the required app
		self.assertEqual(engine.get_install_order([]), ["erpnext", "sbiqc_core"])
		self.assertEqual(engine.get_install_order(["hrms"]), ["erpnext", "hrms", "sbiqc_core"])


class TestInstalledAppsParsing(UnitTestCase):
	def test_installed_apps_are_names_not_whole_list_apps_lines(self):
		completed = SimpleNamespace(returncode=0, stdout=LIST_APPS_OUTPUT, stderr="")
		with patch.object(engine.subprocess, "run", return_value=completed), patch.object(
			engine, "_bench_bin", return_value="bench"
		):
			self.assertEqual(engine._get_installed_apps("site1", "/bench"), {"frappe", "erpnext", "quality_dms"})

	def test_unreadable_site_gives_an_empty_set(self):
		completed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
		with patch.object(engine.subprocess, "run", return_value=completed), patch.object(
			engine, "_bench_bin", return_value="bench"
		):
			self.assertEqual(engine._get_installed_apps("site1", "/bench"), set())


def _tenants(*names):
	return [SimpleNamespace(name=f"T-{n}", site_name=f"{n}.example.test") for n in names]


class TestBackfillExistingTenants(UnitTestCase):
	def _run(self, installed_by_site, dry_run=False, tenants=None):
		tenants = tenants if tenants is not None else _tenants("a", "b", "c")
		with patch.object(engine.frappe, "get_all", return_value=tenants) as get_all, patch.object(
			engine, "_get_installed_apps", side_effect=lambda site, _bench: installed_by_site[site]
		), patch.object(engine.frappe, "enqueue") as enqueue, patch.object(
			engine.frappe.utils, "get_bench_path", return_value="/bench"
		):
			report = engine.ensure_required_apps_on_existing_tenants(dry_run=dry_run)
		return report, enqueue, get_all

	def test_only_tenants_missing_the_app_get_a_job(self):
		report, enqueue, get_all = self._run(
			{
				"a.example.test": {"frappe", "erpnext", "sbiqc_core"},  # already has it
				"b.example.test": {"frappe", "erpnext", "quality_dms"},  # missing
				"c.example.test": {"frappe", "erpnext"},  # missing
			}
		)
		self.assertEqual(enqueue.call_count, 2)
		queued = {c.kwargs["tenant_name"]: c.kwargs["apps_to_add"] for c in enqueue.call_args_list}
		self.assertEqual(queued, {"T-b": ["sbiqc_core"], "T-c": ["sbiqc_core"]})
		for c in enqueue.call_args_list:
			self.assertEqual(c.args[0], "sbiqc_provisioning.provisioner.engine.provision_update")
			self.assertEqual(c.kwargs["queue"], "long")
		self.assertEqual([r["tenant"] for r in report], ["T-a", "T-b", "T-c"])
		self.assertIn("already", report[0]["action"])
		self.assertIn("queued", report[1]["action"])
		get_all.assert_called_once()
		self.assertEqual(get_all.call_args.kwargs["filters"], {"status": "Active"})

	def test_running_it_twice_is_harmless(self):
		everyone_has_it = {f"{n}.example.test": {"frappe", "erpnext", "sbiqc_core"} for n in "abc"}
		_report, enqueue, _ = self._run(everyone_has_it)
		self.assertEqual(enqueue.call_count, 0)

	def test_dry_run_reports_but_queues_nothing(self):
		report, enqueue, _ = self._run(
			{f"{n}.example.test": {"frappe", "erpnext"} for n in "abc"}, dry_run=True
		)
		self.assertEqual(enqueue.call_count, 0)
		self.assertTrue(all("would install" in r["action"] for r in report))

	def test_a_site_whose_apps_cannot_be_read_is_skipped_not_guessed(self):
		report, enqueue, _ = self._run({"a.example.test": set()}, tenants=_tenants("a"))
		self.assertEqual(enqueue.call_count, 0)
		self.assertIn("skipped", report[0]["action"])

	def test_no_tenants_is_fine(self):
		report, enqueue, _ = self._run({}, tenants=[])
		self.assertEqual(report, [])
		self.assertEqual(enqueue.call_count, 0)


class TestProvisionUpdate(UnitTestCase):
	"""provision_update installs the mandatory app too, but never advertises it to the
	client or writes it into the tenant's selectable app list."""

	def _run_update(self, apps_to_add, installed):
		tenant = MagicMock()
		tenant.site_name = "t.example.test"
		tenant.apps_to_install = []
		with patch.object(engine.frappe, "init"), patch.object(engine.frappe, "connect"), patch.object(
			engine.frappe, "get_doc", return_value=tenant
		), patch.object(engine.frappe.utils, "get_bench_path", return_value="/bench"), patch.object(
			engine.frappe, "db"
		), patch.object(engine, "create_log", return_value="LOG"), patch.object(
			engine, "update_log_step"
		), patch.object(engine, "complete_log"), patch.object(engine, "_update_status"), patch.object(
			engine, "_clear_stale_locks"
		), patch.object(engine, "_get_installed_apps", return_value=set(installed)), patch.object(
			engine, "_install_app"
		) as install_app, patch.object(engine, "_run"), patch.object(
			engine, "_bench_bin", return_value="bench"
		), patch.object(engine, "_send_app_update_email") as email:
			engine.provision_update("T-1", apps_to_add)
		return tenant, install_app, email

	def test_the_required_app_is_installed_even_when_only_another_app_was_requested(self):
		_tenant, install_app, _email = self._run_update(["hrms"], installed={"frappe", "erpnext"})
		self.assertEqual([c.args[1] for c in install_app.call_args_list], ["hrms", "sbiqc_core"])

	def test_backfill_job_with_only_the_required_app_sends_no_client_email(self):
		_tenant, install_app, email = self._run_update(["sbiqc_core"], installed={"frappe", "erpnext"})
		self.assertEqual([c.args[1] for c in install_app.call_args_list], ["sbiqc_core"])
		email.assert_not_called()

	def test_client_email_lists_only_the_apps_the_client_asked_for(self):
		_tenant, _install_app, email = self._run_update(["hrms"], installed={"frappe", "erpnext"})
		email.assert_called_once()
		self.assertEqual(email.call_args.args[1], ["hrms"])

	def test_the_required_app_is_not_added_to_the_tenants_app_list(self):
		tenant, _install_app, _email = self._run_update(["hrms"], installed={"frappe", "erpnext"})
		appended = [c.args[1]["app_name"] for c in tenant.append.call_args_list]
		self.assertEqual(appended, ["hrms"])

	def test_nothing_is_reinstalled_when_the_site_already_has_everything(self):
		_tenant, install_app, email = self._run_update(
			["hrms"], installed={"frappe", "erpnext", "hrms", "sbiqc_core"}
		)
		install_app.assert_not_called()
		email.assert_not_called()
