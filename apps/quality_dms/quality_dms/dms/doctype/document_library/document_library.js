// Copyright (c) 2026, Quality Team and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Library", {
	refresh(frm) {
		// Force display of the clear button for mandatory Link fields
		const fields = ['type', 'category', 'department', 'project'];
		const force_clear_btn = () => {
			fields.forEach(f => {
				if(frm.doc[f]) {
					frm.fields_dict[f].$wrapper.find('.btn-clear').removeClass('hide').attr('style', 'display: block !important');
				}
			});
		};

		frm.$wrapper.on('mouseenter click keyup focus', '.control-input', force_clear_btn);
		setTimeout(force_clear_btn, 500);

		// ── Check-out indicator ──────────────────────────────────────────────
		if (frm.doc.checked_out_by) {
			let ts = frm.doc.checked_out_on
				? frappe.datetime.str_to_user(frm.doc.checked_out_on)
				: '';
			frm.set_intro(
				__("Checked out by {0}{1}", [
					frm.doc.checked_out_by,
					ts ? __(" on {0}", [ts]) : ""
				]),
				"orange"
			);
		}

		// ── File management section ──────────────────────────────────────────
		if (frm.doc.file) {
			frm.add_custom_button(__("Preview"), function() {
				_log_and_preview(frm);
			}, __("File"));

			frm.add_custom_button(__("Download"), function() {
				frappe.call({
					method: "quality_dms.dms.api.log_file_download",
					args: { document: frm.docname },
				});
				let a = document.createElement('a');
				a.href = frm.doc.file;
				a.download = '';
				a.target = '_blank';
				a.click();
			}, __("File"));
		}

		// ── Unified document workspace: preview + all versions + audit history ─
		// Rendered inline in the form itself (not a popup) so the reviewer never
		// has to leave the document to see prior files or who touched them.
		_render_document_workspace(frm);

		if (frm.doc.file_doc) {
			frm.add_custom_button(__("Open in File Manager"), function() {
				frappe.set_route('Form', 'File', frm.doc.file_doc);
			}, __("File"));
		}

		// ── Check-out / Check-in buttons ─────────────────────────────────────
		if (frm.doc.docstatus === 1 && frm.doc.status === "Published") {
			if (!frm.doc.checked_out_by) {
				frm.add_custom_button(__("Check Out"), function() {
					frappe.call({
						method: "run_doc_method",
						args: { method: "check_out", dt: frm.doctype, dn: frm.docname },
						callback: function(r) {
							if (r.message) frm.reload_doc();
						}
					});
				}, __("File"));
			} else {
				let can_checkin =
					frm.doc.checked_out_by === frappe.session.user ||
					frappe.user.has_role("System Manager");
				if (can_checkin) {
					frm.add_custom_button(__("Check In"), function() {
						frappe.call({
							method: "run_doc_method",
							args: { method: "check_in", dt: frm.doctype, dn: frm.docname },
							callback: function(r) {
								if (r.message) frm.reload_doc();
							}
						});
					}, __("File"));
				}
			}
		}

		// ── Force Delete (admin-only, any workflow stage) ────────────────────
		// The workflow only offers Mark as Obsolete/Archive from Published, with
		// no path back to a cancellable state, so a plain Cancel-then-Delete is
		// unreachable from the UI. This calls the whitelisted escape hatch that
		// still enforces link integrity and always writes the audit row.
		if (!frm.is_new() && (frappe.user.has_role("DMS Admin") || frappe.user.has_role("System Manager"))) {
			frm.add_custom_button(__("Force Delete"), function() {
				frappe.confirm(
					__("This permanently deletes {0} regardless of its current workflow stage. This cannot be undone. Continue?", [frm.docname]),
					function() {
						frappe.call({
							method: "quality_dms.dms.api.force_delete_document",
							args: { document_name: frm.docname },
							freeze: true,
							freeze_message: __("Deleting..."),
							callback: function(r) {
								if (r.message && r.message.deleted) {
									frappe.show_alert({ message: __("Document deleted"), indicator: "green" });
									frappe.set_route("List", "Document Library");
								}
							}
						});
					}
				);
			}, __("Actions"));
		}

		// ── Workflow action buttons ──────────────────────────────────────────
		if (frm.doc.workflow_state === "Published") {
			frm.add_custom_button(__("Create New Version"), function() {
				frappe.prompt({
					label: 'Reason for Revision',
					fieldname: 'reason',
					fieldtype: 'Text Editor',
					reqd: 1
				}, (values) => {
					frappe.call({
						method: "run_doc_method",
						args: { method: "request_revision", dt: frm.doctype, dn: frm.docname, args: JSON.stringify({ reason: values.reason }) },
						callback: function(r) {
							if (r.message) {
								frappe.set_route('Form', 'Document Request', r.message);
								frappe.show_alert({
									message: __("Revision request {0} created — once an approver signs off, the new version's draft will appear in this document's version list.", [r.message]),
									indicator: 'green'
								}, 7);
							}
						}
					});
				}, __('Create New Version'), __('Submit'));
			}, __("Actions"));

			frm.add_custom_button(__("Acknowledge Document"), function() {
				frappe.prompt({
					label: 'Draw your E-Signature',
					fieldname: 'e_signature',
					fieldtype: 'Signature',
					reqd: 1
				}, (values) => {
					frappe.call({
						method: "quality_dms.dms.api.acknowledge_document",
						args: {
							document: frm.doc.name,
							e_signature: values.e_signature
						},
						callback: function(r) {
							if (r.message) {
								frappe.msgprint(__("Document Acknowledged with E-Signature Successfully"));
							}
						}
					});
				}, __('E-Signature Required'), __('Sign and Acknowledge'));
			}, __("Actions"));
		}
	},

	before_workflow_action: function(frm) {
		// E-signature is required only at the approval state; every other
		// transition proceeds without the signature dialog.
		if (frm.doc.workflow_state !== "Pending Approval") {
			return Promise.resolve();
		}
		return new Promise(function(resolve, reject) {
			const action = frm.selected_workflow_action || __("Workflow Action");
			let signed = false;

			function cancel() {
				frappe.dom.unfreeze();
				reject();
			}

			frappe.call({
				method: "quality_dms.dms.api.get_current_user_info",
				callback: function(r) {
					const info = r.message || {};

					const d = new frappe.ui.Dialog({
						title: __("Electronic Signature — {0}", [action]),
						fields: [
							{
								label: __("User"),
								fieldname: "user_display",
								fieldtype: "Data",
								read_only: 1,
								default: info.full_name || frappe.session.user
							},
							{
								fieldname: "col_break",
								fieldtype: "Column Break"
							},
							{
								label: __("Password"),
								fieldname: "password",
								fieldtype: "Password",
								reqd: 1
							},
							{
								fieldname: "sec_break",
								fieldtype: "Section Break",
								label: __("Meaning of Signature")
							},
							{
								label: __("I confirm that"),
								fieldname: "meaning",
								fieldtype: "Small Text",
								reqd: 1,
								default: __("I authorize the action \"{0}\" on document {1}.", [action, frm.docname])
							}
						],
						primary_action_label: __("Sign & Proceed"),
						primary_action: function(values) {
							frappe.call({
								method: "quality_dms.dms.api.verify_and_log_signature",
								args: {
									doctype: frm.doctype,
									docname: frm.docname,
									password: values.password,
									meaning: values.meaning
								},
								freeze: true,
								freeze_message: __("Verifying signature…"),
								callback: function(r) {
									if (r.message && r.message.status === "success") {
										signed = true;
										d.hide();
										resolve();
									}
								},
								error: function() {
									d.hide();
								}
							});
						}
					});

					d.onhide = function() {
						if (!signed) cancel();
					};

					frappe.dom.unfreeze();
					d.show();

					setTimeout(() => {
						d.$wrapper.find('input[data-fieldname="password"]').attr('autocomplete', 'current-password');
						d.$wrapper.find('.password-strength-indicator, .progress, .password-strength, .help-box').hide();
					}, 100);
				},
				error: function() {
					cancel();
				}
			});
		});
	}
});


// ── Helper: preview file in-browser ─────────────────────────────────────────
function _log_and_preview(frm) {
	frappe.call({
		method: "quality_dms.dms.api.log_file_preview",
		args: { document: frm.docname },
	});

	let file_url = frm.doc.file;
	let ext = (file_url || '').split('.').pop().toLowerCase();
	let previewable = ['pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'txt'];

	if (previewable.includes(ext)) {
		let d = new frappe.ui.Dialog({
			title: __("Document Preview — {0}", [frm.doc.title]),
			size: 'extra-large',
		});
		let body = d.get_body();
		let safe_url = frappe.utils.escape_html(file_url);
		if (ext === 'pdf') {
			$(body).html(
				`<iframe src="${safe_url}" style="width:100%;height:80vh;border:none;"></iframe>`
			);
		} else if (['png','jpg','jpeg','gif','bmp','webp','svg'].includes(ext)) {
			$(body).html(
				`<img src="${safe_url}" style="max-width:100%;display:block;margin:auto;" />`
			);
		} else {
			$(body).html(`<iframe src="${safe_url}" style="width:100%;height:80vh;border:none;"></iframe>`);
		}
		d.show();
	} else {
		frappe.msgprint(
			__("Preview is not available for this file type ({0}). Opening in a new tab.", [ext.toUpperCase()]),
			__("File Preview")
		);
		window.open(file_url, '_blank');
	}
}


// ── Helper: inline preview markup for a given file url ───────────────────────
function _preview_markup(file_url) {
	if (!file_url) return `<div class="text-muted">${__('No file attached')}</div>`;
	let ext = file_url.split('.').pop().toLowerCase();
	let safe_url = frappe.utils.escape_html(file_url);
	if (ext === 'pdf') {
		return `<iframe src="${safe_url}" style="width:100%;height:70vh;border:1px solid #d1d8dd;"></iframe>`;
	}
	if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) {
		return `<img src="${safe_url}" style="max-width:100%;max-height:70vh;display:block;margin:auto;" />`;
	}
	return `<div class="text-muted">${__('Preview not available for this file type.')}
		<a href="${safe_url}" data-inline-file="${safe_url}">${__('Open file')}</a></div>`;
}

// ── Helper: render the unified in-form panel — current file, every version of
// this document, and the combined audit trail across all of its versions ─────
function _render_document_workspace(frm) {
	if (frm.is_new()) return;

	// Call by dt/dn (not by sending the whole doc): the server then loads the
	// document fresh and only needs read permission. Sending a submitted doc
	// back makes run_doc_method demand submit permission, which employees
	// don't have.
	const call_doc_method = (method) =>
		frappe.call({
			method: "run_doc_method",
			args: { method: method, dt: frm.doctype, dn: frm.docname },
		});
	frappe.run_serially([
		() => call_doc_method("get_version_family"),
		(r1) => call_doc_method("get_audit_trail").then((r2) => [r1, r2]),
		(prev) => call_doc_method("get_pending_revision_requests").then((r3) => [...prev, r3]),
	]).then(([r1, r2, r3]) => {
		let versions = (r1 && r1.message) || [];
		let audit = (r2 && r2.message) || [];
		let pending = (r3 && r3.message) || [];
		const esc = frappe.utils.escape_html;

		let pending_html = pending.length
			? `<div class="alert alert-warning" style="margin-bottom:12px;">
				${pending.map(p => `
					<div>
						${__('Pending revision request')}
						<a href="#" data-open-request="${esc(p.name)}">${esc(p.name)}</a>
						${__('on')} ${esc(p.reference_document || '')}
						${p.requested_by ? __('by') + ' ' + esc(p.requested_by) : ''}
						— ${frappe.datetime.str_to_user(p.creation)}.
						${__('Its draft version will appear below once approved.')}
					</div>`).join('')}
			</div>`
			: '';

		let version_rows = versions.map(v => {
			let badge = v.is_current
				? `<span class="indicator-pill green">${__('Current')}</span>`
				: `<span class="indicator-pill gray">${esc(v.status || '')}</span>`;
			let file_link = v.file
				? `<a href="#" data-inline-file="${esc(v.file)}" title="${__('Preview this version')}">${esc(v.file.split('/').pop())}</a>`
				: __('No file');
			// Only versions that live as a genuinely separate legacy record
			// (created before the single-record revision model) are navigable —
			// current-model versions are snapshots on this same document.
			let title_cell = v.linked_record
				? `<a href="#" data-open-doc="${esc(v.name)}">${esc(v.title || v.name)}</a>`
				: esc(v.title || v.name);
			return `
				<tr${v.is_current ? ' style="background:#f3fbf5;"' : ''}>
					<td>${badge}</td>
					<td>${title_cell}</td>
					<td>${esc(v.version || '')}</td>
					<td>${esc(v.document_number || '')}</td>
					<td>${file_link}</td>
					<td>${frappe.datetime.str_to_user(v.creation)}</td>
					<td>${esc(v.owner || '')}</td>
				</tr>`;
		}).join('');

		let audit_rows = audit.map(a => `
			<tr>
				<td>${frappe.datetime.str_to_user(a.timestamp)}</td>
				<td>${esc(a.document || '')}</td>
				<td>${esc(a.action || '')}</td>
				<td>${esc(a.user || '')}</td>
				<td>${esc(a.ip_address || '')}</td>
			</tr>`).join('');

		let html = `
			<div class="dms-unified-workspace">
				${pending_html}
				<div class="dms-preview-pane" style="margin-bottom:16px;">
					${_preview_markup(frm.doc.file)}
				</div>
				<h6>${__('All Versions')} (${versions.length})</h6>
				<table class="table table-bordered table-sm">
					<thead style="background:#f8f9fa;">
						<tr>
							<th>${__('Status')}</th>
							<th>${__('Title')}</th>
							<th>${__('Version')}</th>
							<th>${__('Document Number')}</th>
							<th>${__('File')}</th>
							<th>${__('Created')}</th>
							<th>${__('Owner')}</th>
						</tr>
					</thead>
					<tbody>${version_rows || `<tr><td colspan="7" class="text-muted">${__('No versions found')}</td></tr>`}</tbody>
				</table>
				<h6 style="margin-top:16px;">${__('Audit History')} (${audit.length})</h6>
				<table class="table table-bordered table-sm">
					<thead style="background:#f8f9fa;">
						<tr>
							<th>${__('Timestamp')}</th>
							<th>${__('Document')}</th>
							<th>${__('Action')}</th>
							<th>${__('User')}</th>
							<th>${__('IP Address')}</th>
						</tr>
					</thead>
					<tbody>${audit_rows || `<tr><td colspan="5" class="text-muted">${__('No audit entries found')}</td></tr>`}</tbody>
				</table>
			</div>`;

		if (frm.dms_workspace_section) {
			frm.dms_workspace_section.remove();
		}
		let panel_title = frm.doc.document_number
			? __("Document {0} — Versions & Audit History", [frm.doc.document_number])
			: __("Document, Versions & Audit History");
		frm.dms_workspace_section = frm.dashboard.add_section(html, panel_title);

		frm.dms_workspace_section.on('click', '[data-open-doc]', function(e) {
			e.preventDefault();
			frappe.set_route('Form', 'Document Library', $(this).attr('data-open-doc'));
		});

		frm.dms_workspace_section.on('click', '[data-open-request]', function(e) {
			e.preventDefault();
			frappe.set_route('Form', 'Document Request', $(this).attr('data-open-request'));
		});

		// Any file link (current file or an older version) previews inline in
		// the same panel instead of opening a new browser tab.
		frm.dms_workspace_section.on('click', '[data-inline-file]', function(e) {
			e.preventDefault();
			let file_url = $(this).attr('data-inline-file');
			frm.dms_workspace_section.find('.dms-preview-pane').html(_preview_markup(file_url));
			frappe.utils.scroll_to(frm.dms_workspace_section.find('.dms-preview-pane'), true, 20);
		});
	});
}
