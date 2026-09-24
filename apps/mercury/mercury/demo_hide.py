"""Hide specific Projects (and their Tasks) from every list, report and link field.

WHY THIS EXISTS
---------------
For client demos only the relevant projects should be on screen. Deleting the others
is not acceptable - PROJ-0005 is Adam's Namibia Construction job and that stream is
paused, not finished - and a list filter is not enough, because it only affects the
one list a user happens to be looking at, not reports, dashboards or link searches.

HOW IT WORKS
------------
frappe applies `permission_query_conditions` to every list/report query
(frappe/model/db_query.py:1079). There is no Administrator short-circuit, so this
hides the records for everyone, including Administrator.

NOTHING IS DELETED. The documents, their tasks, timesheets and history are all
intact - they are simply excluded from queries. To bring one back, remove its name
from HIDDEN_PROJECTS below and run `bench --site <site> clear-cache`.

LIMITS - be honest about these
------------------------------
  - A direct URL still opens the document (this filters queries, not `get_doc`).
  - Aggregates computed outside the query builder with raw SQL are unaffected.
  - This is presentation, NOT security. It is not a substitute for permissions.
"""

import frappe

# Empty this list to show everything again.
HIDDEN_PROJECTS: list[str] = []


def _quoted() -> str:
    return ", ".join(frappe.db.escape(name) for name in HIDDEN_PROJECTS)


def project_query(user: str | None = None) -> str:
    """Hide the projects themselves."""
    if not HIDDEN_PROJECTS:
        return ""
    return f"`tabProject`.name not in ({_quoted()})"


def task_query(user: str | None = None) -> str:
    """Hide the tasks belonging to them, but keep tasks with no project."""
    if not HIDDEN_PROJECTS:
        return ""
    return f"ifnull(`tabTask`.project, '') not in ({_quoted()})"


def project_update_query(user: str | None = None) -> str:
    if not HIDDEN_PROJECTS:
        return ""
    return f"ifnull(`tabProject Update`.project, '') not in ({_quoted()})"


def timesheet_query(user: str | None = None) -> str:
    if not HIDDEN_PROJECTS:
        return ""
    return f"ifnull(`tabTimesheet`.parent_project, '') not in ({_quoted()})"
