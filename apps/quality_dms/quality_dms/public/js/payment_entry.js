// Payment Entry: show the linked Purchase Invoice's expense category directly
// on this form -- without this, the category is only visible by opening the
// Purchase Invoice separately. Read-only summary only; never edits anything.
frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		render_category_summary(frm);
	},
	references(frm) {
		render_category_summary(frm);
	},
});

function render_category_summary(frm) {
	const $wrapper = frm.fields_dict.dms_expense_category_summary?.$wrapper;
	if (!$wrapper) return;

	const pi_names = (frm.doc.references || [])
		.filter((r) => r.reference_doctype === "Purchase Invoice" && r.reference_name)
		.map((r) => r.reference_name);

	if (frm.doc.payment_type !== "Pay" || !pi_names.length) {
		$wrapper.empty();
		return;
	}

	// frappe.client.get_list silently strips fields on child-table doctypes
	// (e.g. Purchase Invoice Item) -- fetch each parent Purchase Invoice
	// instead, which returns its full item rows regardless.
	Promise.all(
		pi_names.map((name) =>
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "Purchase Invoice", name },
			}).then((r) => r.message)
		)
	).then((invoices) => {
		const rows = invoices.flatMap((pi) => (pi?.items || []).map((item) => ({
			expense_account: item.expense_account,
			description: item.description,
		})));
		if (!rows.length) {
			$wrapper.empty();
			return;
		}
		$wrapper.html(`
			<div class="dms-expense-category-summary" style="
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: 6px;
				padding: 10px 12px;
				background: var(--control-bg, #f7f8f9);
				margin-bottom: 8px;
			">
				${rows
					.map(
						(row) => `
					<div style="display: flex; justify-content: space-between; gap: 12px; font-size: 12px; padding: 2px 0;">
						<span class="text-muted">${__("Category")}</span>
						<a href="/app/account/${encodeURIComponent(row.expense_account)}">${frappe.utils.escape_html(row.expense_account)}</a>
					</div>
				`
					)
					.join("")}
			</div>
		`);
	});
}
