"""Desktop icon layout for the SBIQC desk.

ERPNext ships its workspace Desktop Icons nested under a single ``ERPNext``
app icon (``parent_icon = "ERPNext"``), so the desk landing page shows one
ERPNext tile instead of the individual workspaces. SBIQC wants them flat, and
wants a real icon on every tile.

This runs from the ``after_migrate`` hook rather than being written into
``apps/erpnext/erpnext/desktop_icon/*.json`` because:

* CLAUDE.md forbids patching frappe / erpnext / hrms core.
* Those files are re-imported from the erpnext app on every ``bench migrate``,
  so an edit there is undone by the next upstream pull anyway.

Icon resolution (frappe/public/js/frappe/ui/desktop_icon.html) is, in order:

1. ``assets/{app}/icons/desktop_icons/{style}/{scrub(label)}.svg``
2. ``logo_url`` / ``icon_image``
3. a generated first-letter tile  <- what we are getting rid of

``Desktop Settings.icon_style`` is ``Solid`` on this bench, so step 1 resolves
against ``apps/erpnext/erpnext/public/icons/desktop_icons/solid/``. Every label
in FLATTEN below has a matching svg there except the ones listed in LOGOS,
which have no erpnext svg and so need an explicit logo_url.
"""

import frappe

# Desktop Icons that erpnext nests under the "ERPNext" app tile. Clearing
# parent_icon promotes them to the desk root.
FLATTEN = [
	"Assets",
	"Buying",
	"CRM",
	"DMS",
	"Manufacturing",
	"Mercury",
	"Projects",
	"Quality",
	"Selling",
	"Stock",
]

# Labels with no matching svg under erpnext's solid/ directory. Without these
# they fall through to the generated first-letter tile.
#
# logo_url only rescues the desk grid. The sidebar "Workspaces" flyout and the
# folder popup go through get_icon_for_menu_item() / build_folder_map() in
# frappe/public/js/frappe/ui/sidebar/sidebar_header.js, which try the svg
# lookup and then go straight to the letter tile - they never read logo_url.
# So anything that must look right in ALL THREE places needs a real svg.
LOGOS = {
	"Mercury": "/assets/mercury/images/desktop_icons/mercury.png",
	"SBIQC Settings": "/assets/quality_dms/images/desktop_icons/sbiqc_settings.png",
	# re-applied after every migrate: re-importing quality_dms/desktop_icon/dms.json
	# resets this field to null
	"DMS": "/assets/quality_dms/images/desktop_icons/dms.png",
	# Everything below is served from mercury. logo_url is a plain URL, so it does
	# not have to live in the record's own app - which avoids both the orphan
	# sweep and the flyout's app grouping.
	"Accounting": "/assets/mercury/images/desktop_icons/accounting.svg",
	"Careers": "/assets/mercury/images/desktop_icons/careers.svg",
	"Home": "/assets/mercury/images/desktop_icons/home.png",
	"SBIQC ERP": "/assets/mercury/images/desktop_icons/sbiqc_erp.svg",
	# helpdesk's stock logo_url points at /assets/helpdesk/images/Helpdesk.png,
	# which the app does not ship (404). Harmless today because the svg lookup
	# wins, but it is a landmine if that ever misses - point it at the real file.
	"Helpdesk": "/assets/helpdesk/icons/desktop_icons/solid/helpdesk.svg",
	# SBIQC star + wordmark composites
	"SBIQ CRM": "/assets/mercury/images/desktop_icons/sbiq_crm.svg",
}

# set_header_icon() in sidebar_header.js looks the workspace up with
# get_desktop_icon_by_label(), which filters on `hidden != 1`. A hidden record is
# never found, so the header falls through to the generated first-letter tile -
# that is why opening Home showed a grey "H" next to "Home / SBIQC".
HIDDEN_OVERRIDES = {
	"Home": 0,
	# already visible on the grid via the layout snapshot; unhiding the live
	# record is what lets its header show the logo rather than an "S"
	"SBIQ CRM": 0,
}

# The stock "ERPNext" app tile, renamed for white-labelling. Renaming the label
# is safe: the orphan sweep matches on the record NAME, not the label - erpnext
# already ships "ERPNext Settings" which this bench relabels "SBIQC Settings".
LABELS = {
	"ERPNext": "SBIQC ERP",
}

# Repointing a *standard* Desktop Icon's `app` at mercury is NOT safe: migrate's
# "Removing orphan Desktop Icons" step deletes any standard record whose owning
# app ships no matching desktop_icon/<scrub>.json fixture, and mercury ships
# none. Doing that deleted Accounting, DMS and SBIQC Settings outright.
#
# Only non-standard records (standard=0) can be repointed this way - the orphan
# sweep leaves those alone.
#   Mercury - standard=0, needs mercury/icons/desktop_icons/*/mercury.svg
#   CRM     - standard=0, had no app set at all; erpnext already ships crm.svg
OWN_SVG_APP = {
	# Mercury must stay on erpnext. build_folder_map() in sidebar_header.js groups
	# the Workspaces flyout by frappe.current_app, so pointing it at mercury made
	# the entry disappear from the menu entirely. It gets its icon via LOGOS.
	"Mercury": "erpnext",
	"CRM": "erpnext",
}


def apply_desktop_icon_layout():
	"""Re-apply the SBIQC desk icon layout. Idempotent."""
	changed = 0

	for label in FLATTEN:
		name = frappe.db.get_value("Desktop Icon", {"label": label})
		if not name:
			continue
		if frappe.db.get_value("Desktop Icon", name, "parent_icon"):
			frappe.db.set_value("Desktop Icon", name, "parent_icon", "", update_modified=False)
			changed += 1

	for old_label, new_label in LABELS.items():
		name = frappe.db.get_value("Desktop Icon", {"label": old_label})
		if name:
			frappe.db.set_value("Desktop Icon", name, "label", new_label, update_modified=False)
			changed += 1

	for label, app in OWN_SVG_APP.items():
		name = frappe.db.get_value("Desktop Icon", {"label": label})
		if not name:
			continue
		if frappe.db.get_value("Desktop Icon", name, "app") != app:
			frappe.db.set_value("Desktop Icon", name, "app", app, update_modified=False)
			changed += 1

	for label, hidden in HIDDEN_OVERRIDES.items():
		name = frappe.db.get_value("Desktop Icon", {"label": label})
		if name and frappe.db.get_value("Desktop Icon", name, "hidden") != hidden:
			frappe.db.set_value("Desktop Icon", name, "hidden", hidden, update_modified=False)
			changed += 1

	for label, logo_url in LOGOS.items():
		name = frappe.db.get_value("Desktop Icon", {"label": label})
		if not name:
			continue
		if frappe.db.get_value("Desktop Icon", name, "logo_url") != logo_url:
			frappe.db.set_value("Desktop Icon", name, "logo_url", logo_url, update_modified=False)
			changed += 1

	if changed:
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
		frappe.clear_cache()

	print(f"mercury: desktop icon layout applied ({changed} change(s))")
	return changed


# --- Navbar white-labelling -------------------------------------------------

# frappe's standard_navbar_items hook (frappe/hooks.py) syncs a "Frappe Support"
# row into the Navbar Settings help dropdown on every migrate, pointing at
# https://frappe.io/support. SBIQC ships its own support portal.
NAVBAR_RENAMES = {
	"Frappe Support": ("SBIQC Support", "https://docs.sbiqc.com"),
}


def apply_navbar_branding():
	"""Re-point the help dropdown at the SBIQC support portal. Idempotent."""
	changed = 0
	settings = frappe.get_single("Navbar Settings")

	for row in settings.help_dropdown:
		rename = NAVBAR_RENAMES.get(row.item_label)
		if not rename:
			continue
		label, route = rename
		if row.item_label != label or row.route != route:
			row.item_label = label
			row.route = route
			row.item_type = "Route"
			changed += 1

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_cache()

	print(f"mercury: navbar branding applied ({changed} change(s))")
	return changed


# --- Desk / website branding ------------------------------------------------

# All of these were unset, which is why frappe's and erpnext's own defaults were
# showing through:
#   favicon       - desk.html falls back to /assets/frappe/images/frappe-favicon.svg
#   app_logo      - get_app_logo() (frappe/core/doctype/navbar_settings) falls back
#                   to the app_logo_url hook, i.e. erpnext-logo.svg. Drives the desk
#                   navbar, the page loader and the login page.
#   app_name      - browser tab / window title, was literally "Frappe"
#
# Setting them as data avoids patching erpnext's `app_logo_url` hook, which
# CLAUDE.md forbids. The logo lives in mercury so the branding travels with the
# override app rather than depending on quality_dms.
SBIQC_LOGO = "/assets/mercury/images/htipl_logo.png"

WEBSITE_SETTINGS = {
	"app_name": "SBIQC",
	"favicon": SBIQC_LOGO,
	"splash_image": SBIQC_LOGO,
	"app_logo": SBIQC_LOGO,
}

NAVBAR_BRANDING = {
	"app_logo": SBIQC_LOGO,
}


def apply_brand_settings():
	"""Point the favicon, loader, login logo and title at SBIQC. Idempotent."""
	changed = 0

	for doctype, values in (
		("Website Settings", WEBSITE_SETTINGS),
		("Navbar Settings", NAVBAR_BRANDING),
	):
		doc = frappe.get_single(doctype)
		dirty = False
		for field, value in values.items():
			if doc.get(field) != value:
				doc.set(field, value)
				dirty = True
				changed += 1
		if dirty:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.save()

	if changed:
		frappe.clear_cache()

	print(f"mercury: brand settings applied ({changed} change(s))")
	return changed


# --- Desktop Layout snapshot ------------------------------------------------

# The /desk grid does NOT render from the Desktop Icon table. frappe stores a
# per-user snapshot of every icon in the "Desktop Layout" doctype (its `layout`
# field is a JSON blob, see frappe/desk/doctype/desktop_layout/) and the grid
# renders that. The sidebar flyout and folder popup read the live records, so
# without this step the two disagree - the flyout updates and the grid does not.
#
# We refresh the fields we own rather than deleting the layout, so any ordering
# or hiding the user has done by hand survives.
# NOT "label". build_folder_map() in sidebar_header.js keys folders by label but
# children reference their parent by NAME, so relabelling a parent silently
# orphans every child to the desk root. Syncing labels renamed Framework ->
# SBIQC and Frappe HR -> SBIQC HR and dumped ~18 nested icons onto the grid.
SYNCED_FIELDS = ("parent_icon", "app", "logo_url", "icon_type")


def sync_desktop_layouts():
	"""Push our Desktop Icon changes into each user's saved grid snapshot."""
	import json

	changed_users = 0

	for name in frappe.get_all("Desktop Layout", pluck="name"):
		doc = frappe.get_doc("Desktop Layout", name)
		try:
			layout = json.loads(doc.layout or "[]")
		except ValueError:
			continue

		dirty = False
		for entry in layout:
			# A Desktop Icon's name is NOT always its label - erpnext ships
			# "ERPNext Settings" and this bench relabels it "SBIQC Settings" -
			# so fall back to a label lookup before giving up on an entry.
			icon_name = entry.get("name")
			if not icon_name or not frappe.db.exists("Desktop Icon", icon_name):
				icon_name = frappe.db.get_value("Desktop Icon", {"label": entry.get("label")})
			if not icon_name:
				continue
			live = frappe.db.get_value("Desktop Icon", icon_name, SYNCED_FIELDS, as_dict=True)
			for field in SYNCED_FIELDS:
				if entry.get(field) != live[field]:
					entry[field] = live[field]
					dirty = True

		# Accounting is no longer a folder, so its former children must not appear
		# as nine loose tiles on the grid. Deliberately NOT done by syncing the
		# `hidden` field wholesale: SBIQC ERP is hidden=1 in the live table and
		# doing so would delete it from the desktop.
		if ACCOUNTING_FLATTEN and ACCOUNTING_CHILDREN_HIDE:
			for entry in layout:
				if entry.get("parent_icon") == "Accounting" and not entry.get("hidden"):
					entry["hidden"] = 1
					entry["parent_icon"] = ""
					dirty = True

		# Repair pass. A folder only collects its children if its LABEL equals the
		# value the children carry in parent_icon (which is the parent's NAME).
		# Framework/Frappe HR already have label != name in the live table, so any
		# entry with visible children must be forced back to its name or the whole
		# folder empties onto the root grid.
		hidden_live = {
			r.label
			for r in frappe.get_all(
				"Desktop Icon", filters={"hidden": 1}, fields=["label"], limit_page_length=0
			)
		}
		visible_parents = {
			e.get("parent_icon")
			for e in layout
			if e.get("parent_icon") and not e.get("hidden") and e.get("label") not in hidden_live
		}
		for entry in layout:
			name = entry.get("name")
			# LABELS are deliberate white-label renames. ERPNext's only child is
			# Support, which is hidden, so nothing visible breaks by keeping it.
			if name in LABELS:
				if entry.get("label") != LABELS[name]:
					entry["label"] = LABELS[name]
					dirty = True
				continue
			if name in visible_parents and entry.get("label") != name:
				entry["label"] = name
				dirty = True

		# Icons created after the snapshot was captured are simply absent from it,
		# so the grid never shows them however the record is configured. Mercury
		# was missing for exactly this reason.
		present = set()
		for entry in layout:
			present.add(entry.get("name"))
			present.add(entry.get("label"))
		for icon in frappe.get_all(
			"Desktop Icon",
			filters={"hidden": 0, "parent_icon": ("in", ("", None))},
			fields=["name", "label", "parent_icon", "app", "logo_url", "icon",
					"icon_type", "link_type", "link_to", "standard", "bg_color"],
			limit_page_length=0,
		):
			if icon.name in present or icon.label in present:
				continue
			entry = dict(icon)
			entry.update({"idx": 0, "hidden": 0, "restrict_removal": 0,
						  "icon_image": None, "child_icons": [], "in_folder": False})
			layout.append(entry)
			dirty = True

		if dirty:
			doc.layout = json.dumps(layout)
			doc.flags.ignore_permissions = True
			doc.save()
			changed_users += 1

	if changed_users:
		frappe.clear_cache()

	print(f"mercury: desktop layout snapshots synced ({changed_users} user(s))")
	return changed_users


# --- Accounting: folder -> flat tile ----------------------------------------

# render_folder_thumbnail() (frappe/desk/page/desktop/desktop.js) clears
# .icon-container and rebuilds it as a grid of the folder's children, so a
# Folder can never show a logo_url - its icon IS that collage. Paul asked for a
# real icon, which means it stops being a Folder.
#
# Its nine children (Invoicing, Payments, Taxes, ...) are all reachable from the
# Accounts Setup sidebar and from search, so they are hidden rather than left to
# spill onto the desk root as nine loose tiles.
ACCOUNTING_FLATTEN = True
ACCOUNTING_CHILDREN_HIDE = True


def flatten_accounting_folder():
	"""Turn the Accounting folder into a normal tile with its own icon."""
	if not ACCOUNTING_FLATTEN:
		return 0

	name = frappe.db.get_value("Desktop Icon", {"label": "Accounting"})
	if not name:
		return 0

	changed = 0
	current = frappe.db.get_value(
		"Desktop Icon", name, ["icon_type", "link_to", "link_type"], as_dict=True
	)

	if current.icon_type != "Link":
		frappe.db.set_value("Desktop Icon", name, "icon_type", "Link", update_modified=False)
		changed += 1

	# no "Accounting" workspace exists; Accounts Setup is the accounting landing
	# page, so the tile has somewhere real to go instead of being inert
	if current.link_to != "Accounts Setup":
		frappe.db.set_value("Desktop Icon", name, "link_to", "Accounts Setup", update_modified=False)
		changed += 1

	if ACCOUNTING_CHILDREN_HIDE:
		for child in frappe.get_all(
			"Desktop Icon", filters={"parent_icon": "Accounting"}, pluck="name", limit_page_length=0
		):
			if not frappe.db.get_value("Desktop Icon", child, "hidden"):
				frappe.db.set_value("Desktop Icon", child, "hidden", 1, update_modified=False)
				changed += 1

	if changed:
		frappe.cache.delete_key("desktop_icons")
		frappe.clear_cache()

	print(f"mercury: accounting folder flattened ({changed} change(s))")
	return changed


# --- Cleanup ----------------------------------------------------------------

# Stray duplicate of the Mercury workspace (private, public=0). Confirmed for
# removal by Paul on 2026-08-18.
STRAY_ICONS = ["Mercury2"]

# Deleting a Workspace is destructive and irreversible, and this hook runs on
# EVERY migrate on EVERY site. Mercury2 is a local-only duplicate, so the removal
# is pinned to the dev bench - on staging/QA/production this is a no-op even if
# a workspace of the same name exists there with real content.
LOCAL_SITES = {"mysite.local"}


def remove_stray_icons():
	"""Delete leftover duplicate desktop icons and their workspaces (local only)."""
	if frappe.local.site not in LOCAL_SITES:
		print(f"mercury: stray icon cleanup skipped (site {frappe.local.site} is not local)")
		return 0

	removed = 0

	for label in STRAY_ICONS:
		name = frappe.db.get_value("Desktop Icon", {"label": label})
		if name:
			frappe.delete_doc("Desktop Icon", name, force=True, ignore_missing=True)
			removed += 1

		# the workspace and its sidebar entry go too, otherwise migrate keeps
		# recreating the icon from the workspace
		for doctype in ("Workspace Sidebar", "Workspace"):
			if frappe.db.exists(doctype, label):
				frappe.delete_doc(doctype, label, force=True, ignore_missing=True)
				removed += 1

	# drop them from every saved grid snapshot as well
	if removed:
		import json

		for name in frappe.get_all("Desktop Layout", pluck="name"):
			doc = frappe.get_doc("Desktop Layout", name)
			try:
				layout = json.loads(doc.layout or "[]")
			except ValueError:
				continue
			kept = [e for e in layout if e.get("label") not in STRAY_ICONS]
			if len(kept) != len(layout):
				doc.layout = json.dumps(kept)
				doc.flags.ignore_permissions = True
				doc.save()
		frappe.clear_cache()

	print(f"mercury: stray desktop icons removed ({removed} doc(s))")
	return removed
