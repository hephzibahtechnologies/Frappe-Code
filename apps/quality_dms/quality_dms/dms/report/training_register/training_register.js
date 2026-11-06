// Fieldnames mirror HIGHLIGHT_FIELDS in training_register.py (the two date
// columns the paper register highlights yellow).
const TRAINING_REGISTER_HIGHLIGHT = ["date_of_completion", "next_due_date"];

frappe.query_reports["Training Register"] = {
	filters: [
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "training_type",
			label: __("Training Type"),
			fieldtype: "Link",
			options: "Document Category",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Completed", "In Progress", "Overdue", "Failed", "Excused"],
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && TRAINING_REGISTER_HIGHLIGHT.includes(column.fieldname)) {
			value = `<div style="background-color: #ffff00; color: #000; margin: -4px -8px; padding: 4px 8px;">${value || "&nbsp;"}</div>`;
		}
		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Download Excel"), () => {
			const params = {};
			Object.entries(report.get_filter_values() || {}).forEach(([key, val]) => {
				if (val) params[key] = val;
			});
			window.open(
				frappe.urllib.get_full_url(
					"/api/method/quality_dms.dms.api.export_training_register?" + $.param(params)
				)
			);
		});
	},
};
