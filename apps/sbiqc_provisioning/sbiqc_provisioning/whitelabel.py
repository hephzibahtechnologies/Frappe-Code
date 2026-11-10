import frappe

# Apps whose titles get replaced with "SBIQC" in the sidebar / boot data
_REBRAND_APPS = {"frappe", "erpnext", "hrms", "helpdesk", "telephony", "crm_unify", "sbiqc_provisioning"}

# Apps whose own logo (the "E" mark) is replaced with the SBIQC logo. The sidebar header of an
# app without a dock shows its owning app's logo (frappe.boot.app_data[].app_logo_url), which for
# every ERPNext module (Selling, Buying, Setup, ...) is erpnext's hook-defined logo. Overridden
# here in boot data so erpnext's own hooks stay untouched.
_SBIQC_LOGO = "/assets/mercury/images/htipl_logo.png"
_LOGO_REBRAND_APPS = {"erpnext"}

# Desktop Icon label overrides — name (PK) left unchanged so parent_icon refs still resolve.
# The fixture JSONs are also patched, so this is a belt-and-suspenders DB sync.
# Note: "ERPNext" icon is hidden=1 so it's never shown — skip it to avoid duplicate label errors.
_DESKTOP_ICON_LABELS = {
    "Framework": "SBIQC",
    "Frappe HR": "SBIQC HR",
    "ERPNext Settings": "SBIQC Settings",
    "Frappe CRM": "SBIQC CRM",
}


def extend_bootinfo(bootinfo):
	"""Replace all app_title entries in boot data with 'SBIQC'."""
	for app in bootinfo.get("app_data") or []:
		if app.get("app_name") in _REBRAND_APPS:
			app["app_title"] = "SBIQC"
		if app.get("app_name") in _LOGO_REBRAND_APPS:
			app["app_logo_url"] = _SBIQC_LOGO

	# Ensure sysdefaults app_name is correct in the boot payload
	if bootinfo.get("sysdefaults"):
		bootinfo["sysdefaults"]["app_name"] = "SBIQC"


def apply_branding():
	"""Run on every bench migrate — keeps DB settings in sync."""
	frappe.db.set_single_value("System Settings", "app_name", "SBIQC")
	frappe.db.set_single_value("Website Settings", "footer_powered", "Powered by SBIQC")

	# Relabel Desktop Icons that still carry Frappe/ERPNext branding.
	# We change only the label (display text), not the name (PK/route), so
	# parent_icon references and any stored user preferences stay intact.
	for icon_name, new_label in _DESKTOP_ICON_LABELS.items():
		if frappe.db.exists("Desktop Icon", icon_name):
			current = frappe.db.get_value("Desktop Icon", icon_name, "label")
			label_taken_elsewhere = frappe.db.exists(
				"Desktop Icon", {"label": new_label, "name": ["!=", icon_name]}
			)
			if current != new_label and not label_taken_elsewhere:
				frappe.db.set_value("Desktop Icon", icon_name, "label", new_label, update_modified=False)
				# ERPNext Settings icon links to the workspace sidebar — update its link_to too
				if icon_name == "ERPNext Settings":
					frappe.db.set_value("Desktop Icon", icon_name, "link_to", "SBIQC Settings", update_modified=False)

	frappe.db.commit()
