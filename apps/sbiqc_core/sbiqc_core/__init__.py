__version__ = "0.1.0"

# Teach Frappe's server-side date parser the global dd-MMM-yyyy format. This runs
# whenever Frappe loads the app's hooks (every web worker, background worker and
# bench command for a site that has this app installed). It only adds a missing
# dictionary entry, so it is safe to import repeatedly and never touches core code.
try:
    from sbiqc_core.date_format import register_python_date_format

    register_python_date_format()
except ImportError:  # frappe is not importable while the package is being built
    pass
