# Copyright (c) 2026, Quality Team and contributors
# Patch: remove the hidden alias Desktop Icons (FCRM, HR, Setup) added by an earlier, reverted
# attempt. The deployed sidebar header never reads Desktop Icons, so they had no effect.
# Only removes records that match exactly what that attempt created. Idempotent.

import frappe

ALIASES = {
	"FCRM": "/assets/quality_dms/images/desktop_icons/frappe_crm.png",
	"HR": "/assets/quality_dms/images/desktop_icons/frappe_hr.png",
	"Setup": "/assets/quality_dms/images/desktop_icons/sbiqc_settings.png",
}


def execute():
	changed = False
	for name, logo_url in ALIASES.items():
		if frappe.db.exists("Desktop Icon", {"name": name, "hidden": 1, "standard": 0, "logo_url": logo_url}):
			frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True)
			changed = True
	if changed:
		frappe.db.commit()
		frappe.clear_cache()
