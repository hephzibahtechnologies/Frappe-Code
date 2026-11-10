# Copyright (c) 2026, Quality Team and contributors
# Patch: show the custom app logo inside an app, not only on the desk screen.
#
# The desk draws each tile from its Desktop Icon record, but the sidebar header
# (frappe sidebar_header.js set_header_icon) looks up a Desktop Icon whose LABEL
# equals the Sidebar NAME. Where the tile label differs from the sidebar name
# (e.g. tile "SBIQC CRM" opens sidebar "FCRM") nothing matches and a grey letter
# is shown. (No link_to: Desktop Icon validates it against the legacy
# Workspace Sidebar list, where these Sidebars don't exist.) This adds hidden alias Desktop Icons named after those sidebars,
# carrying the same logo. Hidden, so the desk screen is unchanged.
# Idempotent: safe to run repeatedly.

import frappe

# sidebar name -> (logo file, owning app)
ALIASES = {
	"FCRM": ("frappe_crm.png", "crm"),
	"HR": ("frappe_hr.png", "hrms"),
	"Setup": ("sbiqc_settings.png", "erpnext"),
}


def execute():
	changed = False
	for sidebar, (filename, app) in ALIASES.items():
		if not frappe.db.exists("Sidebar", sidebar):
			continue
		logo_url = f"/assets/quality_dms/images/desktop_icons/{filename}"
		if frappe.db.exists("Desktop Icon", sidebar):
			if frappe.db.get_value("Desktop Icon", sidebar, "logo_url") != logo_url:
				frappe.db.set_value("Desktop Icon", sidebar, "logo_url", logo_url, update_modified=False)
				changed = True
			continue
		frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": sidebar,
				"icon_type": "Link",
				"app": app,
				"hidden": 1,
				"standard": 0,
				"logo_url": logo_url,
			}
		).insert(ignore_permissions=True)
		changed = True

	if changed:
		frappe.db.commit()
		frappe.clear_cache()
