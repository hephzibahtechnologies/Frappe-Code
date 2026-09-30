# Copyright (c) 2026, Quality Team and contributors
# Patch: Re-apply custom app-switcher (Desktop Icon) artwork, correcting the
# one entry that v1_7 keyed on the wrong field.
#
# v1_7_set_custom_desktop_icons.py keyed ICON_MAP on the Desktop Icon record
# NAME, but for the "SBIQC Settings" tile it used the LABEL by mistake. The
# actual record is named "ERPNext Settings" (its label is "SBIQC Settings"),
# so `frappe.db.exists("Desktop Icon", "SBIQC Settings")` is always False and
# the patch silently skipped it -- fine on sites where the logo_url happened
# to already be set in the DB, but on a fresh site that tile falls back to the
# grey letter after deploy.
#
# This patch re-applies every custom tile idempotently, using the correct
# record NAME for each. It is safe to run repeatedly: it only writes when a
# record exists and its logo_url isn't already the expected value.
#
# (v1_7 already ran on existing sites and is recorded in Patch Log, so editing
# it in place would not re-run. Hence a new patch.)

import frappe

# Keyed on the Desktop Icon record NAME (not the display label).
ICON_MAP = {
	"CRM": "crm.png",
	"Framework": "sbiqc.png",
	"SBIQC Provisioning": "sbiqc_provisioning.png",
	"ERPNext Settings": "sbiqc_settings.png",  # label is "SBIQC Settings"
	"Frappe CRM": "frappe_crm.png",
	"Frappe HR": "frappe_hr.png",
	"DMS": "dms.png",
}


def execute():
	changed = False
	for name, filename in ICON_MAP.items():
		if not frappe.db.exists("Desktop Icon", name):
			continue
		logo_url = f"/assets/quality_dms/images/desktop_icons/{filename}"
		if frappe.db.get_value("Desktop Icon", name, "logo_url") == logo_url:
			continue
		frappe.db.set_value("Desktop Icon", name, "logo_url", logo_url, update_modified=False)
		frappe.db.set_value("Desktop Icon", name, "icon_image", "", update_modified=False)
		changed = True

	if changed:
		frappe.db.commit()
		frappe.clear_cache()
