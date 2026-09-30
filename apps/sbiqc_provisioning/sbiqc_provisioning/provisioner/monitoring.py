"""
monitoring.py — periodic health checks for the provisioning bench.

get_bench_health() (in the Tenant doctype module) was previously only a
whitelisted API endpoint the SBIQC Provisioning console calls on demand —
nothing polled it, so a broken Redis/MariaDB/worker connection on a
provisioning host could sit unnoticed until someone happened to open the
console. This wires it into Frappe's scheduler so it's actually checked
periodically, and surfaces problems as an Error Log entry (visible to any
System Manager, alertable via Frappe's existing Error Log notification
settings) instead of a silent, unpolled endpoint.
"""

from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from sbiqc_provisioning.sbiqc_provisioning.doctype.tenant.tenant import get_bench_health

HEALTH_CHECK_ERROR_TITLE = "SBIQC Provisioning bench health check failed"

# Avoid spamming the Error Log every 15 minutes while a problem persists —
# only log again once this much time has passed since the last log entry
# with the same title.
DEDUP_WINDOW = timedelta(hours=1)


def check_bench_health():
	"""Scheduled entry point (see hooks.py scheduler_events). Never raises —
	a broken health check must not itself break the scheduler."""
	try:
		result = get_bench_health()
	except Exception:
		frappe.log_error(
			title=HEALTH_CHECK_ERROR_TITLE,
			message=f"get_bench_health() itself raised:\n{frappe.get_traceback()}",
		)
		return

	if result.get("overall") == "ok":
		return

	if _recently_logged():
		return

	failing = [c for c in result.get("checks", []) if c.get("status") != "ok"]
	details = "\n".join(
		f"- {c['name']}: {c['status']}" + (f" ({c['detail']})" if c.get("detail") else "")
		for c in failing
	)
	frappe.log_error(
		title=HEALTH_CHECK_ERROR_TITLE,
		message=f"Overall status: {result['overall']}\n\nFailing checks:\n{details}",
	)


def _recently_logged():
	"""True if an Error Log with our title was already created within DEDUP_WINDOW."""
	cutoff = now_datetime() - DEDUP_WINDOW
	return bool(
		frappe.db.exists(
			"Error Log",
			{"method": HEALTH_CHECK_ERROR_TITLE, "creation": [">", cutoff]},
		)
	)
