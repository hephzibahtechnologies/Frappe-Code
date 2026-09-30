frappe.ui.form.on("DMS Training Record", {
	refresh(frm) {
		frm.trigger("setup_status_indicator");
		frm.trigger("setup_action_buttons");
		frm.trigger("setup_view_document");
		frm.trigger("render_document_preview");
		frm.trigger("render_training_video");
		frm.trigger("setup_my_certificate");
	},

	render_training_video(frm) {
		// Embed the document's training video (if any) as an inline player so the
		// employee can watch it on the training record, just like the document.
		const field = frm.get_field("training_video_preview");
		if (!field) return;
		if (frm.doc.__islocal || !frm.doc.document) {
			field.$wrapper.empty();
			return;
		}
		frappe.db.get_value("Document Library", frm.doc.document, ["training_video", "training_video_url"]).then((r) => {
			const file = r.message && r.message.training_video;
			const link = r.message && r.message.training_video_url;

			const player_style = "width:100%; max-height:75vh; aspect-ratio:16/9; border:1px solid var(--border-color); border-radius:var(--border-radius-md); background:#000;";

			// 1) External link takes precedence.
			if (link) {
				const yt = dms_youtube_id(link);
				if (yt) {
					// Fully locked YouTube: native controls hidden (controls=0),
					// driven by our own play/pause + seek; a full-surface overlay
					// blocks every YouTube action (share, settings, CC, logo,
					// "More videos"). See dms_render_locked_youtube.
					dms_render_locked_youtube(field, yt);
					return;
				}
				const embed = dms_video_embed_url(link);  // Vimeo etc.
				if (embed) {
					field.$wrapper.html(
						`<iframe src="${frappe.utils.escape_html(embed)}" allow="autoplay; encrypted-media"
							referrerpolicy="strict-origin-when-cross-origin"
							style="${player_style}" oncontextmenu="return false;"></iframe>`
					);
					return;
				}
				const safe = frappe.utils.escape_html(link);
				field.$wrapper.html(
					`<a class="btn btn-sm btn-default" href="${safe}" target="_blank" rel="noopener">
						${frappe.utils.icon("play", "sm")} ${__("Open training video")}</a>`
				);
				return;
			}

			// 2) Uploaded file — native HTML5 player.
			if (file) {
				const url = frappe.utils.escape_html(file);
				const ext = file.split("?")[0].split(".").pop().toLowerCase();
				if (["mp4", "webm", "ogg", "mov", "m4v"].includes(ext)) {
					// Locked-down player: only play/pause/seek/volume — no download,
					// no fullscreen, no picture-in-picture, no playback-rate, no
					// remote cast, and no right-click "save/copy" menu.
					field.$wrapper.html(
						`<video controls preload="metadata"
							controlslist="nodownload nofullscreen noremoteplayback noplaybackrate"
							disablepictureinpicture disableremoteplayback
							oncontextmenu="return false;" style="${player_style}">
							<source src="${url}">
							${__("Your browser cannot play this video.")}
						</video>`
					);
				} else {
					field.$wrapper.html(
						`<a class="btn btn-sm btn-default" href="${url}" target="_blank" rel="noopener">
							${frappe.utils.icon("play", "sm")} ${__("Open training video")}</a>`
					);
				}
				return;
			}

			field.$wrapper.html(
				`<div class="text-muted">${__("No training video attached to this document.")}</div>`
			);
		});
	},

	setup_my_certificate(frm) {
		// Offer the logged-in employee their own personal certificate. A manager
		// can now verify (and certificate) one employee at a time via
		// "Verify Employee", so this must not wait for the whole record to reach
		// Verified/Closed -- get_my_certificate already returns null until this
		// employee's own row actually has a certificate.
		if (frm.doc.__islocal) return;
		frappe.call({
			method: "run_doc_method",
			args: { method: "get_my_certificate", dt: frm.doctype, dn: frm.docname },
		}).then((r) => {
			const url = r && r.message;
			if (url) {
				frm.add_custom_button(__("My Certificate"), () => {
					window.open(url, "_blank");
				});
			}
		});
	},

	setup_view_document(frm) {
		// Give everyone (esp. the trainee) a one-click way to open and read the
		// document file this training is about, before they take the quiz.
		if (frm.doc.__islocal || !frm.doc.document) return;
		frm.add_custom_button(__("View Document"), () => {
			// The document is embedded on this form — expand and scroll to it.
			const section = frm.get_field("section_document_preview");
			if (section && section.collapse) section.collapse(false);
			frm.scroll_to_field("document_preview");
		});
	},

	render_document_preview(frm) {
		// Embed the linked document inside the training record so the employee
		// can read it without leaving the form.
		const field = frm.get_field("document_preview");
		if (!field) return;
		if (frm.doc.__islocal || !frm.doc.document) {
			field.$wrapper.empty();
			return;
		}
		frappe.db.get_value("Document Library", frm.doc.document, ["file", "title"]).then((r) => {
			const file = r.message && r.message.file;
			const title = (r.message && r.message.title) || frm.doc.document;
			if (!file) {
				field.$wrapper.html(
					`<div class="text-muted">${__("No file is attached to the linked document ({0}).", [
						frappe.utils.escape_html(frm.doc.document),
					])}</div>`
				);
				return;
			}
			const url = frappe.utils.escape_html(file);
			const ext = file.split("?")[0].split(".").pop().toLowerCase();
			const open_link = `<div class="margin-bottom">
				<a class="btn btn-xs btn-default" href="${url}" target="_blank" rel="noopener">
					${frappe.utils.icon("external-link", "xs")} ${__("Open in New Tab")}
				</a>
			</div>`;
			let body;
			if (ext === "pdf") {
				body = `<iframe src="${url}#toolbar=0" title="${frappe.utils.escape_html(title)}"
					style="width:100%; height:75vh; border:1px solid var(--border-color); border-radius:var(--border-radius-md); background:#fff;"></iframe>`;
			} else if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"].includes(ext)) {
				body = `<img src="${url}" alt="${frappe.utils.escape_html(title)}"
					style="max-width:100%; border:1px solid var(--border-color); border-radius:var(--border-radius-md);">`;
			} else if (["txt", "md", "html", "htm"].includes(ext)) {
				body = `<iframe src="${url}" title="${frappe.utils.escape_html(title)}"
					style="width:100%; height:60vh; border:1px solid var(--border-color); border-radius:var(--border-radius-md); background:#fff;"></iframe>`;
			} else {
				body = `<div class="text-muted">${__(
					"This file type ({0}) cannot be previewed in the browser. Use the button above to download/open it.",
					[frappe.utils.escape_html(ext)]
				)}</div>`;
			}
			field.$wrapper.html(open_link + body);
		});
	},

	setup_status_indicator(frm) {
		const color = {
			"Draft": "gray",
			"Assigned": "blue",
			"In Progress": "yellow",
			"Completed": "green",
			"Overdue": "red",
			"Verified": "green",
			"Closed": "darkgrey",
			"Cancelled": "red",
		}[frm.doc.status] || "gray";
		frm.page.set_indicator(frm.doc.status, color);
	},

	setup_action_buttons(frm) {
		if (frm.doc.__islocal) return;

		const is_manager = frappe.user.has_role(["System Manager"]);
		const status = frm.doc.status;

		if (is_manager && ["Draft", "Assigned"].includes(status)) {
			frm.add_custom_button(__("Assign Employees"), () => {
				frm.trigger("open_assign_dialog");
			}, __("Actions"));

			frm.add_custom_button(__("Assign by Department / Group / Company"), () => {
				frm.trigger("open_assign_by_scope_dialog");
			}, __("Actions"));

			const suggested = (frm.doc.employees || []).filter((r) => r.status === "Suggested");
			if (suggested.length) {
				frm.add_custom_button(__("Assign Suggested ({0})", [suggested.length]), () => {
					frm.trigger("open_assign_suggested_dialog");
				}, __("Actions"));
			}
		}

		if (is_manager && !["Closed", "Cancelled"].includes(status)) {
			const verifiable = (frm.doc.employees || []).filter(
				(r) => r.acknowledged && !r.employee_verified_by
			);
			if (verifiable.length) {
				frm.add_custom_button(__("Verify Employee ({0})", [verifiable.length]), () => {
					frappe.prompt(
						[
							{
								label: __("Employee"),
								fieldname: "row_name",
								fieldtype: "Select",
								reqd: 1,
								options: verifiable.map((r) => ({
									label: `${r.employee_name || r.employee} (${r.assessment_score || 0})`,
									value: r.name,
								})),
							},
							{
								label: __("Verification Notes"),
								fieldname: "notes",
								fieldtype: "Text",
							},
						],
						(vals) => {
							frm.call("verify_employee", { row_name: vals.row_name, notes: vals.notes || null }).then(() => {
								frm.reload_doc();
								frappe.show_alert({ message: __("Employee training verified."), indicator: "green" });
							});
						},
						__("Verify Employee Training"),
						__("Verify")
					);
				}, __("Actions"));
			}
		}

		if (is_manager && status === "Completed") {
			frm.add_custom_button(__("Verify Completion"), () => {
				frappe.prompt(
					{
						label: __("Verification Notes"),
						fieldname: "notes",
						fieldtype: "Text",
					},
					(vals) => {
						frm.call("verify_completion", { notes: vals.notes || null }).then(() => {
							frm.reload_doc();
							frappe.show_alert({ message: __("Training record verified."), indicator: "green" });
						});
					},
					__("Verify Training Completion"),
					__("Verify")
				);
			}, __("Actions"));
		}

		if (is_manager && status === "Completed" && frm.doc.verified_by && !frm.doc.secondary_verified_by) {
			frm.add_custom_button(__("Countersign Verification"), () => {
				frappe.prompt(
					{
						label: __("Countersignature Notes"),
						fieldname: "notes",
						fieldtype: "Text",
					},
					(vals) => {
						frm.call("countersign_completion", { notes: vals.notes || null }).then(() => {
							frm.reload_doc();
							frappe.show_alert({ message: __("Training record countersigned and verified."), indicator: "green" });
						});
					},
					__("Countersign Training Verification"),
					__("Countersign")
				);
			}, __("Actions"));
		}

		if (is_manager && status === "Verified") {
			frm.add_custom_button(__("Close Record"), () => {
				frappe.prompt(
					{
						label: __("Closure Notes"),
						fieldname: "notes",
						fieldtype: "Text",
					},
					(vals) => {
						frm.call("close_record", { notes: vals.notes || null }).then(() => {
							frm.reload_doc();
							frappe.show_alert({ message: __("Training record closed."), indicator: "green" });
						});
					},
					__("Close Training Record"),
					__("Close")
				);
			}, __("Actions"));
		}

		if (["Assigned", "In Progress", "Overdue"].includes(status)) {
			frm.add_custom_button(__("Sign My Acknowledgement"), () => {
				frm.trigger("open_sign_dialog");
			});
		}

		if (is_manager && ["Assigned", "In Progress", "Overdue"].includes(status)) {
			frm.add_custom_button(__("Complete on Behalf of Employee"), () => {
				frm.trigger("open_proxy_complete_dialog");
			}, __("Actions"));
		}

		const failed_rows = (frm.doc.employees || []).filter(
			(r) => r.quiz_attempts && !r.acknowledged && !r.retake_allowed
		);
		if (is_manager && failed_rows.length) {
			frm.add_custom_button(__("Allow Quiz Retake ({0})", [failed_rows.length]), () => {
				frm.trigger("open_allow_retake_dialog");
			}, __("Actions"));
		}

		if (is_manager && ["Verified", "Closed"].includes(status)) {
			frm.add_custom_button(__("Record Effectiveness Check"), () => {
				frm.trigger("open_effectiveness_dialog");
			}, __("Actions"));
		}

		if (is_manager && !["Closed", "Cancelled"].includes(status)) {
			frm.add_custom_button(__("Cancel"), () => {
				frappe.prompt(
					{
						label: __("Reason for Cancellation"),
						fieldname: "reason",
						fieldtype: "Text",
						reqd: 1,
					},
					(vals) => {
						frm.call("cancel_record", { reason: vals.reason }).then(() => {
							frm.reload_doc();
							frappe.show_alert({ message: __("Training record cancelled."), indicator: "orange" });
						});
					},
					__("Cancel Training Record"),
					__("Cancel Record")
				);
			}, __("Actions"));
		}
	},

	open_sign_dialog(frm) {
		// The server resolves the logged-in user's own row (and any quiz), so the
		// employee never picks from other people's rows.
		frm.call("get_my_acknowledgement_context").then((r) => {
			if (!r.message) return;
			const { row_name, quiz, retake_locked, last_score } = r.message;
			if (retake_locked) {
				frappe.msgprint({
					title: __("Quiz Locked"),
					indicator: "orange",
					message: __(
						"You did not pass the quiz (your score: {0}%). Please ask your manager to allow a retake before trying again.",
						[last_score != null ? Math.round(last_score) : "—"]
					),
				});
				return;
			}
			if (quiz && quiz.questions && quiz.questions.length) {
				dms_open_quiz_dialog(frm, row_name, quiz);
			} else {
				dms_open_password_dialog(frm, row_name);
			}
		});
	},

	open_proxy_complete_dialog(frm) {
		const rows = (frm.doc.employees || [])
			.filter((r) => !r.acknowledged && r.status !== "Suggested")
			.map((r) => ({ label: `${r.employee_name || r.employee} (${r.status})`, value: r.name }));
		const d = new frappe.ui.Dialog({
			title: __("Complete Training on Behalf of Employee"),
			fields: [
				{
					label: __("Employee Row"),
					fieldname: "row_name",
					fieldtype: "Select",
					options: rows,
					reqd: 1,
				},
				{
					label: __("Reason"),
					fieldname: "reason",
					fieldtype: "Small Text",
					reqd: 1,
					description: __("e.g. employee has left the company / no system access — record why you are completing this on their behalf."),
				},
			],
			primary_action_label: __("Complete"),
			primary_action(values) {
				frm.call("proxy_complete_acknowledgement", {
					row_name: values.row_name,
					reason: values.reason,
				}).then(() => {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({ message: __("Training marked complete on employee's behalf."), indicator: "green" });
				});
			},
		});
		d.show();
	},

	open_allow_retake_dialog(frm) {
		const rows = (frm.doc.employees || [])
			.filter((r) => r.quiz_attempts && !r.acknowledged && !r.retake_allowed)
			.map((r) => ({
				label: `${r.employee_name || r.employee} — scored ${r.assessment_score != null ? Math.round(r.assessment_score) : "—"}% (${r.quiz_attempts} attempt(s))`,
				value: r.name,
			}));
		if (!rows.length) {
			frappe.msgprint(__("No employees are currently waiting for a quiz retake."));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("Allow Quiz Retake"),
			fields: [
				{
					label: __("Employee Row"),
					fieldname: "row_name",
					fieldtype: "Select",
					options: rows,
					reqd: 1,
					description: __("The employee will be able to retake the quiz once. The grant is used up on their next submission."),
				},
			],
			primary_action_label: __("Allow Retake"),
			primary_action(values) {
				frm.call("allow_quiz_retake", { row_name: values.row_name }).then((r) => {
					d.hide();
					frm.reload_doc();
					if (r && r.message) {
						frappe.show_alert({
							message: __("Retake allowed for {0}.", [r.message.employee]),
							indicator: "green",
						});
					}
				});
			},
		});
		d.show();
	},

	open_effectiveness_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Record Training Effectiveness Check"),
			fields: [
				{
					label: __("Effectiveness Rating"),
					fieldname: "rating",
					fieldtype: "Select",
					options: ["Effective", "Partially Effective", "Not Effective"],
					reqd: 1,
				},
				{
					label: __("Notes"),
					fieldname: "notes",
					fieldtype: "Text",
				},
			],
			primary_action_label: __("Save"),
			primary_action(values) {
				frm.call("verify_effectiveness", {
					rating: values.rating,
					notes: values.notes || null,
				}).then(() => {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({ message: __("Effectiveness check recorded."), indicator: "green" });
				});
			},
		});
		d.show();
	},

	open_assign_suggested_dialog(frm) {
		const suggested = (frm.doc.employees || []).filter((r) => r.status === "Suggested");
		const options = suggested.map((r) => ({
			label: `${r.employee_name || r.employee}${r.department ? " — " + r.department : ""}`,
			value: r.employee,
		}));
		const d = new frappe.ui.Dialog({
			title: __("Assign Suggested Employees"),
			fields: [
				{
					fieldname: "select_all",
					fieldtype: "Check",
					label: __("Select all"),
					onchange() {
						const checked = d.get_value("select_all");
						d.set_value("employees", checked ? options.map((o) => o.value) : []);
					},
				},
				{
					label: __("Suggested Employees"),
					fieldname: "employees",
					fieldtype: "MultiCheck",
					options: options,
					columns: 1,
				},
				{
					label: __("Due Date"),
					fieldname: "due_date",
					fieldtype: "Date",
					default: frm.doc.due_date,
					description: __("Leave blank to inherit the training record's current due date."),
				},
			],
			primary_action_label: __("Assign Selected"),
			primary_action(values) {
				const emp_ids = values.employees || [];
				if (!emp_ids.length) {
					frappe.msgprint(__("Please select at least one employee to assign."));
					return;
				}
				frm.call("assign_employees", {
					employee_ids: emp_ids,
					due_date: values.due_date || null,
				}).then((r) => {
					d.hide();
					frm.reload_doc();
					if (r && r.message) {
						const { added, total } = r.message;
						frappe.show_alert({
							message: __("{0} employee(s) assigned & notified. Total assigned: {1}.", [added, total]),
							indicator: "green",
						});
					}
				});
			},
		});
		d.show();
	},

	open_assign_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Assign Employees to Training"),
			fields: [
				{
					label: __("Select Employees"),
					fieldname: "employees",
					fieldtype: "Table MultiSelect",
					options: "Employee",
					reqd: 1,
					get_query() {
						return { filters: { status: "Active" } };
					},
				},
				{
					label: __("Due Date"),
					fieldname: "due_date",
					fieldtype: "Date",
					default: frm.doc.due_date,
					description: __("Leave blank to inherit the training record's current due date."),
				},
			],
			primary_action_label: __("Assign"),
			primary_action(values) {
				const emp_ids = (values.employees || []).map((e) => e.value || e);
				if (!emp_ids.length) {
					frappe.msgprint(__("Please select at least one employee."));
					return;
				}
				frm.call("assign_employees", {
					employee_ids: emp_ids,
					due_date: values.due_date || null,
				}).then((r) => {
					d.hide();
					frm.reload_doc();
					if (r && r.message) {
						const { added, total } = r.message;
						frappe.show_alert({
							message: __("{0} employee(s) added. Total assigned: {1}.", [added, total]),
							indicator: "green",
						});
					}
				});
			},
		});
		d.show();
	},

	open_assign_by_scope_dialog(frm) {
		const scope_doctype = { Department: "Department", "Employee Group": "Employee Group", Company: "Company" };

		const d = new frappe.ui.Dialog({
			title: __("Assign by Department / Group / Company"),
			fields: [
				{
					label: __("Scope Type"),
					fieldname: "scope_type",
					fieldtype: "Select",
					options: ["Department", "Employee Group", "Company"],
					default: "Department",
					reqd: 1,
				},
				{
					label: __("Scope Value"),
					fieldname: "scope_value",
					fieldtype: "Link",
					options: "Department",
					reqd: 1,
				},
				{
					label: __("Include sub-departments"),
					fieldname: "include_subdepartments",
					fieldtype: "Check",
					depends_on: "eval:doc.scope_type=='Department'",
				},
				{
					label: __("Due Date"),
					fieldname: "due_date",
					fieldtype: "Date",
					default: frm.doc.due_date,
					description: __("Leave blank to inherit the training record's current due date."),
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "preview",
					fieldtype: "HTML",
					options: `<div class="text-muted dms-scope-preview">${__("Select a scope to see how many employees will be assigned.")}</div>`,
				},
			],
			primary_action_label: __("Assign"),
			primary_action(values) {
				if (!values.scope_value) {
					frappe.msgprint(__("Please select a scope value."));
					return;
				}
				frappe.call({
					method: "quality_dms.dms.doctype.dms_training_record.dms_training_record.assign_by_scope",
					args: {
						training_record: frm.doc.name,
						scope_type: values.scope_type,
						scope_value: values.scope_value,
						due_date: values.due_date || null,
						include_subdepartments: values.include_subdepartments ? 1 : 0,
					},
				}).then((r) => {
					d.hide();
					frm.reload_doc();
					if (r && r.message) {
						const { added, total, matched } = r.message;
						frappe.show_alert({
							message: __("{0} employee(s) assigned ({1} matched the scope). Total assigned: {2}.", [added, matched, total]),
							indicator: "green",
						});
					}
				});
			},
		});

		const $preview = () => d.get_field("preview").$wrapper.find(".dms-scope-preview");

		const update_preview = frappe.utils.debounce(() => {
			const values = d.get_values(true);
			if (!values.scope_type || !values.scope_value) return;
			$preview().text(__("Checking…"));
			frappe.call({
				method: "quality_dms.dms.doctype.dms_training_record.dms_training_record.count_employees_for_scope",
				args: {
					scope_type: values.scope_type,
					scope_value: values.scope_value,
					include_subdepartments: values.include_subdepartments ? 1 : 0,
				},
			}).then((r) => {
				const count = r.message && r.message.count;
				if (count === 0) {
					$preview().removeClass("text-muted").addClass("text-danger").text(__("No active employees match this scope."));
				} else {
					$preview().removeClass("text-danger").addClass("text-muted").text(__("{0} active employee(s) will be assigned.", [count]));
				}
			});
		}, 400);

		d.set_df_property("scope_type", "onchange", () => {
			const scope_type = d.get_value("scope_type");
			d.set_value("scope_value", "");
			d.set_df_property("scope_value", "options", scope_doctype[scope_type] || "Department");
			d.set_df_property("include_subdepartments", "hidden", scope_type !== "Department");
			$preview().removeClass("text-danger").addClass("text-muted").text(__("Select a scope to see how many employees will be assigned."));
		});
		d.fields_dict.scope_value.df.onchange = update_preview;
		d.fields_dict.include_subdepartments.df.onchange = update_preview;

		d.show();
	},
});

// ── Convert a YouTube/Vimeo watch URL to its embeddable iframe URL ─────────────
// Returns null for anything we don't recognise as embeddable.
// Extract a YouTube video id from any common URL form (or null).
function dms_youtube_id(url) {
	if (!url) return null;
	const m = url.trim().match(
		/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/
	);
	return m ? m[1] : null;
}

// Lazy-load the YouTube IFrame Player API once, then run `cb` when ready.
function dms_load_youtube_api(cb) {
	if (window.YT && window.YT.Player) { cb(); return; }
	const prev = window.onYouTubeIframeAPIReady;
	window.onYouTubeIframeAPIReady = function () {
		if (typeof prev === "function") { try { prev(); } catch (e) { /* noop */ } }
		cb();
	};
	if (!document.getElementById("dms-youtube-api")) {
		const s = document.createElement("script");
		s.id = "dms-youtube-api";
		s.src = "https://www.youtube.com/iframe_api";
		document.head.appendChild(s);
	}
}

// Render a locked-down YouTube player: no native chrome, no share/settings/CC/
// logo/"More videos" — only our own Play/Pause and a seek bar. A transparent
// overlay covers the whole video so clicks never reach YouTube, and the end
// screen is masked so related videos never show.
function dms_render_locked_youtube(field, video_id) {
	const $w = field.$wrapper;
	// Tear down any previous player/timer (form refresh re-renders).
	if ($w._dms_yt_timer) { clearInterval($w._dms_yt_timer); $w._dms_yt_timer = null; }
	if ($w._dms_yt_player && $w._dms_yt_player.destroy) { try { $w._dms_yt_player.destroy(); } catch (e) {} }

	const uid = "dms-yt-" + Math.floor(performance.now()) + "-" + video_id;
	$w.html(`
		<div class="dms-yt" style="position:relative; width:100%; aspect-ratio:16/9; background:#000;
			border:1px solid var(--border-color); border-radius:var(--border-radius-md); overflow:hidden;">
			<div id="${uid}" style="position:absolute; inset:0; width:100%; height:100%; pointer-events:none;"></div>
			<div class="dms-yt-block" title="" style="position:absolute; inset:0; z-index:2; cursor:pointer;"></div>
			<div class="dms-yt-end" style="position:absolute; inset:0; z-index:3; display:none;
				background:#000; color:#fff; align-items:center; justify-content:center;">
				<button class="btn btn-sm btn-default dms-yt-replay">${__("Replay")}</button>
			</div>
		</div>
		<div style="display:flex; align-items:center; gap:10px; margin-top:6px;">
			<button class="btn btn-xs btn-default dms-yt-play" style="min-width:70px;">${__("Play")}</button>
			<input type="range" class="dms-yt-seek" min="0" max="100" value="0" step="0.1"
				style="flex:1; cursor:pointer;">
			<span class="dms-yt-time text-muted" style="font-variant-numeric:tabular-nums;">0:00 / 0:00</span>
		</div>
	`);

	const fmt = (s) => {
		s = Math.max(0, Math.floor(s || 0));
		const m = Math.floor(s / 60);
		return `${m}:${String(s % 60).padStart(2, "0")}`;
	};

	dms_load_youtube_api(function () {
		const player = new window.YT.Player(uid, {
			videoId: video_id,
			playerVars: {
				controls: 0, modestbranding: 1, rel: 0, iv_load_policy: 3,
				disablekb: 1, fs: 0, playsinline: 1, showinfo: 0,
			},
			events: {
				onReady: function () {
					const $seek = $w.find(".dms-yt-seek");
					const $time = $w.find(".dms-yt-time");
					const $play = $w.find(".dms-yt-play");
					$w._dms_yt_timer = setInterval(function () {
						if (!player.getDuration) return;
						const dur = player.getDuration() || 0;
						const cur = player.getCurrentTime() || 0;
						if (!$seek[0].dataset.dragging) {
							$seek.attr("max", dur || 100);
							$seek.val(cur);
						}
						$time.text(`${fmt(cur)} / ${fmt(dur)}`);
					}, 500);

					const toggle = function () {
						const st = player.getPlayerState();
						if (st === window.YT.PlayerState.PLAYING) { player.pauseVideo(); }
						else { player.playVideo(); }
					};
					$w.find(".dms-yt-block").on("click", toggle);
					$play.on("click", toggle);
					$seek.on("mousedown touchstart", function () { this.dataset.dragging = "1"; });
					$seek.on("input change", function () {
						player.seekTo(parseFloat(this.value), true);
					});
					$seek.on("mouseup touchend change", function () { delete this.dataset.dragging; });
					$w.find(".dms-yt-replay").on("click", function () {
						$w.find(".dms-yt-end").css("display", "none");
						player.seekTo(0, true); player.playVideo();
					});
				},
				onStateChange: function (e) {
					const $play = $w.find(".dms-yt-play");
					if (e.data === window.YT.PlayerState.PLAYING) $play.text(__("Pause"));
					else $play.text(__("Play"));
					// Mask the end screen so YouTube's related-video grid never shows.
					if (e.data === window.YT.PlayerState.ENDED) {
						$w.find(".dms-yt-end").css("display", "flex");
					}
				},
			},
		});
		$w._dms_yt_player = player;
	});
}

function dms_video_embed_url(url) {
	if (!url) return null;
	url = url.trim();
	// YouTube: youtu.be/ID, youtube.com/watch?v=ID, /embed/ID, /shorts/ID
	// Params: privacy (nocookie via host below), no related videos (rel=0),
	// minimal branding, no fullscreen (fs=0), no keyboard (disablekb=1),
	// no annotations (iv_load_policy=3).
	let m = url.match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
	if (m) {
		const p = "rel=0&modestbranding=1&fs=0&disablekb=1&iv_load_policy=3&playsinline=1";
		return `https://www.youtube-nocookie.com/embed/${m[1]}?${p}`;
	}
	// Vimeo: vimeo.com/ID or player.vimeo.com/video/ID — hide title/byline/portrait, no fullscreen.
	m = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
	if (m) return `https://player.vimeo.com/video/${m[1]}?title=0&byline=0&portrait=0&fullscreen=0&dnt=1`;
	return null;
}

// ── Quiz-taking flow (Option A: in-app desk quiz) ──────────────────────────────
// The row is resolved server-side (get_my_acknowledgement_context) so the
// employee only ever signs their own row. If the linked document has an active
// quiz it is presented; otherwise a plain password e-signature is used.
function dms_open_quiz_dialog(frm, row_name, quiz) {
	const fields = [
		{
			fieldtype: "HTML",
			options: `<p class="text-muted">${__("Answer all questions. You must score {0}% or higher to pass. ({1} question(s))", [quiz.pass_percentage, quiz.questions.length])}</p>`,
		},
	];

	quiz.questions.forEach((q, i) => {
		fields.push({
			label: `${i + 1}. ${frappe.utils.escape_html(q.question_text || "")}`,
			fieldname: `q_${i}`,
			fieldtype: "Select",
			reqd: 1,
			// value is the 1-based option number the server grades against
			options: (q.options || []).map((opt, j) => ({ label: opt, value: String(j + 1) })),
		});
	});

	fields.push({ fieldtype: "Section Break" });
	fields.push({
		label: __("Your Password"),
		fieldname: "password",
		fieldtype: "Password",
		reqd: 1,
		description: __("Re-enter your password to electronically sign this acknowledgement (21 CFR Part 11 style)."),
	});

	const d = new frappe.ui.Dialog({
		title: __("Take Quiz & Sign — {0}", [quiz.title || ""]),
		size: "extra-large",
		fields,
		primary_action_label: __("Submit & Sign"),
		primary_action(values) {
			const answers = {};
			quiz.questions.forEach((q, i) => {
				answers[i] = values[`q_${i}`];
			});
			frm.call("submit_quiz_and_sign", {
				row_name,
				answers: JSON.stringify(answers),
				password: values.password,
			}).then((r) => {
				if (!r.message) return;
				d.hide();
				frm.reload_doc();
				if (r.message.passed) {
					frappe.show_alert({
						message: __("Passed with {0}% — acknowledgement signed.", [Math.round(r.message.score)]),
						indicator: "green",
					});
				} else {
					// Failing attempt is now recorded (submittable), not discarded.
					frappe.msgprint({
						title: __("Quiz Failed — Attempt Recorded"),
						indicator: "red",
						message: r.message.message || __(
							"You scored {0}%. The passing score is {1}%. A manager must allow a retake before you can try again.",
							[Math.round(r.message.score), Math.round(r.message.pass_percentage)]
						),
					});
				}
			});
		},
	});
	d.show();
	// Expand to a near full-page view so a long quiz is comfortable to take.
	d.$wrapper.find(".modal-dialog").css({ "max-width": "96vw", "width": "1100px" });
	d.$wrapper.find(".modal-content").css({ "height": "92vh" });
	d.$wrapper.find(".modal-body").css({ "max-height": "calc(92vh - 130px)", "overflow-y": "auto" });
}

function dms_open_password_dialog(frm, row_name) {
	const d = new frappe.ui.Dialog({
		title: __("Sign Training Acknowledgement"),
		fields: [
			{
				label: __("Assessment Score (if applicable)"),
				fieldname: "assessment_score",
				fieldtype: "Float",
			},
			{
				label: __("Your Password"),
				fieldname: "password",
				fieldtype: "Password",
				reqd: 1,
				description: __("Re-enter your password to electronically sign this acknowledgement (21 CFR Part 11 style)."),
			},
		],
		primary_action_label: __("Sign"),
		primary_action(values) {
			frm.call("sign_acknowledgement", {
				row_name,
				password: values.password,
				assessment_score: values.assessment_score || null,
			}).then(() => {
				d.hide();
				frm.reload_doc();
				frappe.show_alert({ message: __("Acknowledgement signed."), indicator: "green" });
			});
		},
	});
	d.show();
}
