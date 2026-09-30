"""
engine.py — Multi-tenant provisioning engine for SBIQ.

Environment-aware: reads `is_production` from frappe.conf (default False).
- Local mode: creates site, installs apps, updates /etc/hosts
- Production mode: creates site, installs apps, writes Nginx conf (stubbed)
"""

import hashlib
import os
import secrets
import shutil
import subprocess
import traceback
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import random_string

from sbiqc_provisioning.provisioner.seeder import seed_tenant


def _bench_bin():
    """Return the absolute path to the bench binary (works even when ~/.local/bin is not in PATH)."""
    found = shutil.which("bench")
    if found:
        return found
    import pwd
    try:
        real_home = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        real_home = os.path.expanduser("~")
    candidates = [
        os.path.join(real_home, ".local", "bin", "bench"),
        "/usr/local/bin/bench",
        os.path.join(frappe.utils.get_bench_path(), "env", "bin", "bench"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "bench"  # last-resort fallback
from sbiqc_provisioning.sbiqc_provisioning.doctype.provisioning_log.provisioning_log import (
	complete_log,
	create_log,
	update_log_step,
)


def provision_tenant(tenant_name):
	"""Main entry point — called by the background job queue."""
	frappe.init(site=frappe.local.site)
	frappe.connect()

	tenant = frappe.get_doc("Tenant", tenant_name)
	bench_path = frappe.utils.get_bench_path()
	is_production = frappe.conf.get("is_production", False)
	site_name = tenant.site_name
	db_root_password = frappe.conf.get("db_root_password", "root")
	# Generated fresh per tenant — never logged, never emailed. `bench new-site`
	# needs a real password to seed the site's Administrator account, but the
	# tenant admin only ever receives a one-time password-reset link (see
	# _generate_admin_reset_link below), so this value is discarded immediately
	# after site creation.
	admin_password = secrets.token_urlsafe(24)

	log_name = create_log(tenant_name, site_name)

	try:
		_update_status(tenant, "Provisioning")
		update_log_step(log_name, "Initializing", 5)

		# Step 1: Create the new site (skip only if the site dir AND its DB exist)
		site_path = os.path.join(bench_path, "sites", site_name)
		site_cfg_path = os.path.join(site_path, "site_config.json")
		site_fully_created = False
		if os.path.isdir(site_path) and os.path.exists(site_cfg_path):
			try:
				import json as _json
				with open(site_cfg_path) as _f:
					_scfg = _json.load(_f)
				import subprocess as _sp
				_chk = _sp.run(
					[_bench_bin(), "--site", site_name, "list-apps"],
					cwd=bench_path, capture_output=True, text=True, timeout=30,
				)
				site_fully_created = _chk.returncode == 0
			except Exception:
				site_fully_created = False
		if site_fully_created:
			update_log_step(log_name, f"Site {site_name} already exists — reusing", 25)
		else:
			if os.path.isdir(site_path):
				import shutil as _shutil
				_shutil.rmtree(site_path)  # remove incomplete dir so new-site starts clean
			update_log_step(log_name, "Creating site: " + site_name, 10)
			_run(
				[
					_bench_bin(), "new-site", site_name,
					"--mariadb-root-password", db_root_password,
					"--admin-password", admin_password,
				],
				cwd=bench_path,
				timeout=600,
				secret_values=(db_root_password, admin_password),
			)
			update_log_step(log_name, "Site created", 25)
		frappe.publish_progress(25, title=_("Provisioning {0}").format(site_name))

		# Step 2: Install apps — skip already-installed, erpnext first
		app_names = [row.app_name for row in tenant.apps_to_install]
		if "erpnext" in app_names:
			app_names.remove("erpnext")
		install_order = ["erpnext"] + sorted(app_names)

		_clear_stale_locks(site_name, bench_path)
		already_installed = _get_installed_apps(site_name, bench_path)
		to_install = [a for a in install_order if a not in already_installed]

		if not to_install:
			update_log_step(log_name, "All apps already installed", 65)
		else:
			for i, app in enumerate(to_install):
				update_log_step(log_name, f"Installing {app}", 25 + int((i + 1) / len(to_install) * 40))
				_install_app(site_name, app, bench_path)
				pct = 25 + int((i + 1) / len(to_install) * 40)
				frappe.publish_progress(pct, title=_("Installing {0}").format(app))
			update_log_step(log_name, "All apps installed", 65)

		# Step 3: Seed company defaults
		update_log_step(log_name, "Seeding company defaults", 70)
		seed_tenant(
			site_name=site_name,
			client_name=tenant.client_name,
			plan=tenant.plan,
			currency=getattr(tenant, "currency", "INR") or "INR",
			timezone=getattr(tenant, "timezone", "Asia/Kolkata") or "Asia/Kolkata",
			admin_email=getattr(tenant, "admin_email", None) or None,
		)
		frappe.publish_progress(75, title=_("Seeding defaults"))
		update_log_step(log_name, "Defaults configured", 75)

		# Step 4: Routing — environment switch
		update_log_step(log_name, "Configuring routing", 80)
		if is_production:
			_setup_production_routing(site_name)
		else:
			_setup_local_routing(site_name)
		frappe.publish_progress(90, title=_("Configuring routing"))
		update_log_step(log_name, "Routing configured", 90)

		# Step 5: Clear cache
		update_log_step(log_name, "Clearing cache", 95)
		_run([_bench_bin(), "--site", site_name, "clear-cache"], cwd=bench_path)

		# Step 6: Mark active
		_update_status(tenant, "Active")
		tenant.reload()
		tenant.db_set("provisioned_at", datetime.now())
		frappe.db.commit()

		# Step 7: Send welcome email (non-blocking) — a one-time password-reset
		# link, never the raw password (see _generate_admin_reset_link).
		reset_link = _generate_admin_reset_link(site_name)
		_send_welcome_email(tenant, reset_link)

		frappe.publish_progress(100, title=_("Done"))
		complete_log(log_name)

	except Exception:
		tb = traceback.format_exc()
		_update_status(tenant, "Error")
		tenant.reload()
		tenant.db_set("error_log", tb[:10000])
		frappe.db.commit()
		frappe.log_error(
			title=f"Tenant provisioning failed: {tenant_name}",
			message=tb,
		)
		complete_log(log_name, failed=True, error=tb)
		raise


def _update_status(tenant, status):
	tenant.reload()
	tenant.db_set("status", status)
	frappe.db.commit()


def _generate_admin_reset_link(site_name):
	"""Generate a one-time password-reset link for the new site's Administrator
	account, so the tenant admin sets their own password instead of the raw
	value ever being logged, emailed, or displayed.

	core's whitelisted `reset_password()` explicitly refuses to act on the
	Administrator account (see frappe/core/doctype/user/user.py), so the
	reset key is set directly here, the same way update_password.py validates
	it (sha256-hashed key + last_reset_password_key_generated_on timestamp).

	Runs against the tenant's own site DB, then restores the original site
	context — failure here must never crash provisioning, since the tenant
	site is already fully set up at this point.
	"""
	original_site = frappe.local.site
	try:
		frappe.init(site=site_name)
		frappe.connect()
		key = random_string(32)
		hashed_key = hashlib.sha256(key.encode()).hexdigest()
		frappe.db.set_value("User", "Administrator", "reset_password_key", hashed_key)
		frappe.db.set_value("User", "Administrator", "last_reset_password_key_generated_on", datetime.now())
		frappe.db.commit()
		is_production = frappe.conf.get("is_production", False)
		port = "" if is_production else ":8000"
		return f"http://{site_name}{port}/update-password?key={key}"
	except Exception:
		frappe.logger().warning(
			f"Could not generate admin reset link for {site_name}: {frappe.get_traceback()}"
		)
		return None
	finally:
		frappe.init(site=original_site)
		frappe.connect()


def _send_welcome_email(tenant, reset_link=None):
	"""Send a welcome email to the tenant admin after successful provisioning.
	Email failure never raises — provisioning is already complete at this point.
	"""
	if not getattr(tenant, "admin_email", None):
		return

	try:
		is_production = frappe.conf.get("is_production", False)
		port = "" if is_production else ":8000"
		site_url = f"http://{tenant.site_name}{port}"

		subject = f"Your SBIQ instance is ready — {tenant.client_name}"

		if reset_link:
			reset_block = f"""
    <div style="margin:20px 0;padding:14px 16px;background:#ede9fe;border-radius:6px;font-size:13px;color:#4c1d95;">
      <strong>Set your password to log in for the first time</strong><br/>
      This link is valid once and expires after a limited time.
      <div style="margin-top:12px;">
        <a href="{reset_link}" style="display:inline-block;background:#6366f1;color:#fff;
           padding:10px 18px;border-radius:6px;font-weight:600;text-decoration:none;font-size:13px;">
          Set Your Password
        </a>
      </div>
    </div>"""
			reset_missing_note = ""
		else:
			# Reset-link generation failed (see _generate_admin_reset_link) —
			# provisioning already succeeded, so don't block on this, but be
			# explicit rather than silently omitting how to log in.
			reset_block = """
    <div style="margin:20px 0;padding:14px 16px;background:#fef2f2;border-radius:6px;font-size:13px;color:#991b1b;">
      <strong>Password setup link unavailable</strong><br/>
      Contact your administrator to have your password reset manually.
    </div>"""
			reset_missing_note = " (or contact your administrator if you didn't receive a working link)"

		message = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1f2937;">
  <div style="background:#6366f1;padding:28px 32px;border-radius:8px 8px 0 0;">
    <h1 style="color:#fff;font-size:22px;margin:0;">Welcome to SBIQ, {tenant.client_name}!</h1>
    <p style="color:#e0e7ff;margin:8px 0 0;font-size:14px;">Your SBIQ instance is live and ready to use.</p>
  </div>
  <div style="background:#f9fafb;padding:28px 32px;border:1px solid #e5e7eb;border-top:0;">
    <h2 style="font-size:16px;color:#374151;margin:0 0 16px;">Your login details</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr>
        <td style="padding:8px 0;color:#6b7280;width:140px;">Site URL</td>
        <td style="padding:8px 0;"><a href="{site_url}" style="color:#6366f1;font-weight:600;">{site_url}</a></td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Login Email</td>
        <td style="padding:8px 0;font-weight:600;">{tenant.admin_email}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Plan</td>
        <td style="padding:8px 0;">{tenant.plan or "Standard"}</td>
      </tr>
    </table>
    {reset_block}
    <h2 style="font-size:16px;color:#374151;margin:20px 0 10px;">Getting started</h2>
    <ol style="font-size:14px;color:#374151;line-height:1.8;padding-left:18px;margin:0;">
      <li>Set your password using the button above{reset_missing_note}</li>
      <li>Complete the <strong>Setup Wizard</strong> to configure your company</li>
      <li>Invite your team members from <em>Settings &rarr; Users</em></li>
    </ol>
    <div style="margin-top:28px;padding-top:20px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
      Powered by <strong>SBIQ</strong><br/>
      This email was sent automatically after your instance was provisioned.
    </div>
  </div>
</div>
"""

		frappe.sendmail(
			recipients=[tenant.admin_email],
			subject=subject,
			message=message,
			now=True,
		)
		frappe.logger().info(f"Welcome email sent to {tenant.admin_email} for tenant {tenant.name}")

	except Exception:
		frappe.logger().warning(
			f"Welcome email failed for tenant {tenant.name}: {frappe.get_traceback()}"
		)


def _send_app_update_email(tenant, apps_added):
	"""Notify the tenant admin that new apps were installed on their instance.
	Email failure never raises — the app install is already complete at this point.
	"""
	if not getattr(tenant, "admin_email", None) or not apps_added:
		return

	try:
		is_production = frappe.conf.get("is_production", False)
		port = "" if is_production else ":8000"
		site_url = f"http://{tenant.site_name}{port}"

		app_labels = {"erpnext": "SBIQC", "quality_dms": "DMS"}
		display_apps = [app_labels.get(a, a) for a in apps_added]
		apps_list_html = "".join(f"<li>{a}</li>" for a in display_apps)

		subject = f"New apps added to your SBIQ instance — {tenant.client_name}"

		message = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1f2937;">
  <div style="background:#6366f1;padding:28px 32px;border-radius:8px 8px 0 0;">
    <h1 style="color:#fff;font-size:22px;margin:0;">Your SBIQ instance was updated</h1>
    <p style="color:#e0e7ff;margin:8px 0 0;font-size:14px;">New apps have been installed and are ready to use.</p>
  </div>
  <div style="background:#f9fafb;padding:28px 32px;border:1px solid #e5e7eb;border-top:0;">
    <h2 style="font-size:16px;color:#374151;margin:0 0 16px;">Apps added</h2>
    <ul style="font-size:14px;color:#374151;line-height:1.8;padding-left:18px;margin:0 0 20px;">
      {apps_list_html}
    </ul>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr>
        <td style="padding:8px 0;color:#6b7280;width:140px;">Site URL</td>
        <td style="padding:8px 0;"><a href="{site_url}" style="color:#6366f1;font-weight:600;">{site_url}</a></td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Client</td>
        <td style="padding:8px 0;font-weight:600;">{tenant.client_name}</td>
      </tr>
    </table>
    <div style="margin-top:28px;padding-top:20px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
      Powered by <strong>SBIQ</strong><br/>
      This email was sent automatically after your instance was updated.
    </div>
  </div>
</div>
"""

		frappe.sendmail(
			recipients=[tenant.admin_email],
			subject=subject,
			message=message,
			now=True,
		)
		frappe.logger().info(f"App update email sent to {tenant.admin_email} for tenant {tenant.name}")

	except Exception:
		frappe.logger().warning(
			f"App update email failed for tenant {tenant.name}: {frappe.get_traceback()}"
		)


# Argv flags whose following value must never appear in error messages or logs.
SENSITIVE_FLAGS = ("--mariadb-root-password", "--admin-password")


def _redact_argv(argv):
	"""Return a display string for argv with values of sensitive flags redacted."""
	redacted = []
	redact_next = False
	for arg in argv:
		if redact_next:
			redacted.append("[REDACTED]")
			redact_next = False
		else:
			redacted.append(arg)
			if arg in SENSITIVE_FLAGS:
				redact_next = True
	return " ".join(redacted)


def _redact_values(text, secret_values):
	"""Defense in depth: strip any literal secret value that might have been
	echoed back verbatim in a subprocess's own stdout/stderr (argv redaction
	in _redact_argv only covers the command line we constructed, not output
	the child process chooses to print)."""
	for value in secret_values:
		if value:
			text = text.replace(value, "[REDACTED]")
	return text


def _run(argv, cwd=None, timeout=120, secret_values=()):
	try:
		result = subprocess.run(
			argv, cwd=cwd,
			capture_output=True, text=True, timeout=timeout,
		)
	except subprocess.TimeoutExpired:
		# `from None` suppresses exception chaining: str(TimeoutExpired) embeds the
		# raw argv (including passwords), and a chained __context__/__cause__ would
		# still surface it in traceback.format_exc(). Only the redacted command may leak.
		raise RuntimeError(
			f"Command timed out after {timeout}s: {_redact_argv(argv)}"
		) from None
	if result.returncode != 0:
		raise RuntimeError(
			f"Command failed (exit {result.returncode}): {_redact_argv(argv)}\n"
			f"stdout: {_redact_values(result.stdout[-2000:], secret_values)}\n"
			f"stderr: {_redact_values(result.stderr[-2000:], secret_values)}"
		)
	return result.stdout


def _get_installed_apps(site_name, bench_path):
	"""Return set of apps already installed on a site."""
	result = subprocess.run(
		[_bench_bin(), "--site", site_name, "list-apps"],
		cwd=bench_path,
		capture_output=True, text=True, timeout=30,
	)
	if result.returncode != 0:
		return set()
	return {line.strip() for line in result.stdout.strip().splitlines() if line.strip()}


def _clear_stale_locks(site_name, bench_path):
	"""Remove stale install_app.lock left by a crashed prior run."""
	lock_dir = os.path.join(bench_path, "sites", site_name, "locks")
	if not os.path.isdir(lock_dir):
		return
	lock_file = os.path.join(lock_dir, "install_app.lock")
	if os.path.exists(lock_file):
		os.remove(lock_file)


def _install_app(site_name, app, bench_path):
	"""Install an app on a site. Tolerates non-zero exit if the app ends up installed."""
	result = subprocess.run(
		[_bench_bin(), "--site", site_name, "install-app", app],
		cwd=bench_path,
		capture_output=True, text=True, timeout=300,
	)
	if result.returncode != 0:
		verify = subprocess.run(
			[_bench_bin(), "--site", site_name, "list-apps"],
			cwd=bench_path,
			capture_output=True, text=True, timeout=30,
		)
		if app in verify.stdout:
			return
		raise RuntimeError(
			f"Failed to install {app} on {site_name} (exit {result.returncode}):\n"
			f"stderr: {result.stderr[-2000:]}"
		)


def _setup_local_routing(site_name):
	"""Idempotently add 127.0.0.1 entry to both WSL /etc/hosts and Windows hosts file.

	This is written for a WSL dev bench (sudo + /mnt/c/... available). In a
	plain Docker container (no sudo, no /mnt/c) it's not just optional but
	unnecessary — *.localhost already resolves to 127.0.0.1 in modern
	browsers without any hosts-file entry — so skip gracefully with a
	warning instead of crashing the whole provisioning run over a routing
	nicety that has no effect on whether the tenant is actually usable.
	"""
	if not shutil.which("sudo"):
		frappe.logger().warning(
			f"Skipping /etc/hosts update for {site_name} — no 'sudo' in this environment "
			"(expected outside WSL; *.localhost resolves to 127.0.0.1 automatically anyway)."
		)
		return

	hosts_entry = f"127.0.0.1   {site_name}"

	# --- WSL /etc/hosts ---
	with open("/etc/hosts", "r") as f:
		content = f.read()

	if hosts_entry not in content:
		result = subprocess.run(
			["sudo", "-n", "tee", "-a", "/etc/hosts"],
			input=(hosts_entry + "\n").encode(),
			shell=False,
			capture_output=True,
			text=False,
			timeout=30,
		)
		result_stderr = result.stderr.decode(errors="replace") if result.stderr else ""
		result_returncode = result.returncode
		if result_returncode != 0:
			frappe.log_error(
				title=f"Failed to update WSL /etc/hosts for {site_name}",
				message=result_stderr,
			)
			raise RuntimeError(f"Could not update WSL /etc/hosts: {result_stderr}")

	# --- Windows hosts file (for browser access) ---
	_update_windows_hosts(site_name)


def _update_windows_hosts(site_name):
	"""Idempotently add 127.0.0.1 entry to the Windows hosts file (WSL only)."""
	win_hosts = "/mnt/c/Windows/System32/drivers/etc/hosts"

	try:
		with open(win_hosts, "r") as f:
			content = f.read()
	except FileNotFoundError:
		return

	hosts_entry = f"127.0.0.1   {site_name}"
	if hosts_entry in content:
		return

	try:
		with open(win_hosts, "a") as f:
			f.write(f"\n{hosts_entry}\n")
	except PermissionError:
		frappe.log_error(
			title=f"Cannot write Windows hosts for {site_name}",
			message=(
				f"Permission denied on {win_hosts}. "
				f"Run in PowerShell as admin: icacls \"C:\\Windows\\System32\\drivers\\etc\\hosts\" /grant \"$USER:(M)\""
			),
		)
		frappe.msgprint(
			f"Could not auto-update Windows hosts file for {site_name}. "
			f"Please manually add '{hosts_entry}' to C:\\Windows\\System32\\drivers\\etc\\hosts",
			alert=True,
		)


def _setup_production_routing(site_name):
	"""
	Production routing relies on wildcard DNS (*.sbiqc.com -> this server) plus a
	single shared Nginx server block with a wildcard TLS cert (*.sbiqc.com) that
	proxies every subdomain to this bench (see infra/nginx/sbiqc-wildcard.conf).
	Because that one config already covers every possible tenant subdomain,
	there is no per-tenant Nginx file to generate, validate, or reload here.

	This function's job is instead to verify the new site is actually reachable
	end-to-end through that existing routing layer, so a wildcard-DNS,
	Nginx, or TLS-cert misconfiguration surfaces as a provisioning failure
	rather than silently leaving an "Active" tenant nobody can reach.
	"""
	import requests

	url = f"https://{site_name}/api/method/ping"
	try:
		resp = requests.get(url, timeout=10)
		resp.raise_for_status()
	except Exception as e:
		raise RuntimeError(
			f"Site {site_name} was provisioned but is not reachable via the production "
			f"routing layer ({url}): {e}. Check wildcard DNS (*.{{domain}} -> this server), "
			f"the shared Nginx wildcard server block, and the wildcard TLS certificate."
		) from e


def provision_update(tenant_name, apps_to_add):
	"""Install additional apps on an already-Active tenant site."""
	frappe.init(site=frappe.local.site)
	frappe.connect()

	tenant = frappe.get_doc("Tenant", tenant_name)
	bench_path = frappe.utils.get_bench_path()
	site_name = tenant.site_name

	log_name = create_log(tenant_name, site_name)

	try:
		_update_status(tenant, "Provisioning")
		update_log_step(log_name, "Starting app update", 5)
		_clear_stale_locks(site_name, bench_path)
		already_installed = _get_installed_apps(site_name, bench_path)
		to_install = [a for a in apps_to_add if a not in already_installed]
		to_install = list(dict.fromkeys(to_install))  # preserve order, remove dupes

		if not to_install:
			update_log_step(log_name, "All requested apps already installed", 80)
		else:
			for i, app in enumerate(to_install):
				pct = 10 + int((i + 1) / len(to_install) * 60)
				update_log_step(log_name, f"Installing {app}", pct)
				_install_app(site_name, app, bench_path)

		update_log_step(log_name, "Running migrations", 80)
		_run([_bench_bin(), "--site", site_name, "migrate"], cwd=bench_path, timeout=300)

		update_log_step(log_name, "Clearing cache", 92)
		_run([_bench_bin(), "--site", site_name, "clear-cache"], cwd=bench_path)

		# Append new apps to Tenant.apps_to_install child table
		tenant.reload()
		existing_apps = {row.app_name for row in tenant.apps_to_install}
		for app in to_install:
			if app not in existing_apps:
				tenant.append("apps_to_install", {"app_name": app})
		if to_install:
			tenant.flags.ignore_validate_update_after_submit = True
			tenant.save(ignore_permissions=True)  # background worker has no session user context
		frappe.db.commit()

		_update_status(tenant, "Active")
		complete_log(log_name)

		if to_install:
			_send_app_update_email(tenant, to_install)

	except Exception:
		tb = traceback.format_exc()
		_update_status(tenant, "Error")
		tenant.reload()
		tenant.db_set("error_log", tb[:10000])
		frappe.db.commit()
		frappe.log_error(title=f"App update failed: {tenant_name}", message=tb)
		complete_log(log_name, failed=True, error=tb)
		raise
