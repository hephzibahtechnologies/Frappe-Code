# Copyright (c) 2026, Quality Team and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DMSTrainingAssignmentRule(Document):
	pass


def _get_matching_rules(document_category, document_type):
	"""Active rules whose match conditions are blank (match-all) or equal to
	the published document's category/type. Onboarding-only rules (curriculum
	set) are excluded here — they're applied via the Employee.after_insert
	hook instead, not on document publish."""
	rules = frappe.get_all(
		"DMS Training Assignment Rule",
		filters={"active": 1},
		fields=[
			"name", "document_category", "document_type", "department", "role",
			"company", "employee_group", "retraining_months", "curriculum",
		],
	)
	matched = []
	for rule in rules:
		if rule.curriculum:
			continue
		if rule.document_category and rule.document_category != document_category:
			continue
		if rule.document_type and rule.document_type != document_type:
			continue
		matched.append(rule)
	return matched


def _resolve_employees(rule):
	"""Resolve the Employees targeted by a single rule's department/role/company/
	employee-group filters. All filters set on the rule must match (AND)."""
	filters = {"status": "Active"}
	if rule.department:
		filters["department"] = rule.department
	if rule.company:
		filters["company"] = rule.company

	employees = frappe.get_all("Employee", filters=filters, fields=["name", "user_id"])

	if rule.employee_group:
		group_members = set(
			frappe.get_all(
				"Employee Group Table",
				filters={"parenttype": "Employee Group", "parent": rule.employee_group},
				pluck="employee",
			)
		)
		employees = [e for e in employees if e.name in group_members]

	if not rule.role:
		return [e.name for e in employees]

	users_with_role = set(
		frappe.get_all(
			"Has Role",
			filters={"role": rule.role, "parenttype": "User"},
			pluck="parent",
		)
	)
	return [e.name for e in employees if e.user_id and e.user_id in users_with_role]


def _employee_matches_rule(employee, rule):
	if rule.department and employee.department != rule.department:
		return False
	if rule.company and employee.company != rule.company:
		return False
	if rule.employee_group and not frappe.db.exists(
		"Employee Group Table",
		{"parenttype": "Employee Group", "parent": rule.employee_group, "employee": employee.name},
	):
		return False
	if rule.role:
		if not employee.user_id:
			return False
		if not frappe.db.exists("Has Role", {"parent": employee.user_id, "role": rule.role, "parenttype": "User"}):
			return False
	return True


def apply_onboarding_rules(doc, method=None):
	"""Auto-assign onboarding curricula to a newly created Employee, based on
	active DMS Training Assignment Rules that have an Onboarding Curriculum
	set and whose Department/Role filters match this employee. Registered as
	the Employee.after_insert doc_event (see hooks.py), so `doc` is the
	Employee document itself."""
	employee_name = doc.name if hasattr(doc, "name") else doc
	employee = frappe.db.get_value(
		"Employee", employee_name, ["name", "department", "company", "user_id", "status"], as_dict=True
	)
	if not employee or employee.status != "Active":
		return

	rules = frappe.get_all(
		"DMS Training Assignment Rule",
		filters={"active": 1},
		fields=["name", "department", "role", "company", "employee_group", "curriculum"],
	)

	for rule in rules:
		if not rule.curriculum:
			continue
		if not _employee_matches_rule(employee, rule):
			continue
		try:
			curriculum = frappe.get_doc("DMS Curriculum", rule.curriculum)
			if not curriculum.active:
				continue
			curriculum.assign_to_employee(employee.name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"DMS Training: onboarding rule {rule.name} failed for employee {employee.name}",
			)


def apply_rules(training_record):
	"""Auto-assign employees to a freshly-created Draft DMS Training Record based
	on active DMS Training Assignment Rules. Called from
	Document Library._create_training_record() right after the training record
	is created; safe to call multiple times since assignment itself is
	idempotent (assign_employees skips employees already on the record)."""
	if isinstance(training_record, str):
		trn = frappe.get_doc("DMS Training Record", training_record)
	else:
		trn = training_record

	if not trn.document:
		return

	category, doc_type = frappe.db.get_value(
		"Document Library", trn.document, ["category", "type"]
	)

	rules = _get_matching_rules(category, doc_type)
	if not rules:
		return

	employee_ids = set()
	retraining_months = None
	for rule in rules:
		try:
			employee_ids.update(_resolve_employees(rule))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"DMS Training: failed to resolve employees for rule {rule.name}",
			)
		if rule.retraining_months and not retraining_months:
			retraining_months = rule.retraining_months

	if not employee_ids:
		return

	try:
		if retraining_months and not trn.retraining_months:
			trn.retraining_months = retraining_months
			trn.save(ignore_permissions=True)
		# Stage the matched employees as "Suggested" candidates on the record
		# rather than assigning them outright. A manager then reviews the list
		# and assigns the ones they choose (see DMSTrainingRecord.assign_employees).
		trn._stage_employees(sorted(employee_ids))
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"DMS Training: auto-assignment failed for {trn.name}",
		)
