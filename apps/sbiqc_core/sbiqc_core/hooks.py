app_name = "sbiqc_core"
app_title = "SBIQC Core"
app_publisher = "Hephzibah Technologies"
app_description = "Site-wide SBIQC behaviour that must exist on every site (global date format)"
app_email = "lijish.wilson@hephzibahtech.com"
app_license = "mit"

# Hidden infrastructure app: no tile in the apps screen
add_to_apps_screen = []

# Browser side of the global date format: gives the desk's calendar picker the
# spelling it understands (see public/js/global_date_format.js). Loaded after
# Frappe's own bundles, so the Date controls already exist when it runs.
app_include_js = "/assets/sbiqc_core/js/global_date_format.js?v=1"

# The two Property Setters that add the optional dd-MMM-yyyy choice to
# System Settings > Date Format and Language > Date Format. Selected by module
# so only records this app owns are exported/imported. Fixtures are re-applied on
# every `bench migrate`.
fixtures = [
	{"dt": "Property Setter", "filters": [["module", "=", "SBIQC Core"]]},
]
