"""Server-side gate for the custom "Delivered" Task status.

The option itself is added by a Property Setter (Task.status options), which is
DocType-wide - Frappe Select options are metadata, so there is no way to offer an
option to only some records. The Client Script on Task hides it in the UI, but the
UI is not a control: a REST call, a Data Import or `frappe.db.set_value` would still
write "Delivered" onto any task. This hook is the actual enforcement.

Gate = the `allow_delivered_task_status` checkbox on Company (a Custom Field owned by
this app), NOT a hardcoded company name. Company is a Link field, so its value is the
exact record name and a name comparison would work today - but it would silently also
match a future "Mercury Freight Ltd", and enabling a second company would mean a code
change instead of a click.

Wired up in hooks.py -> doc_events["Task"]["validate"].

This module also carries TaskStatusMixin, which stops the nightly overdue sweep from
eating the Delivered status. See the class docstring.
"""

import frappe
from frappe import _

DELIVERED = "Delivered"
COMPANY_FLAG = "allow_delivered_task_status"


def company_allows_delivered(company: str | None) -> bool:
	"""True when `company` has the Delivered checkbox ticked."""
	if not company:
		return False
	return bool(frappe.db.get_value("Company", company, COMPANY_FLAG))


def validate(doc, method=None):
	"""Reject "Delivered" on tasks whose company has not opted in."""
	if doc.status != DELIVERED:
		return

	# Task.company is fetch_from project.company and can still be empty on a task
	# with no project, so fall back to the project rather than trusting the field.
	company = doc.company
	if not company and doc.project:
		company = frappe.db.get_value("Project", doc.project, "company")

	if company_allows_delivered(company):
		return

	frappe.throw(
		_('Task status "{0}" is not enabled for company {1}.').format(
			DELIVERED, frappe.bold(company or _("(not set)"))
		)
		+ "<br><br>"
		+ _("Tick {0} on the Company record to enable it.").format(
			frappe.bold(_("Allow Delivered Task Status"))
		),
		title=_("Status Not Allowed"),
	)


@frappe.whitelist()
def is_delivered_allowed(company: str | None = None, project: str | None = None) -> bool:
	"""Used by the Task Client Script to decide whether to show the option.

	Whitelisted because the Client Script runs as the logged-in user; it only reads a
	single boolean off a Company the user already has in front of them.
	"""
	if not company and project:
		company = frappe.db.get_value("Project", project, "company")
	return company_allows_delivered(company)


class TaskStatusMixin:
	"""Keeps "Delivered" from being flipped to "Overdue" by the nightly sweep.

	erpnext Task.update_status() treats only Cancelled and Completed as terminal, so
	anything else with a past exp_end_date becomes Overdue. That list is hardcoded and
	predates our custom status, so a Delivered task silently reverts overnight -
	set_tasks_as_overdue() runs from erpnext/hooks.py daily_maintenance.

	Mixed into the Task controller via hooks.py -> extend_doctype_class. Frappe builds
	the extended class as (mixin, ..., base), so this update_status wins the MRO and
	super() reaches erpnext's. Deliberately NOT a copy of the core logic: everything
	except the extra terminal status still comes from erpnext, so upstream changes to
	the overdue rule keep applying.

	Not a doc_event: update_status() calls db_set() directly and never runs validate,
	so there is no hook that fires on this path.
	"""

	def update_status(self):
		if self.status == DELIVERED:
			return

		super().update_status()
