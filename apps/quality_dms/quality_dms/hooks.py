app_name = "quality_dms"
app_title = "SBIQC"
app_publisher = "Quality Team"
app_description = "Document Management System"
app_email = "quality@example.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "quality_dms",
# 		"logo": "/assets/quality_dms/logo.png",
# 		"title": "Quality DMS",
# 		"route": "/quality_dms",
# 		"has_permission": "quality_dms.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/quality_dms/css/quality_dms.css?v=40"
app_include_js = "/assets/quality_dms/js/quality_dms.js?v=46"

# include js, css files in header of web template
# web_include_css = "/assets/quality_dms/css/quality_dms.css"
# web_include_js = "/assets/quality_dms/js/quality_dms.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "quality_dms/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Payment Entry": "public/js/payment_entry.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "quality_dms/public/icons.svg"

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
# jinja = {
# 	"methods": "quality_dms.utils.jinja_methods",
# 	"filters": "quality_dms.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "quality_dms.install.before_install"
# after_install = "quality_dms.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "quality_dms.uninstall.before_uninstall"
# after_uninstall = "quality_dms.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "quality_dms.utils.before_app_install"
# after_app_install = "quality_dms.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "quality_dms.utils.before_app_uninstall"
# after_app_uninstall = "quality_dms.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "quality_dms.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "quality_dms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Document Library": "quality_dms.dms.api.get_permission_query_conditions",
	"DMS Training Record": "quality_dms.dms.doctype.dms_training_record.dms_training_record.get_permission_query_conditions",
	"DMS Training Score History": "quality_dms.dms.doctype.dms_training_score_history.dms_training_score_history.get_permission_query_conditions",
	"File": "quality_dms.dms.api.file_permission_query_conditions",
}

has_permission = {
	"Document Library": "quality_dms.dms.api.has_permission",
	"DMS Training Record": "quality_dms.dms.doctype.dms_training_record.dms_training_record.has_permission",
	"DMS Training Score History": "quality_dms.dms.doctype.dms_training_score_history.dms_training_score_history.has_permission",
	"File": "quality_dms.dms.api.file_has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"File": {
		"before_insert": "quality_dms.dms.virus_scan.scan_file_before_insert",
	},
	"Document Library": {
		"on_update": "quality_dms.dms.api.log_audit_event",
		"on_submit": "quality_dms.dms.api.log_audit_event",
		"on_cancel": "quality_dms.dms.api.log_audit_event",
		"on_trash": "quality_dms.dms.api.log_audit_event",
	},
	"Document Request": {
		"on_update": "quality_dms.dms.api.log_request_audit_event",
		"on_trash": "quality_dms.dms.api.log_request_audit_event",
	},
	"Document Category": {
		"after_insert": "quality_dms.dms.doctype.document_category.document_category.create_file_folder",
		"on_update": "quality_dms.dms.doctype.document_category.document_category.create_file_folder",
	},
	"Employee": {
		"after_insert": "quality_dms.dms.doctype.dms_training_assignment_rule.dms_training_assignment_rule.apply_onboarding_rules",
		"on_update": "quality_dms.dms.api.handle_employee_status_change",
	},
}

scheduler_events = {
	"daily": [
		"quality_dms.dms.api.notify_upcoming_reviews",
		"quality_dms.dms.doctype.dms_training_record.dms_training_record.mark_overdue_training_records",
		"quality_dms.dms.doctype.dms_training_record.dms_training_record.check_training_expiry",
		"quality_dms.dms.doctype.dms_training_record.dms_training_record.escalate_overdue_training",
	],
	"weekly": [
		"quality_dms.dms.doctype.dms_training_record.dms_training_record.send_manager_training_digest",
	],
}

# Testing
# -------

# before_tests = "quality_dms.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "quality_dms.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "quality_dms.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "quality_dms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["quality_dms.utils.before_request"]
# after_request = ["quality_dms.utils.after_request"]

# Job Events
# ----------
# before_job = ["quality_dms.utils.before_job"]
# after_job = ["quality_dms.utils.after_job"]

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
# 	"quality_dms.auth.validate"
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

