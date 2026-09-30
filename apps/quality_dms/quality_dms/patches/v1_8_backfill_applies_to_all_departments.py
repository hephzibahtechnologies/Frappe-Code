# Copyright (c) 2026, Quality Team and contributors
# Patch: Documents were previously marked "visible to every department" by
# pointing their department Link at a literal "All Departments" record — an
# ad-hoc convention, not a real permission rule. Now that department-scoped
# permissions are enforced (see quality_dms.dms.api), that convention would
# make those documents invisible to everyone but System Manager. Back-fill
# the new applies_to_all_departments checkbox for any document still using
# that sentinel so existing visibility is preserved.

import frappe


def execute():
	if not frappe.db.exists("Department", "All Departments"):
		return

	frappe.db.set_value(
		"Document Library",
		{"department": "All Departments", "applies_to_all_departments": 0},
		"applies_to_all_departments",
		1,
	)
	frappe.db.commit()
