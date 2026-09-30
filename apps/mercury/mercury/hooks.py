app_name = "mercury"
app_title = "Mercury"
app_publisher = "Hephzibah Tech"
app_description = "Mercury client demo: configuration and customizations"
app_email = "paul.sahayadoss@hephzibahtech.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "mercury",
# 		"logo": "/assets/mercury/logo.png",
# 		"title": "Mercury",
# 		"route": "/mercury",
# 		"has_permission": "mercury.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Desk UI overrides: single (hidden) scrollbar on form views, form sidebar aligned
# with the main section, and a permanently pinned page head + form tab bar.
# Additive CSS only - no frappe/erpnext core file is patched, so commenting this
# line out reverts every one of those behaviours.
# Bump ?v= when editing the file so browsers pick the change up (same convention
# as hrms/quality_dms above it in the include list).
app_include_css = "/assets/mercury/css/mercury_desk.css?v=23"
app_include_js = "/assets/mercury/js/mercury_desk.js?v=4"

# include js, css files in header of web template
# web_include_css = "/assets/mercury/css/mercury.css"
# web_include_js = "/assets/mercury/js/mercury.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "mercury/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "mercury/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# qr_base64() renders a QR code (base64 PNG) inside Print Formats — used by the
# Mercury shipping label (Stage 6). v16 has no built-in QR-in-print, so this small
# helper (uses the pre-installed pyqrcode lib) is the "light custom" piece.
jinja = {
	"methods": ["mercury.utils.qr_base64"],
}

# Installation
# ------------

# before_install = "mercury.install.before_install"
# after_install = "mercury.install.after_install"

after_migrate = [
	"mercury.desktop_icons.remove_stray_icons",
	"mercury.desktop_icons.flatten_accounting_folder",
	"mercury.desktop_icons.apply_desktop_icon_layout",
	"mercury.desktop_icons.sync_desktop_layouts",
	"mercury.desktop_icons.apply_navbar_branding",
	"mercury.desktop_icons.apply_brand_settings",
]

# Uninstallation
# ------------

# before_uninstall = "mercury.uninstall.before_uninstall"
# after_uninstall = "mercury.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "mercury.utils.before_app_install"
# after_app_install = "mercury.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "mercury.utils.before_app_uninstall"
# after_app_uninstall = "mercury.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "mercury.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "mercury.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Demo housekeeping: keep unrelated projects off the screen without deleting them.
# The list of hidden projects lives in mercury/demo_hide.py - empty it and clear-cache
# to bring everything back. Nothing is deleted; these only filter queries.
permission_query_conditions = {
	"Project": "mercury.demo_hide.project_query",
	"Task": "mercury.demo_hide.task_query",
	"Project Update": "mercury.demo_hide.project_update_query",
	"Timesheet": "mercury.demo_hide.timesheet_query",
}

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# The custom "Delivered" Task status is added DocType-wide by a Property Setter
# (Select options are metadata - they cannot be per-record). The Client Script on Task
# only hides it in the UI; this hook is what actually enforces the company gate for
# REST / Data Import / db.set_value writes. See mercury/task_status.py.
doc_events = {
	"Task": {
		"validate": [
			"mercury.task_status.validate",
			# Assignee required on real Tasks, exempt on templates. The field's
			# mandatory_depends_on is JS-only (frappe has no python side for it),
			# so this hook is what actually enforces it. See task_assign.py.
			"mercury.task_assign.validate_assignee",
		],
		# Assign tab -> real ToDo assignment. on_update, not validate: a ToDo needs
		# doc.name, which does not exist until after the insert. See task_assign.py.
		"on_update": "mercury.task_assign.sync_assignment",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"mercury.tasks.all"
# 	],
# 	"daily": [
# 		"mercury.tasks.daily"
# 	],
# 	"hourly": [
# 		"mercury.tasks.hourly"
# 	],
# 	"weekly": [
# 		"mercury.tasks.weekly"
# 	],
# 	"monthly": [
# 		"mercury.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "mercury.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "mercury.custom.task.CustomTaskMixin"
# }

# The nightly overdue sweep (erpnext daily_maintenance -> set_tasks_as_overdue) flips
# any task that is not Cancelled/Completed and whose exp_end_date has passed. Our
# custom "Delivered" status is not on that hardcoded list, so it reverts to Overdue on
# the first night after a Mercury task gets an Expected End Date. The mixin makes
# Delivered terminal. A mixin rather than a doc_event because update_status() writes
# with db_set() and never runs validate. See mercury/task_status.py.
extend_doctype_class = {
	"Task": "mercury.task_status.TaskStatusMixin",
}

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "mercury.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "mercury.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["mercury.utils.before_request"]
# after_request = ["mercury.utils.after_request"]

# Job Events
# ----------
# before_job = ["mercury.utils.before_job"]
# after_job = ["mercury.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"mercury.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Fixtures
# --------
# Config objects owned by the Mercury app are exported to JSON here so they are
# git-tracked and re-applied by `bench migrate` (see .claude/rules.md).
# As each Phase 1 stage is built, its config object is added below and re-exported
# with:  bench --site mysite.local export-fixtures --app mercury
fixtures = [
	# Workspace uses an ERPNext module ("Setup") so the desk groups it under the
	# ERPNext app (see boot.py: grouping joins Workspace.module -> Module Def.app_name).
	# Exported by NAME so it stays owned by the mercury app regardless of module.
	{"dt": "Workspace", "filters": [["name", "=", "Mercury"]]},
	# The desk flyout menu is built from Workspace Sidebar records (one per top-level
	# entry). This record backs the Mercury flyout entry.
	# Only "Mercury" - our own record. Deliberately NOT the erpnext-owned "Projects"
	# sidebar: exporting that would make mercury's copy win on every environment and
	# silently block later erpnext changes to it.
	{"dt": "Workspace Sidebar", "filters": [["name", "=", "Mercury"]]},
	# The Workspaces flyout is actually rendered from Desktop Icon records (each points
	# to a Workspace Sidebar via link_to). This Desktop Icon puts "Mercury" in the
	# ERPNext group (parent_icon="ERPNext").
	{"dt": "Desktop Icon", "filters": [["name", "=", "Mercury"]]},
	# Stage 2 - RTM approval workflow on Sales Order + the states/actions it references.
	{"dt": "Workflow", "filters": [["name", "=", "Mercury RTM Approval"]]},
	{"dt": "Workflow State", "filters": [["name", "in", [
		"Draft", "Submittal Under Customer Review", "Revision Requested", "RTM Approved"]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", [
		"Send for Customer Review", "Approve RTM", "Request Revision", "Resubmit for Review"]]]},
	# Stage 6 - "Mercury Shipping Label" (per-unit QR labels, references the logo at
	# /assets/mercury/images/mercury_logo.png) and Stage 8 - "Mercury Monthly Progress
	# Report". The logo itself is a FILE in this app's public/images (not a DB record),
	# so it travels with git; only the HTML that references it lives in the DB.
	{"dt": "Print Format", "filters": [["name", "like", "Mercury%"]]},
	# The five progress payments named in Mercury's schedule 103-1105VS10. These are
	# LINK targets for the rows of the template below, so - like the Quality
	# Inspection Parameters further down - they must import FIRST or the template
	# import fails with LinkValidationError.
	{"dt": "Payment Term", "filters": [["name", "like", "Progress Payment:%"]]},
	# Stage 7 - milestone billing schedules: the original 30/40/30, and the
	# 1105VS10 five-milestone schedule taken from the client's own document.
	{"dt": "Payment Terms Template", "filters": [["name", "like", "Mercury%"]]},
	# Stage 5/6e - incoming (raw material) + outgoing (finished pump + accessories)
	# QC checklists. NOTE: a template row's "specification" is a LINK to Quality
	# Inspection Parameter, so those records must be imported BEFORE the templates
	# or the template import fails with LinkValidationError. They are listed first
	# because fixtures import in the order given here.
	{"dt": "Quality Inspection Parameter", "filters": [["name", "in", [
		"Surface Finish", "Hardness (HB)", "Dimensional Tolerance",
		"Leak / Hydro Test", "Performance Check", "Paint / Finish",
		"Visual / Surface Finish", "Dimensional / Flange Fit", "Marking / Tag Present"]]]},
	{"dt": "Quality Inspection Template", "filters": [["name", "like", "Mercury%"]]},
	# Custom "Delivered" Task status (mgmt request, 2026-08-05). Three records:
	#   Property Setter  - appends "Delivered" to Task.status options (DocType-wide;
	#                      Select options are metadata and cannot be per-record).
	#   Custom Field     - Company.allow_delivered_task_status, the opt-in checkbox.
	#   Client Script    - hides the option unless the task's company has opted in.
	# Server-side enforcement is code, not config: mercury/task_status.py via doc_events.
	# Filtered by module so only records this app owns are exported.
	{"dt": "Custom Field", "filters": [["module", "=", "Mercury"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "Mercury"]]},
	{"dt": "Client Script", "filters": [["module", "=", "Mercury"]]},
]

