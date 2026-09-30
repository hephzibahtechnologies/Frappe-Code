import json
import os
import re
import shutil

import frappe
from frappe import _
from frappe.model.document import Document

SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")

RESERVED = frozenset({
	"www", "mail", "ftp", "admin", "api", "app", "assets",
	"static", "sbiqc", "localhost", "test", "staging", "prod",
})

ALWAYS_EXCLUDED = frozenset({"frappe", "sbiqc_provisioning", "crm_unify", "telephony"})


class Tenant(Document):

	def validate(self):
		self.subdomain = (self.subdomain or "").strip().lower()

		if not SUBDOMAIN_RE.match(self.subdomain):
			frappe.throw(
				_("Subdomain must be 3-32 chars: lowercase letters, digits, and hyphens. "
				  "Must start and end with a letter or digit.")
			)

		if self.subdomain in RESERVED:
			frappe.throw(_("'{0}' is a reserved subdomain.").format(self.subdomain))

		if not (self.admin_email or "").strip():
			# The tenant admin password is randomly generated and never surfaced
			# anywhere (see provisioner/engine.py) — without an email to deliver
			# the password-reset link to, the tenant would be permanently
			# unrecoverable, so this is now required rather than optional.
			frappe.throw(_("Admin Email is required — it's the only way the tenant admin receives access."))

		domain = (
			frappe.conf.get("tenant_domain_suffix")
			or ("sbiqc.com" if frappe.conf.get("is_production") else "localhost")
		)
		self.site_name = f"{self.subdomain}.{domain}"

		existing = frappe.db.get_value(
			"Tenant",
			{"subdomain": self.subdomain, "name": ("!=", self.name)},
			"name",
		)
		if existing:
			frappe.throw(_("Subdomain '{0}' is already taken.").format(self.subdomain))

		if not self.apps_to_install:
			frappe.throw(_("Select at least one app to install."))

		app_names = [row.app_name for row in self.apps_to_install]
		if "erpnext" not in app_names:
			row = self.append("apps_to_install", {})
			row.app_name = "erpnext"
			frappe.msgprint(_("ERPNext is always included — added automatically."))

		if not self.status:
			self.status = "Pending"

	def on_submit(self):
		self.db_set("status", "Provisioning")

		frappe.enqueue(
			"sbiqc_provisioning.provisioner.engine.provision_tenant",
			tenant_name=self.name,
			queue="long",
			timeout=1800,
			now=frappe.in_test,
			enqueue_after_commit=True,
		)
		frappe.msgprint(
			_("Provisioning job queued for {0}. Status will update automatically.").format(
				self.site_name
			),
			alert=True,
		)


@frappe.whitelist()
def get_installable_apps():
	"""Return list of apps available on the bench, excluding frappe and sbiqc_provisioning."""
	frappe.only_for("System Manager")
	bench_path = frappe.utils.get_bench_path()
	apps_file = os.path.join(bench_path, "sites", "apps.txt")

	if not os.path.exists(apps_file):
		apps_file = os.path.join(bench_path, "apps", "apps.txt")

	apps = []
	if os.path.exists(apps_file):
		with open(apps_file) as f:
			for line in f:
				app = line.strip()
				if app and app not in ALWAYS_EXCLUDED:
					apps.append(app)

	return sorted(apps)


@frappe.whitelist()
def get_provisioning_stats(offset=0, limit=20):
	frappe.only_for("System Manager")
	"""Return tenant counts by status for the dashboard."""
	offset = int(offset)
	limit = int(limit)
	stats = frappe.db.sql("""
		SELECT status, COUNT(*) as count
		FROM `tabTenant`
		GROUP BY status
	""", as_dict=True)

	result = {
		"total": 0,
		"Pending": 0, "Provisioning": 0, "Active": 0,
		"Error": 0, "Suspended": 0, "Terminated": 0,
	}
	for row in stats:
		result[row.status] = row["count"]
		result["total"] += row["count"]

	result["recent_logs"] = frappe.get_all(
		"Provisioning Log",
		fields=["name", "tenant", "site_name", "status", "current_step",
				"progress", "started_at", "completed_at"],
		order_by="creation desc",
		limit_page_length=10,
	)

	result["recent_tenants"] = frappe.get_all(
		"Tenant",
		fields=["name", "subdomain", "client_name", "site_name", "status",
				"plan", "provisioned_at", "admin_email"],
		order_by="creation desc",
		limit_page_length=limit,
		limit_start=offset,
	)

	for t in result["recent_tenants"]:
		t["db_name"] = ""
		if t.get("site_name"):
			cfg_path = os.path.join(
				frappe.utils.get_bench_path(), "sites", t["site_name"], "site_config.json"
			)
			if os.path.exists(cfg_path):
				try:
					with open(cfg_path) as f:
						cfg = json.load(f)
					t["db_name"] = cfg.get("db_name", "")
				except Exception:
					pass

	return result


@frappe.whitelist()
def delete_tenant(tenant_name):
	"""Delete a tenant, cancel if submitted, optionally drop its site."""
	import subprocess
	frappe.only_for("System Manager")
	tenant = frappe.get_doc("Tenant", tenant_name)
	site_name = tenant.site_name
	bench_path = frappe.utils.get_bench_path()

	if tenant.docstatus == 1:
		tenant.cancel()

	frappe.log_error(
		title=f"Tenant deleted: {tenant_name}",
		message=f"site={site_name}, deleted_by={frappe.session.user}, action=delete_tenant",
	)
	frappe.delete_doc("Tenant", tenant_name, force=True)

	site_path = os.path.join(bench_path, "sites", site_name)
	if os.path.isdir(site_path):
		import shutil as _shutil
		db_root_password = frappe.conf.get("db_root_password", "root")
		bench_bin = _shutil.which("bench") or os.path.join(bench_path, "env", "bin", "bench")
		try:
			result = subprocess.run(
				[bench_bin, "drop-site", site_name,
				 "--db-root-password", db_root_password, "--no-backup"],
				shell=False, cwd=bench_path,
				capture_output=True, text=True, timeout=120,
			)
			if result.returncode != 0:
				frappe.log_error(
					title=f"drop-site failed for {site_name}",
					message=result.stderr or result.stdout or "no output",
				)
		except Exception as e:
			frappe.log_error(title=f"drop-site launch error for {site_name}", message=str(e))

	frappe.db.commit()
	return {"status": "ok", "message": f"Tenant {tenant_name} deleted"}


@frappe.whitelist()
def update_tenant_apps(tenant_name, new_apps):
	"""Queue a provision_update job to install additional apps on an Active tenant."""
	frappe.only_for("System Manager")
	if isinstance(new_apps, str):
		new_apps = json.loads(new_apps)
	frappe.enqueue(
		"sbiqc_provisioning.provisioner.engine.provision_update",
		tenant_name=tenant_name,
		apps_to_add=new_apps,
		queue="long",
		timeout=1800,
		now=frappe.in_test,
	)
	return {"status": "queued", "apps": new_apps}


@frappe.whitelist()
def get_bench_health():
	"""Return health status of bench services."""
	import redis as _redis
	frappe.only_for("System Manager")
	bench_path = frappe.utils.get_bench_path()
	checks = []

	# Redis Cache
	try:
		_redis.Redis.from_url(frappe.conf.get("redis_cache", "redis://127.0.0.1:13000")).ping()
		checks.append({"name": "Redis Cache", "status": "ok"})
	except Exception as e:
		checks.append({"name": "Redis Cache", "status": "error", "detail": str(e)})

	# Redis Queue
	try:
		_redis.Redis.from_url(frappe.conf.get("redis_queue", "redis://127.0.0.1:11000")).ping()
		checks.append({"name": "Redis Queue", "status": "ok"})
	except Exception as e:
		checks.append({"name": "Redis Queue", "status": "error", "detail": str(e)})

	# MariaDB
	try:
		frappe.db.sql("SELECT 1")
		checks.append({"name": "MariaDB", "status": "ok"})
	except Exception as e:
		checks.append({"name": "MariaDB", "status": "error", "detail": str(e)})

	# Long Worker
	try:
		import rq as _rq
		conn = _redis.Redis.from_url(frappe.conf.get("redis_queue", "redis://127.0.0.1:11000"))
		q = _rq.Queue("long", connection=conn)
		workers = _rq.Worker.all(connection=conn)
		long_workers = [w for w in workers if any(q.name in str(qq) for qq in w.queues)]
		if long_workers:
			checks.append({"name": "Long Worker", "status": "ok", "detail": f"{len(long_workers)} worker(s)"})
		else:
			checks.append({"name": "Long Worker", "status": "warn", "detail": "No long queue worker found"})
	except Exception as e:
		checks.append({"name": "Long Worker", "status": "error", "detail": str(e)})

	# Disk Free
	try:
		free_bytes = shutil.disk_usage(bench_path).free
		free_gb = round(free_bytes / (1024 ** 3), 1)
		status = "ok" if free_gb >= 5 else "warn"
		checks.append({"name": "Disk Free", "status": status, "detail": f"{free_gb} GB"})
	except Exception as e:
		checks.append({"name": "Disk Free", "status": "error", "detail": str(e)})

	# Sites on bench
	try:
		sites_dir = os.path.join(bench_path, "sites")
		site_count = sum(
			1 for d in os.listdir(sites_dir)
			if os.path.isfile(os.path.join(sites_dir, d, "site_config.json"))
		)
		checks.append({"name": "Sites on Bench", "status": "ok", "detail": f"{site_count} site(s)"})
	except Exception as e:
		checks.append({"name": "Sites on Bench", "status": "error", "detail": str(e)})

	# Bench Apps
	try:
		apps_file = os.path.join(bench_path, "sites", "apps.txt")
		with open(apps_file) as f:
			apps = [l.strip() for l in f if l.strip()]
		app_labels = {"erpnext": "SBIQC", "quality_dms": "DMS"}
		apps = [app_labels.get(a, a) for a in apps]
		checks.append({"name": "Bench Apps", "status": "ok", "detail": ", ".join(apps)})
	except Exception as e:
		checks.append({"name": "Bench Apps", "status": "error", "detail": str(e)})

	overall = "error" if any(c["status"] == "error" for c in checks) else \
			  "warn"  if any(c["status"] == "warn"  for c in checks) else "ok"
	return {"checks": checks, "overall": overall}


@frappe.whitelist()
def get_provisioning_report():
	"""Return provisioning analytics for the Reports section."""
	frappe.only_for("System Manager")

	# Monthly counts — last 6 months
	monthly = frappe.db.sql("""
		SELECT DATE_FORMAT(creation, '%Y-%m') AS month, COUNT(*) AS count
		FROM `tabProvisioning Log`
		WHERE status = 'Completed'
		  AND creation >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
		GROUP BY month
		ORDER BY month
	""", as_dict=True)

	# Plan breakdown
	plans = frappe.db.sql("""
		SELECT plan, COUNT(*) AS count
		FROM `tabTenant`
		WHERE status != 'Terminated'
		GROUP BY plan
	""", as_dict=True)

	# Average duration in minutes
	avg_dur = frappe.db.sql("""
		SELECT AVG(TIMESTAMPDIFF(SECOND, started_at, completed_at)) AS avg_seconds
		FROM `tabProvisioning Log`
		WHERE status = 'Completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
	""", as_dict=True)
	avg_minutes = round((avg_dur[0].avg_seconds or 0) / 60, 1) if avg_dur else 0

	# Top 5 apps
	top_apps = frappe.db.sql("""
		SELECT app_name, COUNT(*) AS count
		FROM `tabTenant App`
		GROUP BY app_name
		ORDER BY count DESC
		LIMIT 5
	""", as_dict=True)

	return {
		"monthly": monthly,
		"plans": plans,
		"avg_provision_minutes": avg_minutes,
		"top_apps": top_apps,
	}


@frappe.whitelist()
def cancel_queued_job(log_name):
	"""Cancel a Queued provisioning job before it starts."""
	frappe.only_for("System Manager")
	log = frappe.get_doc("Provisioning Log", log_name)
	if log.status != "Queued":
		return {"status": "error", "message": "Job is not in Queued state"}
	log.db_set("status", "Failed")
	log.db_set("current_step", "Cancelled by user")
	log.db_set("completed_at", frappe.utils.now())
	tenant = frappe.get_doc("Tenant", log.tenant)
	if tenant.status == "Provisioning":
		tenant.db_set("status", "Pending")
	frappe.db.commit()
	return {"status": "ok"}


@frappe.whitelist()
def retry_provisioning(tenant_name):
	"""Re-queue a failed provisioning job."""
	frappe.only_for("System Manager")
	tenant = frappe.get_doc("Tenant", tenant_name)
	if tenant.docstatus != 1:
		frappe.throw("Tenant must be submitted before retrying.")
	tenant.db_set("status", "Provisioning")
	frappe.db.commit()
	frappe.enqueue(
		"sbiqc_provisioning.provisioner.engine.provision_tenant",
		tenant_name=tenant_name,
		queue="long",
		timeout=1800,
		now=frappe.in_test,
	)
	return {"status": "queued"}
