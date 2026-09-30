frappe.pages["my-training-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("My Training Dashboard"),
		single_column: true,
	});

	new MyTrainingDashboard(page);
};

class MyTrainingDashboard {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.trainingStatusFilter = "";
		this.render_shell();
		this.add_transcript_button();
		this.load();
	}

	add_transcript_button() {
		this.page.add_inner_button(__("Download My Training Report"), () => {
			frappe.show_alert({ message: __("Generating your transcript..."), indicator: "blue" });
			frappe.call({
				method: "quality_dms.dms.api.generate_training_transcript",
				callback: (r) => {
					if (!r.message || !r.message.file_url) {
						frappe.msgprint(__("Could not generate a transcript for your account."));
						return;
					}
					window.open(r.message.file_url, "_blank");
				},
			});
		});
	}

	render_shell() {
		this.$body.html(`
			<div class="mtd-root">
				<style>${this.styles()}</style>
				<div class="mtd-loading">${__("Loading your training dashboard...")}</div>
			</div>
		`);
		this.$root = this.$body.find(".mtd-root");
	}

	load() {
		Promise.all([
			frappe.call({ method: "quality_dms.dms.api.get_my_training_dashboard" }),
			frappe.call({ method: "quality_dms.dms.api.get_my_score_trend" }),
		]).then(([dashboardRes, trendRes]) => {
			if (!dashboardRes.message) return;
			this.render(dashboardRes.message, (trendRes.message || {}).trend || []);
		});
	}

	render(data, trend) {
		if (!data.employee) {
			this.$root.html(`
				<style>${this.styles()}</style>
				<div class="mtd-empty">
					${__("No Employee record is linked to your user account, so there is no training data to show.")}
				</div>
			`);
			return;
		}

		const score = data.overall_score;
		const band = data.score_band;
		const bandClass = band ? band.toLowerCase() : "none";
		const gaugePct = score !== null ? Math.min(100, Math.max(0, score)) : 0;
		const gaugeAngle = (gaugePct / 100) * 180;

		const icon = (path) => `<svg class="mtd-title-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">${path}</svg>`;
		const icons = {
			gauge: icon('<path d="M12 3a9 9 0 100 18 9 9 0 000-18z" stroke="currentColor" stroke-width="1.6"/><path d="M12 12l4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'),
			check: icon('<path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
			list: icon('<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
			trophy: icon('<path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 01-10 0V4z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M7 5H4v2a3 3 0 003 3M17 5h3v2a3 3 0 01-3 3" stroke="currentColor" stroke-width="1.6"/>'),
			trend: icon('<path d="M3 17l6-6 4 4 8-8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 7h6v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
		};

		const scores = trend.map((t) => t.score);
		const bestScore = scores.length ? Math.max(...scores) : null;
		const latestScore = scores.length ? scores[scores.length - 1] : null;

		this.$root.html(`
			<style>${this.styles()}</style>
			<div class="mtd-grid">
				<div class="mtd-card mtd-gauge-card mtd-accent-${bandClass}">
					<div class="mtd-card-title">${icons.gauge}${__("My Overall Training Score")}</div>
					${this.gauge_svg(gaugeAngle, score, bandClass)}
					<div class="mtd-band-legend">
						<span class="mtd-band-dot poor"></span>${__("Poor")} (&lt; 60)
						<span class="mtd-band-dot fair"></span>${__("Fair")} (60-79)
						<span class="mtd-band-dot good"></span>${__("Good")} (&ge; 80)
					</div>
				</div>

				<div class="mtd-card mtd-accent-blue">
					<div class="mtd-card-title">${icons.check}${__("Completion")}</div>
					<div class="mtd-stat-row">
						<div class="mtd-stat">
							<div class="mtd-stat-value">${data.total_completed}/${data.total_assigned}</div>
							<div class="mtd-stat-label">${__("Trainings Completed")}</div>
						</div>
						<div class="mtd-stat">
							<div class="mtd-stat-value">${data.completion_pct}%</div>
							<div class="mtd-stat-label">${__("Completion Rate")}</div>
						</div>
					</div>
					<div class="mtd-progress-track">
						<div class="mtd-progress-fill" style="width:${data.completion_pct}%"></div>
					</div>
				</div>

				<div class="mtd-card mtd-todo-card mtd-accent-amber">
					<div class="mtd-card-title-row">
						<div class="mtd-card-title">${icons.list}${__("My Trainings")} <span class="mtd-count" id="mtd-trainings-count"></span></div>
						<select class="form-control input-sm mtd-status-filter" id="mtd-status-filter">
							<option value="">${__("All Statuses")}</option>
							<option value="Completed">${__("Completed")}</option>
							<option value="Pending">${__("Pending")}</option>
							<option value="Overdue">${__("Overdue")}</option>
							<option value="In Progress">${__("In Progress")}</option>
							<option value="Failed">${__("Failed")}</option>
						</select>
					</div>
					<div id="mtd-trainings-body"></div>
				</div>

				<div class="mtd-card mtd-leaderboard-card mtd-accent-violet">
					<div class="mtd-card-title">${icons.trophy}${__("Leaderboard")}</div>
					${this.leaderboard_table(data.leaderboard, data.employee)}
				</div>

				<div class="mtd-card mtd-trend-card mtd-accent-blue">
					<div class="mtd-card-title">${icons.trend}${__("Score Trend")}</div>
					<div class="mtd-trend-layout">
						<div class="mtd-trend-chart-col">${this.trend_chart(trend)}</div>
						<div class="mtd-trend-stats-col">
							<div class="mtd-trend-stat">
								<div class="mtd-trend-stat-value">${bestScore !== null ? bestScore + "%" : "—"}</div>
								<div class="mtd-trend-stat-label">${__("Best Score")}</div>
							</div>
							<div class="mtd-trend-stat">
								<div class="mtd-trend-stat-value">${latestScore !== null ? latestScore + "%" : "—"}</div>
								<div class="mtd-trend-stat-label">${__("Latest Score")}</div>
							</div>
							<div class="mtd-trend-stat">
								<div class="mtd-trend-stat-value">${trend.length}</div>
								<div class="mtd-trend-stat-label">${__("Graded Attempts")}</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`);

		this._lastData = data;
		this.render_trainings_table();
		this.$root.find("#mtd-status-filter").on("change", (e) => {
			this.trainingStatusFilter = e.target.value;
			this.render_trainings_table();
		});
	}

	render_trainings_table() {
		let rows = this._lastData.all_trainings.slice();
		if (this.trainingStatusFilter) {
			rows = rows.filter((r) => r.status === this.trainingStatusFilter);
		}
		this.$root.find("#mtd-trainings-count").text(`(${rows.length}${rows.length !== this._lastData.all_trainings.length ? ` / ${this._lastData.all_trainings.length}` : ""})`);
		this.$root.find("#mtd-trainings-body").html(this.my_trainings_table(rows));
	}

	trend_chart(trend) {
		if (!trend || trend.length < 2) {
			return `<div class="mtd-empty-small">${__("Not enough graded attempts yet to show a trend (need at least 2).")}</div>`;
		}

		const width = 680;
		const height = 220;
		const padLeft = 38;
		const padRight = 16;
		const padTop = 28;
		const padBottom = 30;
		const plotW = width - padLeft - padRight;
		const plotH = height - padTop - padBottom;
		const n = trend.length;
		const xStep = n > 1 ? plotW / (n - 1) : 0;
		const xFor = (i) => padLeft + i * xStep;
		const yFor = (score) => padTop + plotH - (Math.min(100, Math.max(0, score)) / 100) * plotH;

		// Recessive y-axis gridlines + labels at fixed 0/25/50/75/100 -- a
		// percentage scale, so the axis reads consistently regardless of
		// this employee's actual score range.
		const GRID_VALUES = [0, 25, 50, 75, 100];
		const gridlines = GRID_VALUES.map(
			(v) => `
			<line x1="${padLeft}" y1="${yFor(v)}" x2="${width - padRight}" y2="${yFor(v)}" class="mtd-trend-grid" />
			<text x="${padLeft - 8}" y="${yFor(v) + 4}" class="mtd-trend-axis-label" text-anchor="end">${v}</text>`
		).join("");

		const points = trend.map((t, i) => ({ x: xFor(i), y: yFor(t.score), ...t }));
		const linePoints = points.map((p) => `${p.x},${p.y}`).join(" ");
		const dots = points
			.map((p, i) => {
				// Edge points anchor their value label away from the y-axis
				// (start) / plot edge (end) instead of centering, so they never
				// collide with the axis labels or get clipped off the side.
				const anchor = i === 0 ? "start" : i === points.length - 1 ? "end" : "middle";
				const labelX = anchor === "start" ? p.x + 6 : anchor === "end" ? p.x - 6 : p.x;
				return `
				<circle cx="${p.x}" cy="${p.y}" r="4.5" class="mtd-trend-dot ${p.passed ? "good" : "crit"}">
					<title>${frappe.utils.escape_html(p.date)}: ${p.score}%</title>
				</circle>
				<text x="${labelX}" y="${p.y - 12}" class="mtd-trend-value-label" text-anchor="${anchor}">${p.score}%</text>
				<text x="${p.x}" y="${height - padBottom + 18}" class="mtd-trend-axis-label" text-anchor="middle">${frappe.utils.escape_html(p.date)}</text>`;
			})
			.join("");

		return `
			<svg viewBox="0 0 ${width} ${height}" class="mtd-trend-svg" preserveAspectRatio="xMidYMid meet">
				${gridlines}
				<line x1="${padLeft}" y1="${yFor(70)}" x2="${width - padRight}" y2="${yFor(70)}" class="mtd-trend-threshold" />
				<text x="${width - padRight}" y="${yFor(70) - 5}" class="mtd-trend-threshold-label" text-anchor="end">${__("Target")} 70%</text>
				<polyline points="${linePoints}" class="mtd-trend-line" />
				${dots}
			</svg>
		`;
	}

	gauge_svg(angleDeg, score, bandClass) {
		const r = 80;
		const cx = 100;
		const cy = 100;
		const startAngle = 180;
		const endAngle = 180 - angleDeg;
		const toRad = (deg) => (deg * Math.PI) / 180;
		const x1 = cx + r * Math.cos(toRad(startAngle));
		const y1 = cy - r * Math.sin(toRad(startAngle));
		const x2 = cx + r * Math.cos(toRad(endAngle));
		const y2 = cy - r * Math.sin(toRad(endAngle));
		const largeArc = angleDeg > 180 ? 1 : 0;

		return `
			<div class="mtd-gauge-wrap">
				<svg viewBox="0 0 200 110" class="mtd-gauge">
					<path d="M 20 100 A 80 80 0 0 1 180 100" class="mtd-gauge-track" />
					${
						score !== null
							? `<path d="M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}" class="mtd-gauge-fill ${bandClass}" />`
							: ""
					}
				</svg>
				<div class="mtd-gauge-value">
					${score !== null ? `<span class="mtd-gauge-number ${bandClass}">${score}</span><span class="mtd-gauge-suffix">%</span>` : `<span class="mtd-gauge-none">${__("No score yet")}</span>`}
				</div>
			</div>
		`;
	}

	my_trainings_table(rows) {
		if (!rows || !rows.length) {
			return `<div class="mtd-empty-small">${__("No trainings match this filter.")}</div>`;
		}
		const statusClass = (status) => {
			const s = (status || "").toLowerCase();
			if (s === "overdue" || s === "failed") return "crit";
			if (s === "pending" || s === "in progress") return "warn";
			if (s === "completed") return "good";
			return "neutral";
		};
		const body = rows
			.map((t) => {
				const isCompleted = (t.status || "").toLowerCase() === "completed";
				return `
				<tr>
					<td>${frappe.utils.escape_html(t.document || "")}</td>
					<td><span class="mtd-status-badge ${statusClass(t.status)}">${frappe.utils.escape_html(t.status || "")}</span></td>
					<td>${t.assessment_score !== null && t.assessment_score !== undefined ? t.assessment_score + "%" : "—"}</td>
					<td>${isCompleted ? (t.completion_date || "—") : (t.due_date || "—")}</td>
					<td><a class="btn btn-xs btn-primary" href="/app/dms-training-record/${encodeURIComponent(t.training_record || "")}" title="${__("Open the training record")}">${__("Go")}</a></td>
				</tr>`;
			})
			.join("");
		return `
			<div class="mtd-scroll-table">
				<table class="table mtd-table">
					<thead>
						<tr>
							<th>${__("Document")}</th>
							<th>${__("Status")}</th>
							<th>${__("Score")}</th>
							<th>${__("Date")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`;
	}

	leaderboard_table(leaderboard, currentEmployee) {
		if (!leaderboard || !leaderboard.length) {
			return `<div class="mtd-empty-small">${__("No completed, scored trainings yet.")}</div>`;
		}
		const medal = (rank) => {
			if (rank === 1) return `<span class="mtd-medal gold">1</span>`;
			if (rank === 2) return `<span class="mtd-medal silver">2</span>`;
			if (rank === 3) return `<span class="mtd-medal bronze">3</span>`;
			return `<span class="mtd-medal-rank">${rank}</span>`;
		};
		const rows = leaderboard
			.map(
				(row) => `
				<tr class="${row.employee === currentEmployee ? "mtd-me-row" : ""}">
					<td>${medal(row.rank)}</td>
					<td>${frappe.utils.escape_html(row.employee_name || row.employee)}${row.employee === currentEmployee ? ` <span class="mtd-me-tag">${__("You")}</span>` : ""}</td>
					<td>${row.score}%</td>
				</tr>`
			)
			.join("");
		return `
			<table class="table mtd-table">
				<thead>
					<tr>
						<th>${__("Rank")}</th>
						<th>${__("Employee")}</th>
						<th>${__("Score")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`;
	}

	styles() {
		return `
			.mtd-root { padding: 4px 2px 24px; }
			.mtd-loading, .mtd-empty { padding: 40px; text-align: center; color: var(--text-muted); }
			.mtd-grid {
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 16px;
			}
			@media (max-width: 900px) { .mtd-grid { grid-template-columns: 1fr; } }
			.mtd-card {
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #e1e1e1);
				border-top: 3px solid transparent;
				border-radius: 10px;
				padding: 18px 20px;
				box-shadow: 0 1px 3px rgba(16,24,40,0.04), 0 1px 2px rgba(16,24,40,0.03);
				transition: box-shadow .15s ease, transform .15s ease;
			}
			.mtd-card:hover {
				box-shadow: 0 4px 14px rgba(16,24,40,0.08), 0 1px 3px rgba(16,24,40,0.05);
			}
			.mtd-accent-good, .mtd-accent-blue { border-top-color: #1f4e79; }
			.mtd-accent-fair { border-top-color: #fab219; }
			.mtd-accent-poor { border-top-color: #d03b3b; }
			.mtd-accent-none { border-top-color: var(--border-color, #e1e1e1); }
			.mtd-accent-amber { border-top-color: #fab219; }
			.mtd-accent-violet { border-top-color: #7c5cbf; }
			.mtd-card-title {
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
			.mtd-title-icon { width: 15px; height: 15px; color: var(--text-muted); flex: 0 0 auto; }
			.mtd-card-title-row {
				display: flex;
				align-items: center;
				justify-content: space-between;
				margin-bottom: 14px;
				flex-wrap: wrap;
				gap: 8px;
			}
			.mtd-card-title-row .mtd-card-title { margin-bottom: 0; }
			.mtd-count { font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--text-muted); }
			.mtd-status-filter { width: 150px; height: 26px; font-size: 12.5px; }
			.mtd-scroll-table { max-height: 300px; overflow-y: auto; }
			.mtd-scroll-table::-webkit-scrollbar { width: 8px; }
			.mtd-scroll-table::-webkit-scrollbar-track { background: var(--border-color, #e1e1e1); border-radius: 4px; }
			.mtd-scroll-table::-webkit-scrollbar-thumb { background: #1f4e79; border-radius: 4px; }
			.mtd-gauge-card { display: flex; flex-direction: column; align-items: center; }
			.mtd-gauge-wrap { position: relative; width: 220px; }
			.mtd-gauge { width: 100%; }
			.mtd-gauge-track { fill: none; stroke: var(--border-color, #e1e1e1); stroke-width: 14; stroke-linecap: round; }
			.mtd-gauge-fill { fill: none; stroke-width: 14; stroke-linecap: round; }
			.mtd-gauge-fill.good { stroke: #0ca30c; }
			.mtd-gauge-fill.fair { stroke: #fab219; }
			.mtd-gauge-fill.poor { stroke: #d03b3b; }
			.mtd-gauge-value {
				position: absolute;
				bottom: 8px;
				left: 0; right: 0;
				text-align: center;
			}
			.mtd-gauge-number { font-size: 34px; font-weight: 700; }
			.mtd-gauge-number.good { color: #0ca30c; }
			.mtd-gauge-number.fair { color: #b8860b; }
			.mtd-gauge-number.poor { color: #d03b3b; }
			.mtd-gauge-suffix { font-size: 16px; color: var(--text-muted); margin-left: 2px; }
			.mtd-gauge-none { font-size: 14px; color: var(--text-muted); }
			.mtd-band-legend {
				margin-top: 8px;
				font-size: 11.5px;
				color: var(--text-muted);
				display: flex;
				gap: 12px;
				flex-wrap: wrap;
				justify-content: center;
			}
			.mtd-band-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
			.mtd-band-dot.poor { background: #d03b3b; }
			.mtd-band-dot.fair { background: #fab219; }
			.mtd-band-dot.good { background: #0ca30c; }
			.mtd-stat-row { display: flex; gap: 24px; margin-bottom: 14px; }
			.mtd-stat-value { font-size: 26px; font-weight: 700; }
			.mtd-stat-label { font-size: 12px; color: var(--text-muted); }
			.mtd-progress-track { height: 8px; border-radius: 4px; background: var(--border-color, #e1e1e1); overflow: hidden; }
			.mtd-progress-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #1f4e79 0%, #4a86b8 100%); }
			.mtd-table { font-size: 13px; margin: 0; }
			.mtd-table th { color: var(--text-muted); font-weight: 600; font-size: 11.5px; text-transform: uppercase; }
			.mtd-table tbody tr:hover { background: rgba(31,78,121,0.03); }
			.mtd-status-badge {
				font-size: 11px;
				font-weight: 600;
				padding: 2px 9px;
				border-radius: 20px;
				background: rgba(31,78,121,0.1);
				color: #1f4e79;
			}
			.mtd-status-badge.crit { background: rgba(208,59,59,0.12); color: #d03b3b; }
			.mtd-status-badge.warn { background: rgba(250,178,25,0.18); color: #8a6100; }
			.mtd-status-badge.good { background: rgba(12,163,12,0.12); color: #0ca30c; }
			.mtd-status-badge.neutral { background: rgba(31,78,121,0.1); color: #1f4e79; }
			.mtd-medal {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 22px;
				height: 22px;
				border-radius: 50%;
				font-size: 11px;
				font-weight: 700;
				color: #fff;
			}
			.mtd-medal.gold { background: linear-gradient(135deg, #f2c94c, #e0a800); }
			.mtd-medal.silver { background: linear-gradient(135deg, #cfd6dd, #9aa5b1); }
			.mtd-medal.bronze { background: linear-gradient(135deg, #d38b5d, #a8622f); }
			.mtd-medal-rank {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 22px;
				height: 22px;
				border-radius: 50%;
				font-size: 11px;
				font-weight: 600;
				color: var(--text-muted);
				background: var(--border-color, #e1e1e1);
			}
			.mtd-me-row { background: rgba(31,78,121,0.06); }
			.mtd-me-tag {
				font-size: 10.5px;
				font-weight: 600;
				color: #1f4e79;
				background: rgba(31,78,121,0.12);
				padding: 1px 6px;
				border-radius: 20px;
			}
			.mtd-empty-small { color: var(--text-muted); font-size: 13px; padding: 8px 0; }
			.mtd-todo-card, .mtd-leaderboard-card { grid-column: span 1; }
			.mtd-trend-card { grid-column: span 2; }
			.mtd-trend-layout { display: flex; gap: 24px; align-items: stretch; }
			.mtd-trend-chart-col { flex: 1 1 auto; min-width: 0; }
			.mtd-trend-stats-col {
				flex: 0 0 160px;
				display: flex;
				flex-direction: column;
				justify-content: center;
				gap: 16px;
				border-left: 1px solid var(--border-color, #e1e1e1);
				padding-left: 20px;
			}
			.mtd-trend-stat-value { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; color: #1f4e79; }
			.mtd-trend-stat-label { font-size: 11.5px; color: var(--text-muted); margin-top: 2px; }
			.mtd-trend-svg { width: 100%; height: 220px; }
			.mtd-trend-line { fill: none; stroke: #1f4e79; stroke-width: 2; }
			.mtd-trend-grid { stroke: var(--border-color, #e1e1e1); stroke-width: 1; opacity: 0.6; }
			.mtd-trend-threshold { stroke: #d03b3b; stroke-width: 1.2; stroke-dasharray: 4 3; opacity: 0.7; }
			.mtd-trend-threshold-label { font-size: 10px; fill: #d03b3b; opacity: 0.85; }
			.mtd-trend-dot { stroke: #fff; stroke-width: 1.5; }
			.mtd-trend-dot.good { fill: #0ca30c; }
			.mtd-trend-dot.crit { fill: #d03b3b; }
			.mtd-trend-value-label { font-size: 11px; font-weight: 700; fill: var(--text-color, #17212b); }
			.mtd-trend-axis-label { font-size: 10.5px; fill: var(--text-muted); }
		`;
	}
}
