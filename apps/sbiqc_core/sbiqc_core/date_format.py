"""Global ``dd-MMM-yyyy`` date format (shown as 05-Nov-2026).

Why the capital ``MMM``: Frappe's ``format_date()`` converts the setting to a
babel pattern with ``replace("mm", "MM")``. For a lowercase ``dd-mmm-yyyy`` that
produces ``dd-MMm-yyyy`` where the last ``m`` means *minutes*, and every server
side date formatting call raises. ``dd-MMM-yyyy`` is already a valid babel
pattern (abbreviated month), is accepted by moment/dayjs once upper-cased, and
is correctly converted by the Frappe CRM app, so it needs only the parser entry
below.
"""

NEW_DATE_FORMAT = "dd-MMM-yyyy"
NEW_DATE_FORMAT_STRPTIME = "%d-%b-%Y"


def register_python_date_format():
    """Add ``dd-MMM-yyyy`` to Frappe's table of parseable date formats.

    ``frappe.utils.dateutils.user_to_str`` / ``parse_date`` look the user's format
    up in this dict and raise ``KeyError`` for a format it does not list. Adding a
    key to the shared dict (rather than replacing any function) is visible to every
    module that already imported it. Idempotent, and never overrides an entry that
    already exists.
    """
    from frappe.utils.dateutils import dateformats

    dateformats.setdefault(NEW_DATE_FORMAT, NEW_DATE_FORMAT_STRPTIME)
