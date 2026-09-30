frappe.pages["training-analytics"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Training Analytics"),
		single_column: true,
	});

	new TrainingAnalytics(page);
};

class TrainingAnalytics {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.filters = { from_date: null, to_date: null, department: null };
		this.departments = [];
		this.empEmployeeFilter = "";
		this.empDeptFilter = "";
		this.empSort = { key: "overall_score", dir: "desc" };
		this.pendEmployeeFilter = "";
		this.pendDeptFilter = "";
		this.pendSort = { key: "due_date_raw", dir: "asc" };
		this.render_shell();
		// get_departments_for_filter() throws frappe.PermissionError for
		// non-admins -- without this .catch(), load() (which already knows
		// how to show a proper permission message) would never run, leaving
		// those users stuck on the "Loading..." spinner from render_shell()
		// forever.
		this.load_departments().then(() => this.load()).catch(() => this.load());
	}

	render_shell() {
		this.$body.html(`
			<div class="ta-root">
				<style>${this.styles()}</style>
				<div class="ta-filter-bar"></div>
				<div class="ta-content">
					<div class="ta-loading">${__("Loading training analytics...")}</div>
				</div>
			</div>
		`);
		this.$root = this.$body.find(".ta-root");
		this.$filterBar = this.$root.find(".ta-filter-bar");
		this.$content = this.$root.find(".ta-content");
	}

	load_departments() {
		return frappe.call({ method: "quality_dms.dms.api.get_departments_for_filter" }).then((r) => {
			this.departments = r.message || [];
			this.render_filter_bar();
		});
	}

	render_filter_bar() {
		const deptOptions = this.departments
			.map((d) => `<option value="${frappe.utils.escape_html(d)}">${frappe.utils.escape_html(d)}</option>`)
			.join("");
		this.$filterBar.html(`
			<div class="ta-filters">
				<div class="ta-filter-field">
					<label>${__("From")}</label>
					<input type="date" class="form-control ta-from-date" />
				</div>
				<div class="ta-filter-field">
					<label>${__("To")}</label>
					<input type="date" class="form-control ta-to-date" />
				</div>
				<div class="ta-filter-field">
					<label>${__("Department")}</label>
					<select class="form-control ta-department">
						<option value="">${__("All Departments")}</option>
						${deptOptions}
					</select>
				</div>
				<button class="btn btn-sm btn-default ta-clear-filters">${__("Clear")}</button>
			</div>
		`);
		this.$filterBar.find(".ta-from-date").on("change", (e) => {
			this.filters.from_date = e.target.value || null;
			this.load();
		});
		this.$filterBar.find(".ta-to-date").on("change", (e) => {
			this.filters.to_date = e.target.value || null;
			this.load();
		});
		this.$filterBar.find(".ta-department").on("change", (e) => {
			this.filters.department = e.target.value || null;
			this.load();
		});
		this.$filterBar.find(".ta-clear-filters").on("click", () => {
			this.filters = { from_date: null, to_date: null, department: null };
			this.$filterBar.find(".ta-from-date, .ta-to-date").val("");
			this.$filterBar.find(".ta-department").val("");
			this.load();
		});
	}

	load() {
		frappe.call({
			method: "quality_dms.dms.api.get_training_analytics",
			args: this.filters,
			callback: (r) => {
				if (!r.message) return;
				this.render(r.message);
			},
			error: () => {
				this.$content.html(`
					<div class="ta-empty">${__("You do not have permission to view training analytics.")}</div>
				`);
			},
		});
	}

	render(data) {
		const totalCompleted = data.completion_by_department.reduce((s, d) => s + d.completed, 0);
		const totalAssigned = data.completion_by_department.reduce((s, d) => s + d.total, 0);
		const overallCompletionPct = totalAssigned ? Math.round((totalCompleted / totalAssigned) * 1000) / 10 : 0;
		const lastMonth = data.score_trend.length ? data.score_trend[data.score_trend.length - 1] : null;

		const scoreBand = (score) => {
			if (score === null || score === undefined) return "none";
			if (score >= 80) return "good";
			if (score >= 60) return "fair";
			return "poor";
		};
		const completionBand = (pct) => (pct >= 80 ? "good" : pct >= 50 ? "fair" : "poor");

		const icon = (path) => `<svg class="ta-title-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">${path}</svg>`;
		const icons = {
			trend: icon('<path d="M3 17l6-6 4 4 8-8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 7h6v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
			check: icon('<path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
			bars: icon('<path d="M5 21V10M12 21V3M19 21v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
			dept: icon('<path d="M3 21h18M6 21V7l6-4 6 4v14M9 9h1M9 13h1M9 17h1M14 9h1M14 13h1M14 17h1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
			alert: icon('<path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a1 1 0 00.87 1.5h18.62a1 1 0 00.87-1.5L13.71 3.86a1 1 0 00-1.72 0z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
			list: icon('<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
		};

		const lastPassRate = data.pass_rate_trend.length ? data.pass_rate_trend[data.pass_rate_trend.length - 1] : null;

		this.$content.html(`
			<div class="ta-tiles">
				<div class="ta-tile ta-accent-${scoreBand(lastMonth ? lastMonth.avg_score : null)}">
					<div class="ta-tile-label">${icons.trend}${__("Latest Monthly Avg Score")}</div>
					<div class="ta-tile-value ta-value-${scoreBand(lastMonth ? lastMonth.avg_score : null)}">${lastMonth ? lastMonth.avg_score + "%" : "—"}</div>
				</div>
				<div class="ta-tile ta-accent-${completionBand(overallCompletionPct)}">
					<div class="ta-tile-label">${icons.check}${__("Overall Completion Rate")}</div>
					<div class="ta-tile-value ta-value-${completionBand(overallCompletionPct)}">${overallCompletionPct}%</div>
				</div>
				<div class="ta-tile ta-accent-${completionBand(lastPassRate ? lastPassRate.pass_rate : null)}">
					<div class="ta-tile-label">${icons.check}${__("Latest Monthly Pass Rate")}</div>
					<div class="ta-tile-value ta-value-${completionBand(lastPassRate ? lastPassRate.pass_rate : null)}">${lastPassRate ? lastPassRate.pass_rate + "%" : "—"}</div>
				</div>
			</div>

			<div class="ta-grid">
				<div class="ta-card ta-accent-amber">
					<div class="ta-card-title">${icons.bars}${__("Score Distribution")}</div>
					${this.distribution_chart(data.distribution)}
				</div>

				<div class="ta-card ta-accent-poor">
					<div class="ta-card-title">${icons.alert}${__("Overdue Trainings by Due Month")}</div>
					${this.overdue_chart(data.overdue_trend)}
				</div>

				<div class="ta-card ta-dept-card ta-accent-violet">
					<div class="ta-card-title">${icons.dept}${__("Completion Rate by Department")}</div>
					${this.department_table(data.completion_by_department)}
				</div>

				<div class="ta-card ta-dept-card ta-accent-blue">
					<div class="ta-card-title-row">
						<div class="ta-card-title">${icons.trend}${__("Employee Scores")} <span class="ta-count" id="ta-emp-count"></span></div>
						<div class="ta-table-tools">
							<input type="text" class="form-control input-sm ta-filter-typeahead" id="ta-emp-employee-filter" list="ta-emp-employee-list" placeholder="${__("Type employee name...")}" autocomplete="off" />
							<datalist id="ta-emp-employee-list">
								${this._unique(data.employee_scores, "employee_name").map((v) => `<option value="${frappe.utils.escape_html(v)}">`).join("")}
							</datalist>
							<input type="text" class="form-control input-sm ta-filter-typeahead" id="ta-emp-dept-filter" list="ta-emp-dept-list" placeholder="${__("Type department...")}" autocomplete="off" />
							<datalist id="ta-emp-dept-list">
								${this._unique(data.employee_scores, "department").map((v) => `<option value="${frappe.utils.escape_html(v)}">`).join("")}
							</datalist>
							<button class="btn btn-xs btn-default ta-download" data-table="employee_scores">${__("Download CSV")}</button>
						</div>
					</div>
					<div id="ta-emp-table-body"></div>
				</div>

				<div class="ta-card ta-dept-card ta-accent-amber">
					<div class="ta-card-title-row">
						<div class="ta-card-title">${icons.list}${__("Pending Trainings — All Employees")} <span class="ta-count" id="ta-pend-count"></span></div>
						<div class="ta-table-tools">
							<input type="text" class="form-control input-sm ta-filter-typeahead" id="ta-pend-employee-filter" list="ta-pend-employee-list" placeholder="${__("Type employee name...")}" autocomplete="off" />
							<datalist id="ta-pend-employee-list">
								${this._unique(data.pending_trainings, "employee_name").map((v) => `<option value="${frappe.utils.escape_html(v)}">`).join("")}
							</datalist>
							<input type="text" class="form-control input-sm ta-filter-typeahead" id="ta-pend-dept-filter" list="ta-pend-dept-list" placeholder="${__("Type department...")}" autocomplete="off" />
							<datalist id="ta-pend-dept-list">
								${this._unique(data.pending_trainings, "department").map((v) => `<option value="${frappe.utils.escape_html(v)}">`).join("")}
							</datalist>
							<button class="btn btn-xs btn-default ta-download" data-table="pending_trainings">${__("Download CSV")}</button>
						</div>
					</div>
					<div id="ta-pend-table-body"></div>
				</div>
			</div>
		`);

		this._lastData = data;
		this.render_employee_table();
		this.render_pending_table();

		this.$content.find(".ta-download").on("click", (e) => {
			const table = $(e.currentTarget).data("table");
			this.download_csv(table);
		});
		this.$content.find("#ta-emp-employee-filter").on("input", (e) => {
			this.empEmployeeFilter = e.target.value.toLowerCase();
			this.render_employee_table();
		});
		this.$content.find("#ta-emp-dept-filter").on("input", (e) => {
			this.empDeptFilter = e.target.value.toLowerCase();
			this.render_employee_table();
		});
		this.$content.find("#ta-pend-employee-filter").on("input", (e) => {
			this.pendEmployeeFilter = e.target.value.toLowerCase();
			this.render_pending_table();
		});
		this.$content.find("#ta-pend-dept-filter").on("input", (e) => {
			this.pendDeptFilter = e.target.value.toLowerCase();
			this.render_pending_table();
		});
	}

	_unique(rows, key) {
		return [...new Set(rows.map((r) => r[key]).filter(Boolean))].sort();
	}

	render_employee_table() {
		let rows = this._lastData.employee_scores.slice();
		if (this.empEmployeeFilter) {
			rows = rows.filter((r) => (r.employee_name || "").toLowerCase().includes(this.empEmployeeFilter));
		}
		if (this.empDeptFilter) {
			rows = rows.filter((r) => (r.department || "").toLowerCase().includes(this.empDeptFilter));
		}
		const { key, dir } = this.empSort;
		rows.sort((a, b) => {
			let av = a[key], bv = b[key];
			if (av === null || av === undefined) av = dir === "asc" ? Infinity : -Infinity;
			if (bv === null || bv === undefined) bv = dir === "asc" ? Infinity : -Infinity;
			if (typeof av === "string") return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
			return dir === "asc" ? av - bv : bv - av;
		});
		this.$content.find("#ta-emp-count").text(`(${rows.length}${rows.length !== this._lastData.employee_scores.length ? ` / ${this._lastData.employee_scores.length}` : ""})`);
		this.$content.find("#ta-emp-table-body").html(this.employee_scores_table(rows));
		this.$content.find("#ta-emp-table-body [data-sort]").on("click", (e) => {
			const sortKey = $(e.currentTarget).data("sort");
			this.empSort = { key: sortKey, dir: this.empSort.key === sortKey && this.empSort.dir === "desc" ? "asc" : "desc" };
			this.render_employee_table();
		});
		this.$content.find("#ta-emp-table-body .ta-emp-link").on("click", (e) => {
			e.preventDefault();
			const $el = $(e.currentTarget);
			this.show_employee_trainings($el.data("employee"), $el.data("employee-name"));
		});
	}

	show_employee_trainings(employee, employee_name) {
		const dialog = new frappe.ui.Dialog({
			title: __("Trainings — {0}", [employee_name]),
			size: "large",
			fields: [{ fieldname: "body", fieldtype: "HTML" }],
		});
		dialog.fields_dict.body.$wrapper.html(`<div class="ta-emp-dialog-loading">${__("Loading...")}</div>`);
		dialog.show();

		frappe.call({
			method: "quality_dms.dms.api.get_my_training_dashboard",
			args: { employee },
			callback: (r) => {
				const all = (r.message && r.message.all_trainings) || [];
				const completed = all.filter((t) => t.status === "Completed");
				const incomplete = all.filter((t) => t.status !== "Completed");

				const row = (t) => `
					<tr>
						<td>${frappe.utils.escape_html(t.document || "")}</td>
						<td><span class="indicator-pill ${t.status === "Completed" ? "green" : t.status === "Overdue" ? "red" : "orange"}">${frappe.utils.escape_html(t.status || "")}</span></td>
						<td>${t.assessment_score !== null && t.assessment_score !== undefined ? t.assessment_score + "%" : "—"}</td>
						<td>${frappe.utils.escape_html((t.status === "Completed" ? t.completion_date : t.due_date) || "—")}</td>
					</tr>`;

				const section = (title, rows, emptyMsg) => `
					<h6 class="ta-emp-dialog-heading">${title} (${rows.length})</h6>
					${
						rows.length
							? `<table class="table table-bordered ta-emp-dialog-table">
								<thead><tr><th>${__("Document")}</th><th>${__("Status")}</th><th>${__("Score")}</th><th>${__("Date")}</th></tr></thead>
								<tbody>${rows.map(row).join("")}</tbody>
							</table>`
							: `<div class="ta-empty-small">${emptyMsg}</div>`
					}`;

				dialog.fields_dict.body.$wrapper.html(`
					${section(__("Completed"), completed, __("No completed trainings yet."))}
					${section(__("Incomplete"), incomplete, __("Nothing outstanding — all caught up."))}
				`);
			},
			error: () => {
				dialog.fields_dict.body.$wrapper.html(
					`<div class="ta-empty-small">${__("You do not have permission to view this employee's trainings.")}</div>`
				);
			},
		});
	}

	render_pending_table() {
		let rows = this._lastData.pending_trainings.slice();
		if (this.pendEmployeeFilter) {
			rows = rows.filter((r) => (r.employee_name || "").toLowerCase().includes(this.pendEmployeeFilter));
		}
		if (this.pendDeptFilter) {
			rows = rows.filter((r) => (r.department || "").toLowerCase().includes(this.pendDeptFilter));
		}
		const { key, dir } = this.pendSort;
		rows.sort((a, b) => {
			let av = a[key] || "", bv = b[key] || "";
			return dir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
		});
		this.$content.find("#ta-pend-count").text(`(${rows.length}${rows.length !== this._lastData.pending_trainings.length ? ` / ${this._lastData.pending_trainings.length}` : ""})`);
		this.$content.find("#ta-pend-table-body").html(this.pending_trainings_table(rows));
		this.$content.find("#ta-pend-table-body [data-sort]").on("click", (e) => {
			const sortKey = $(e.currentTarget).data("sort");
			this.pendSort = { key: sortKey, dir: this.pendSort.key === sortKey && this.pendSort.dir === "desc" ? "asc" : "desc" };
			this.render_pending_table();
		});
	}

	overdue_chart(overdueTrend) {
		if (!overdueTrend || !overdueTrend.length) {
			return `<div class="ta-empty-small">${__("No overdue trainings on record — nothing to show.")}</div>`;
		}
		const max = Math.max(...overdueTrend.map((d) => d.overdue_count), 1);
		const cols = overdueTrend
			.map(
				(d) => `
				<div class="ta-vdist-col">
					<div class="ta-vdist-count">${d.overdue_count}</div>
					<div class="ta-vdist-track">
						<div class="ta-vdist-fill crit" style="height:${(d.overdue_count / max * 100).toFixed(1)}%"></div>
					</div>
					<div class="ta-vdist-label">${frappe.utils.escape_html(d.month)}</div>
				</div>`
			)
			.join("");
		return `<div class="ta-vdist-chart">${cols}</div>`;
	}

	distribution_chart(distribution) {
		if (!distribution || !distribution.some((d) => d.count > 0)) {
			return `<div class="ta-empty-small">${__("No graded attempts on record yet.")}</div>`;
		}
		const max = Math.max(...distribution.map((d) => d.count), 1);
		const cols = distribution
			.map((d) => {
				const cls = d.label === "0-59" ? "crit" : d.label === "60-69" || d.label === "70-79" ? "warn" : "good";
				return `
				<div class="ta-vdist-col">
					<div class="ta-vdist-count">${d.count}</div>
					<div class="ta-vdist-track">
						<div class="ta-vdist-fill ${cls}" style="height:${(d.count / max * 100).toFixed(1)}%"></div>
					</div>
					<div class="ta-vdist-label">${d.label}</div>
				</div>`;
			})
			.join("");
		return `<div class="ta-vdist-chart">${cols}</div>`;
	}

	department_table(rows) {
		if (!rows || !rows.length) {
			return `<div class="ta-empty-small">${__("No assigned trainings on record yet.")}</div>`;
		}
		const band = (pct) => (pct >= 80 ? "good" : pct >= 50 ? "fair" : "poor");
		const body = rows
			.map(
				(r) => `
				<tr>
					<td>${frappe.utils.escape_html(r.department)}</td>
					<td>${r.completed}/${r.total}</td>
					<td>
						<div class="ta-dept-bar-track">
							<div class="ta-dept-bar-fill ${band(r.completion_pct)}" style="width:${r.completion_pct}%"></div>
						</div>
					</td>
					<td><span class="ta-rate-badge ${band(r.completion_pct)}">${r.completion_pct}%</span></td>
				</tr>`
			)
			.join("");
		return `
			<table class="table ta-table">
				<thead>
					<tr>
						<th>${__("Department")}</th>
						<th>${__("Completed")}</th>
						<th>${__("Progress")}</th>
						<th>${__("Rate")}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		`;
	}

	sort_arrow(currentSort, key) {
		if (currentSort.key !== key) return "";
		return currentSort.dir === "asc" ? " ▲" : " ▼";
	}

	employee_scores_table(rows) {
		if (!rows || !rows.length) {
			return `<div class="ta-empty-small">${__("No employees match your search.")}</div>`;
		}
		const band = (score) => (score === null ? "none" : score >= 80 ? "good" : score >= 60 ? "fair" : "poor");
		const body = rows
			.map(
				(r, i) => `
				<tr class="ta-row-accent-${band(r.overall_score)}">
					<td>${i + 1}</td>
					<td><a href="#" class="ta-emp-link" data-employee="${frappe.utils.escape_html(r.employee)}" data-employee-name="${frappe.utils.escape_html(r.employee_name || r.employee)}">${frappe.utils.escape_html(r.employee_name || r.employee)}</a></td>
					<td>${frappe.utils.escape_html(r.department)}</td>
					<td>${r.completed}/${r.total}</td>
					<td>${r.completion_pct}%</td>
					<td>${r.overall_score !== null ? `<span class="ta-rate-badge ${band(r.overall_score)}">${r.overall_score}%</span>` : "—"}</td>
				</tr>`
			)
			.join("");
		const sortTh = (label, key) =>
			`<th class="ta-sortable${this.empSort.key === key ? " ta-sort-active" : ""}" data-sort="${key}">${label}${this.sort_arrow(this.empSort, key)}</th>`;
		return `
			<div class="ta-scroll-table">
				<table class="table ta-table">
					<thead>
						<tr>
							<th>#</th>
							${sortTh(__("Employee"), "employee_name")}
							${sortTh(__("Department"), "department")}
							${sortTh(__("Completed"), "completed")}
							${sortTh(__("Completion %"), "completion_pct")}
							${sortTh(__("Overall Score"), "overall_score")}
						</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`;
	}

	pending_trainings_table(rows) {
		if (!rows || !rows.length) {
			return `<div class="ta-empty-small">${__("No pending trainings match your search.")}</div>`;
		}
		const statusClass = (status) => {
			const s = (status || "").toLowerCase();
			if (s === "overdue" || s === "failed") return "crit";
			if (s === "pending" || s === "in progress") return "warn";
			return "neutral";
		};
		const today = frappe.datetime.get_today();
		const daysOverdue = (r) => {
			if ((r.status || "").toLowerCase() !== "overdue" || !r.due_date_raw) return null;
			return frappe.datetime.get_day_diff(today, r.due_date_raw);
		};
		const body = rows
			.map((r) => {
				const overdueDays = daysOverdue(r);
				return `
				<tr class="ta-row-accent-${statusClass(r.status)}">
					<td>${frappe.utils.escape_html(r.employee_name || "")}</td>
					<td>${frappe.utils.escape_html(r.department)}</td>
					<td>${frappe.utils.escape_html(r.document || "")}</td>
					<td><span class="ta-rate-badge ${statusClass(r.status)}">${frappe.utils.escape_html(r.status || "")}</span></td>
					<td>${r.due_date || "—"}</td>
					<td>${overdueDays !== null ? `<span class="ta-rate-badge crit">${overdueDays}d</span>` : "—"}</td>
					<td><a href="/app/dms-training-record/${encodeURIComponent(r.training_record || "")}">${__("Open")}</a></td>
				</tr>`;
			})
			.join("");
		const sortTh = (label, key) =>
			`<th class="ta-sortable${this.pendSort.key === key ? " ta-sort-active" : ""}" data-sort="${key}">${label}${this.sort_arrow(this.pendSort, key)}</th>`;
		return `
			<div class="ta-scroll-table">
				<table class="table ta-table">
					<thead>
						<tr>
							${sortTh(__("Employee"), "employee_name")}
							${sortTh(__("Department"), "department")}
							${sortTh(__("Document"), "document")}
							${sortTh(__("Status"), "status")}
							${sortTh(__("Due Date"), "due_date_raw")}
							<th>${__("Overdue By")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`;
	}

	download_csv(table) {
		if (!this._lastData) return;
		let rows = [];
		let filename = "";
		if (table === "employee_scores") {
			rows = [["Employee", "Department", "Completed", "Total", "Completion %", "Overall Score"]];
			this._lastData.employee_scores.forEach((r) => {
				rows.push([r.employee_name || r.employee, r.department, r.completed, r.total, r.completion_pct, r.overall_score ?? ""]);
			});
			filename = "employee_scores.csv";
		} else if (table === "pending_trainings") {
			rows = [["Employee", "Department", "Document", "Status", "Due Date"]];
			this._lastData.pending_trainings.forEach((r) => {
				rows.push([r.employee_name, r.department, r.document, r.status, r.due_date || ""]);
			});
			filename = "pending_trainings.csv";
		} else {
			return;
		}
		const csv = rows
			.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
			.join("\n");
		const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = filename;
		a.click();
		URL.revokeObjectURL(url);
	}

	styles() {
		return `
			.ta-root { padding: 4px 2px 24px; }
			.ta-loading, .ta-empty { padding: 40px; text-align: center; color: var(--text-muted); }
			.ta-filters {
				display: flex;
				align-items: flex-end;
				gap: 14px;
				margin-bottom: 18px;
				flex-wrap: wrap;
			}
			.ta-filter-field { display: flex; flex-direction: column; gap: 4px; }
			.ta-filter-field label { font-size: 11.5px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; }
			.ta-filter-field .form-control { width: 170px; }
			.ta-clear-filters { margin-bottom: 1px; }
			.ta-tiles {
				display: grid;
				grid-template-columns: repeat(3, 1fr);
				gap: 14px;
				margin-bottom: 16px;
			}
			.ta-tile {
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #e1e1e1);
				border-top: 3px solid transparent;
				border-radius: 10px;
				padding: 16px 18px;
				box-shadow: 0 1px 3px rgba(16,24,40,0.04), 0 1px 2px rgba(16,24,40,0.03);
				transition: box-shadow .15s ease;
			}
			.ta-tile:hover { box-shadow: 0 4px 14px rgba(16,24,40,0.08), 0 1px 3px rgba(16,24,40,0.05); }
			.ta-tile-label {
				font-size: 12px;
				color: var(--text-muted);
				margin-bottom: 6px;
				display: flex;
				align-items: center;
				gap: 6px;
			}
			.ta-tile-value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
			.ta-value-good { color: #0ca30c; }
			.ta-value-fair { color: #b8860b; }
			.ta-value-poor { color: #d03b3b; }
			.ta-accent-blue { border-top-color: #1f4e79; }
			.ta-accent-amber { border-top-color: #fab219; }
			.ta-accent-violet { border-top-color: #7c5cbf; }
			.ta-accent-good { border-top-color: #0ca30c; }
			.ta-accent-fair { border-top-color: #fab219; }
			.ta-accent-poor { border-top-color: #d03b3b; }
			.ta-accent-none { border-top-color: var(--border-color, #e1e1e1); }
			.ta-title-icon { width: 14px; height: 14px; color: var(--text-muted); flex: 0 0 auto; }
			.ta-grid {
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 16px;
			}
			@media (max-width: 900px) { .ta-grid, .ta-tiles { grid-template-columns: 1fr; } }
			.ta-card {
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #e1e1e1);
				border-top: 3px solid transparent;
				border-radius: 10px;
				padding: 18px 20px;
				box-shadow: 0 1px 3px rgba(16,24,40,0.04), 0 1px 2px rgba(16,24,40,0.03);
				transition: box-shadow .15s ease;
			}
			.ta-card:hover { box-shadow: 0 4px 14px rgba(16,24,40,0.08), 0 1px 3px rgba(16,24,40,0.05); }
			.ta-card-title {
				font-size: 13px;
				font-weight: 600;
				text-transform: uppercase;
				letter-spacing: 0.02em;
				color: var(--text-muted);
				margin-bottom: 14px;
				display: flex;
				align-items: center;
				gap: 8px;
			}
			.ta-card-title-row {
				display: flex;
				align-items: center;
				justify-content: space-between;
				margin-bottom: 14px;
			}
			.ta-card-title-row .ta-card-title { margin-bottom: 0; }
			.ta-count { font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--text-muted); }
			.ta-table-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
			.ta-scroll-table { max-height: 360px; overflow-y: auto; }
			.ta-scroll-table::-webkit-scrollbar { width: 8px; }
			.ta-scroll-table::-webkit-scrollbar-track { background: var(--border-color, #e1e1e1); border-radius: 4px; }
			.ta-scroll-table::-webkit-scrollbar-thumb { background: #1f4e79; border-radius: 4px; }
			.ta-scroll-table::-webkit-scrollbar-thumb:hover { background: #163d5e; }
			.ta-sortable { cursor: pointer; user-select: none; }
			.ta-sortable:hover { color: var(--text-color, #17212b); }
			.ta-sort-active { background: rgba(31,78,121,0.08); color: #1f4e79 !important; font-weight: 700; }
			.ta-filter-typeahead { width: 170px; height: 26px; font-size: 12.5px; }
			.ta-row-accent-good { box-shadow: inset 3px 0 0 #0ca30c; }
			.ta-row-accent-fair, .ta-row-accent-warn { box-shadow: inset 3px 0 0 #fab219; }
			.ta-row-accent-poor, .ta-row-accent-crit { box-shadow: inset 3px 0 0 #d03b3b; }
			.ta-row-accent-none, .ta-row-accent-neutral { box-shadow: inset 3px 0 0 transparent; }
			.ta-dept-card { grid-column: span 2; }
			.ta-dist-chart { display: flex; flex-direction: column; gap: 10px; }
			.ta-dist-row { display: grid; grid-template-columns: 60px 1fr 40px; align-items: center; gap: 10px; }
			.ta-dist-label { font-size: 12px; color: var(--text-secondary, #52514e); text-align: right; }
			.ta-dist-track { height: 16px; border-radius: 4px; background: var(--border-color, #e1e1e1); overflow: hidden; }
			.ta-dist-fill { height: 100%; border-radius: 4px; }
			.ta-dist-fill.crit { background: #d03b3b; }
			.ta-dist-fill.warn { background: #fab219; }
			.ta-dist-fill.good { background: #0ca30c; }
			.ta-dist-count { font-size: 12px; font-weight: 600; text-align: right; }
			.ta-vdist-chart {
				display: flex;
				align-items: flex-end;
				justify-content: space-around;
				gap: 14px;
				height: 220px;
				padding-top: 8px;
			}
			.ta-vdist-col {
				display: flex;
				flex-direction: column;
				align-items: center;
				justify-content: flex-end;
				flex: 1 1 0;
				height: 100%;
				min-width: 0;
			}
			.ta-vdist-count { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
			.ta-vdist-track {
				width: 32px;
				flex: 1 1 auto;
				border-radius: 4px;
				background: var(--border-color, #e1e1e1);
				overflow: hidden;
				display: flex;
				align-items: flex-end;
			}
			.ta-vdist-fill { width: 100%; border-radius: 4px 4px 0 0; }
			.ta-vdist-fill.crit { background: #d03b3b; }
			.ta-vdist-fill.warn { background: #fab219; }
			.ta-vdist-fill.good { background: #0ca30c; }
			.ta-vdist-label {
				margin-top: 8px;
				font-size: 12px;
				color: var(--text-secondary, #52514e);
				text-align: center;
				white-space: nowrap;
			}
			.ta-table { font-size: 13px; margin: 0; }
			.ta-table thead th {
				background: linear-gradient(90deg, #1f4e79 0%, #2c6499 100%);
				color: #ffffff;
				font-weight: 600;
				font-size: 11.5px;
				text-transform: uppercase;
				letter-spacing: 0.03em;
				padding-top: 10px;
				padding-bottom: 10px;
				position: sticky;
				top: 0;
				z-index: 1;
			}
			.ta-table thead th.ta-sortable:hover { color: #ffffff; background: linear-gradient(90deg, #163d5e 0%, #24537e 100%); }
			.ta-table thead th.ta-sort-active { background: #16334d; color: #ffffff !important; }
			.ta-table tbody tr:hover { background: rgba(31,78,121,0.03); }
			.ta-dept-bar-track { height: 8px; border-radius: 4px; background: var(--border-color, #e1e1e1); overflow: hidden; width: 120px; }
			.ta-dept-bar-fill { height: 100%; border-radius: 4px; }
			.ta-dept-bar-fill.good { background: linear-gradient(90deg, #0ca30c, #3fbf3f); }
			.ta-dept-bar-fill.fair { background: linear-gradient(90deg, #fab219, #ffc94d); }
			.ta-dept-bar-fill.poor { background: linear-gradient(90deg, #d03b3b, #e56b6b); }
			.ta-rate-badge {
				font-size: 11.5px;
				font-weight: 700;
				padding: 2px 9px;
				border-radius: 20px;
			}
			.ta-rate-badge.good { background: rgba(12,163,12,0.12); color: #0ca30c; }
			.ta-rate-badge.fair { background: rgba(250,178,25,0.18); color: #8a6100; }
			.ta-rate-badge.poor, .ta-rate-badge.crit { background: rgba(208,59,59,0.12); color: #d03b3b; }
			.ta-rate-badge.warn { background: rgba(250,178,25,0.18); color: #8a6100; }
			.ta-rate-badge.neutral, .ta-rate-badge.none { background: rgba(31,78,121,0.1); color: #1f4e79; }
			.ta-empty-small { color: var(--text-muted); font-size: 13px; padding: 8px 0; }
			.ta-emp-link { color: #1f4e79; text-decoration: none; font-weight: 500; }
			.ta-emp-link:hover { text-decoration: underline; }
			.ta-emp-dialog-heading { margin: 16px 0 8px; font-weight: 700; }
			.ta-emp-dialog-heading:first-child { margin-top: 0; }
			.ta-emp-dialog-table { font-size: 13px; margin-bottom: 8px; }
			.ta-emp-dialog-loading { color: var(--text-muted); font-size: 13px; padding: 20px 0; text-align: center; }
		`;
	}
}
