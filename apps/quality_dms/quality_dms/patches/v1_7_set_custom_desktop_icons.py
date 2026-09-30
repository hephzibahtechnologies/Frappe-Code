# Copyright (c) 2026, Quality Team and contributors
# Patch: Point a set of app-switcher (Desktop Icon) tiles at custom artwork.
#
# These were originally set by editing the Desktop Icon records directly in
# a dev site's database (via the Icon Image/logo_url fields) -- that works
# on the site it was done on, but a fresh site's database has none of it,
# so the tiles would silently fall back to their defaults after a deploy.
# This patch re-applies the same values from images bundled with this app
# (quality_dms/public/images/desktop_icons/), so any site running this app
# ends up with the same icons after `bench migrate`.
#
# Not every record here belongs to quality_dms (CRM/Framework/SBIQC
# Provisioning/SBIQC Settings/Frappe CRM/Frappe HR are core/vendor Desktop
# Icon records) -- there's no other app in this repo set up to own a
# "branding" patch for shared tiles, and quality_dms is the one actively
# maintained here, so it's grouped with DMS's own tile update rather than
# split across several near-empty patches in other apps.
#
# Excluded: Mercury's Desktop Icon tile, and the 10 tiles patched directly
# in vendor SVG files (Helpdesk + 9 ERPNext module icons) -- those already
# deploy correctly as-is (Mercury has its own fixture in the mercury app;
# the vendor SVGs are just files, no DB state involved).

import frappe

ICON_MAP = {
	"CRM": "crm.png",
	"Framework": "sbiqc.png",
	"SBIQC Provisioning": "sbiqc_provisioning.png",
	"SBIQC Settings": "sbiqc_settings.png",
	"Frappe CRM": "frappe_crm.png",
	"Frappe HR": "frappe_hr.png",
	"DMS": "dms.png",
}


def execute():
	for name, filename in ICON_MAP.items():
		if not frappe.db.exists("Desktop Icon", name):
			continue
		frappe.db.set_value(
			"Desktop Icon", name, "logo_url",
			f"/assets/quality_dms/images/desktop_icons/{filename}",
			update_modified=False,
		)
		frappe.db.set_value("Desktop Icon", name, "icon_image", "", update_modified=False)
	frappe.db.commit()
