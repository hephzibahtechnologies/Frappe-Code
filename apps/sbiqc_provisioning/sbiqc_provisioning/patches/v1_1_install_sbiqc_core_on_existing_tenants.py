"""Install the mandatory apps (sbiqc_core) on every existing Active tenant site.

Runs once, when the control-plane site migrates. It only *queues* a background job, so
migrate stays fast: the job asks each tenant site which apps it has and queues a normal
provision_update (install, migrate, clear cache) for the ones missing sbiqc_core. Tenants
that already have it are left alone, so it is safe to run again.

New tenants get the app at provisioning time (engine.ALWAYS_INSTALL_APPS).
"""

import frappe


def execute():
	frappe.enqueue(
		"sbiqc_provisioning.provisioner.engine.ensure_required_apps_on_existing_tenants",
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		now=frappe.in_test,
	)
