const TARO_METHOD_PREFIX =
	"quality_dms.dms.report.training_assessment_results_register.training_assessment_results_register";
const TARO_ALL_DOCUMENTS = "__all__";

frappe.query_reports["Training Assessment Results Register"] = {
	filters: [
		{
			fieldname: "training_document",
			label: __("Training Document"),
			fieldtype: "Select",
			// Filled from the database in onload().
			options: [],
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "result",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Pass", "Fail", "Pending"],
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
		{
			fieldname: "include_pending",
			label: __("Include employees with no assessment attempts"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "result") {
			if (data.result === "Pass") {
				value = `<span style="color: var(--green-600, #278f5e); font-weight: 600;">${value}</span>`;
			} else if (data.result === "Fail") {
				value = `<span style="color: var(--red-600, #c93a3a); font-weight: 600;">${value}</span>`;
			}
		}
		return value;
	},

	onload(report) {
		// The document list comes from the database, so it is loaded here and
		// the first document is selected: the report opens on a single
		// document (All Documents is opt-in).
		frappe.call({
			method: `${TARO_METHOD_PREFIX}.get_training_documents`,
			callback(r) {
				const documents = r.message || [];
				const filter = report.get_filter("training_document");
				filter.df.options = [{ label: __("All Documents"), value: TARO_ALL_DOCUMENTS }, ...documents];
				// Select controls only rebuild their <option>s through set_options().
				filter.set_options();
				// `filter.value` is the model value (the <select> itself would
				// show "All Documents" first), so a document chosen via the
				// URL is kept and otherwise the first real document is selected.
				if (!filter.value) {
					filter.set_value(documents.length ? documents[0].value : TARO_ALL_DOCUMENTS);
				}
			},
		});

		report.page.add_inner_button(__("Download Excel"), () => {
			const values = report.get_filter_values() || {};
			if (!values.training_document) {
				frappe.msgprint(__("Select a Training Document (or All Documents) first."));
				return;
			}
			const params = {};
			Object.entries(values).forEach(([key, val]) => {
				if (val !== null && val !== undefined && val !== "") params[key] = val;
			});
			// An unticked Check filter is falsy, so send it explicitly.
			params.include_pending = values.include_pending ? 1 : 0;
			window.open(
				frappe.urllib.get_full_url(
					"/api/method/quality_dms.dms.api.export_training_assessment_results_register?" +
						$.param(params)
				)
			);
		});
	},
};
