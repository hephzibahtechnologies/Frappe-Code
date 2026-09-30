// Quality DMS theme scoping — adds .dms-theme to <body> on every DMS page
// (DMS workspace + all its child workspaces, all quality_dms doctypes in any
// view, and the DMS reports), so the blue theme in quality_dms.css never
// touches other apps' pages. UI-only: no workflow or data logic here.
(function () {
	// ── Auto-clear stale client-side cache on a new deploy ──────────────────
	// Recurring pain point: Frappe caches full page snapshots and boot/desktop
	// -icon state in localStorage (see frappe/public/js/frappe/views/pageview.js
	// and the "desktop_icons"/"bootinfo" cache keys), and a normal hard refresh
	// (Ctrl+Shift+R) does NOT clear localStorage -- only DevTools' "Clear site
	// data" does. That gap caused several "changes not reflecting" reports.
	// This compares the running quality_dms.js's own ?v= (already bumped on
	// every asset change, see hooks.py) against what the browser last saw; on
	// a mismatch it wipes just the known-stale keys and does one hard reload,
	// so users never have to do that manual DevTools step themselves again.
	// Does not affect the 10 vendor-SVG icon files without a query-string
	// version (assets/<app>/icons/desktop_icons/...) -- those are outside any
	// URL this app constructs, so no client-side cache key can target them;
	// their staleness window is bounded by the server's own Cache-Control
	// (12h) rather than by anything fixable here.
	try {
		const script = document.currentScript;
		const src = (script && script.src) || "";
		const match = src.match(/[?&]v=([\w.]+)/);
		const current_version = match ? match[1] : null;
		const STORAGE_KEY = "dms_app_version";

		if (current_version) {
			const last_version = window.localStorage.getItem(STORAGE_KEY);
			if (last_version && last_version !== current_version) {
				Object.keys(window.localStorage)
					.filter((k) => k.startsWith("_page:") || k === "metadata_version" || k === "page_info")
					.forEach((k) => window.localStorage.removeItem(k));
				if (window.caches && window.caches.keys) {
					window.caches.keys().then((names) => names.forEach((n) => window.caches.delete(n)));
				}
				window.localStorage.setItem(STORAGE_KEY, current_version);
				window.location.reload();
				return; // page is reloading -- don't run the rest against stale state
			}
			window.localStorage.setItem(STORAGE_KEY, current_version);
		}
	} catch (e) {
		// cache bookkeeping must never break the rest of the page
	}

	// ── Default the desk to full width ──────────────────────────────────────
	// "Toggle Full Width" (Display menu) is a plain localStorage flag core
	// Frappe reads on its own during desk boot (see desk.js's
	// set_fullwidth_if_enabled, called on startup) -- there's no per-user
	// server-side default for it. Set it to on only the first time a browser
	// has never expressed a preference (localStorage key entirely absent);
	// once a user explicitly toggles it either way, that choice is respected
	// and never overwritten here again.
	try {
		if (window.localStorage.getItem("container_fullwidth") === null) {
			window.localStorage.setItem("container_fullwidth", "true");
		}
	} catch (e) {
		// non-fatal -- worst case the desk just isn't full-width by default
	}

	// ── Keep "Defect" (Issue) inside the Projects sidebar, not Support ───────
	// Issue is relabeled "Defect" throughout the Projects/Mercury UI, but its
	// real home in core ERPNext is the "Support" module/workspace (legacy
	// ticketing, being deprecated in favor of the separate Helpdesk app this
	// system actually uses). Frappe's own sidebar resolver (frappe.ui.Sidebar,
	// see set_workspace_sidebar/get_workspace_sidebars in
	// frappe/public/js/frappe/ui/sidebar/sidebar.js) decides which sidebar to
	// show for a doctype route by checking which "Workspace Sidebar" record
	// lists that doctype as an item -- a *different* doctype from "Workspace"
	// (whose own Link/Shortcut rows only affect the workspace *page* content
	// and breadcrumb text, not this). Support's Workspace Sidebar record still
	// lists Issue, so any full navigation to Issue's list -- from anywhere:
	// this stat card, "View All Defects", the awesomebar, browser back/
	// forward -- flips the whole left sidebar to Support's branding.
	//
	// frappe.router's own "change" handler already calls
	// frappe.app.sidebar.set_workspace_sidebar(router) on every route change
	// (sidebar.js's setup_events); this listener is registered afterward, so
	// it always runs after that one and corrects its result rather than
	// racing it. set_workspace_sidebar's own re-run (e.g. via
	// frappe.app.sidebar.refresh() on page/form refresh) is idempotent when
	// the target hasn't changed, and our explicit .setup() call below is
	// itself idempotent too (Sidebar.setup() is the same method Frappe calls
	// internally), so this is safe to run on every route change without
	// fighting a later correction.
	try {
		frappe.router.on("change", function () {
			const route = frappe.get_route();
			// Covers List, Form, Report, Kanban, etc. -- any view of Issue.
			if (route[1] === "Issue" && frappe.app && frappe.app.sidebar) {
				frappe.app.sidebar.setup("Projects");
			}
		});
	} catch (e) {
		// non-fatal -- worst case Defect's sidebar reverts to core's own resolution
	}

	const DMS_DOCTYPES = new Set([
		"Document Library",
		"Document Request",
		"Document Revision",
		"Document Acknowledgement",
		"Document Category",
		"Document Type",
		"Approval Matrix",
		"DMS Audit Log",
		"DMS Curriculum",
		"DMS Curriculum Document",
		"DMS Project",
		"DMS Quiz",
		"DMS Quiz Question",
		"DMS Training Assignment Rule",
		"DMS Training Record",
		"DMS Training Score History",
		"DMS Training Session",
		"DMS Training Session Attendee",
		"Training Settings",
		"CFR Part 11 Signature Log",
		// core doctypes reached from the DMS workspace sidebar
		"File",
		"Workflow",
		"Workflow Action",
		"Department",
	]);
	const DMS_REPORTS = new Set([
		"Audit Trail Report",
		"Master Document List",
		"Overdue Training Report",
		"Training Compliance Report",
		"Training Matrix Report",
	]);
	// Custom Pages (not a DocType view or Report) -- frappe.get_route() for
	// these is just [page_name], so they need their own check below.
	const DMS_PAGES = new Set([
		"my-training-dashboard",
		"training-analytics",
	]);

	// The ERPNext Projects module reuses the same navy/blue theme so its
	// workspace, lists, and forms match the DMS look.
	const PROJECT_DOCTYPES = new Set([
		"Project",
		"Task",
		"Timesheet",
		"Project Template",
		"Project Type",
		"Project Update",
		"Activity Type",
		"Activity Cost",
		"Task Type",
		"Issue",
	]);
	const PROJECT_REPORTS = new Set([
		"Project Summary",
		"Daily Timesheet Summary",
		"Timesheet Billing Summary",
		"Project wise Stock Tracking",
		"Delayed Tasks Summary",
	]);

	// The Mercury manufacturing-journey workspace reuses the same navy/blue
	// theme as DMS so its overview and doctype cards match.
	const MERCURY_DOCTYPES = new Set([
		"Sales Order",
		"Purchase Order",
		"Quality Inspection",
		"Packing Slip",
		"Delivery Note",
		"Sales Invoice",
	]);

	function slug(txt) {
		return (txt || "").toString().toLowerCase().replace(/[\s_]+/g, "-");
	}

	// All workspaces belonging to the DMS module / quality_dms app,
	// including child workspaces (Folder Management, Compliance & Logs, …).
	function dms_workspace_slugs() {
		const pages =
			(frappe.boot && (frappe.boot.allowed_workspaces || frappe.boot.sidebar_pages?.pages)) || [];
		const slugs = new Set(["dms"]);
		for (const ws of pages) {
			const module = slug(ws.module);
			const app = slug(ws.app);
			const parent = slug(ws.parent_page);
			if (module === "dms" || app === "quality-dms" || app === "quality_dms" || parent === "dms" || slugs.has(parent)) {
				slugs.add(slug(ws.name));
				slugs.add(slug(ws.title));
			}
		}
		return slugs;
	}

	function is_dms_route() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		if (!route.length) return false;
		const view = route[0];
		const target = route[1] || "";
		if (view === "Workspaces") return dms_workspace_slugs().has(slug(target));
		if (view === "query-report") return DMS_REPORTS.has(target);
		if (slug(view) === "module-onboarding") return slug(target) === "dms";
		// any view of a DMS doctype: List, Form, Tree, Report, Kanban,
		// Calendar, Dashboard, Image, print…
		if (DMS_DOCTYPES.has(target)) return true;
		// custom Pages: frappe.get_route() is just [page_name] here, so `view`
		// itself (route[0]) is the page name, not a view-type keyword.
		if (DMS_PAGES.has(view)) return true;
		return false;
	}

	function is_projects_route() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		if (!route.length) return false;
		const view = route[0];
		const target = route[1] || "";
		if (view === "Workspaces") return slug(target) === "projects";
		if (view === "query-report") return PROJECT_REPORTS.has(target);
		// any view of a Projects doctype: List, Form, Kanban, Gantt, Report, …
		if (PROJECT_DOCTYPES.has(target)) return true;
		return false;
	}

	function is_mercury_route() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		if (!route.length) return false;
		const view = route[0];
		const target = route[1] || "";
		if (view === "Workspaces") return slug(target) === "mercury";
		// any view of a Mercury-journey doctype: List, Form, Report, …
		if (MERCURY_DOCTYPES.has(target)) return true;
		return false;
	}

	function apply() {
		document.body.classList.toggle(
			"dms-theme",
			is_dms_route() || is_projects_route() || is_mercury_route()
		);
	}

	// Curated Document Library entry points (Repository, ToDo, the
	// "Published Documents" Key Metrics card) should land on a pre-scoped view
	// that reads as the default list for that purpose, not as "a filter someone
	// applied and could remove." Hides just the clear-all-filters (X) button --
	// scoped to when the ONLY active filter is exactly one of these curated
	// ones, so a user's own manual filtering elsewhere is completely unaffected.
	const LOCKED_FILTER_SIGNATURES = [
		{ fieldname: "is_in_progress", value: "1", title: "ToDo" },
		{ fieldname: "workflow_state", value: "Published", title: "Repository" },
	];

	function apply_locked_filter_ui() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		const is_doc_library_list = route[0] === "List" && route[1] === "Document Library";
		if (!is_doc_library_list) {
			document.body.classList.remove("dms-locked-filter");
			return;
		}
		setTimeout(() => {
			try {
				const filters = (cur_list && cur_list.filter_area && cur_list.filter_area.get()) || [];
				const match =
					filters.length === 1 &&
					LOCKED_FILTER_SIGNATURES.find(
						(sig) => filters[0][1] === sig.fieldname && String(filters[0][3]) === sig.value
					);
				document.body.classList.toggle("dms-locked-filter", !!match);
				// Rename the page title/breadcrumb away from "Document Library" so
				// the curated view reads as its own page (Repository/ToDo),
				// matching the sidebar label the user actually clicked.
				if (match && cur_list && cur_list.page && cur_list.page.set_title) {
					cur_list.page.set_title(__(match.title));
				}
			} catch (e) {
				document.body.classList.remove("dms-locked-filter");
			}
		}, 400);
	}

	// The DMS sidebar uses friendly labels (e.g. "Curricula", "Classifications")
	// that don't match the underlying DocType/Report's own name, so the page
	// title/breadcrumb a user lands on can read completely differently from
	// what they clicked. Unlike the locked-filter case above, these apply
	// unconditionally to every view of that route (List/Report/Kanban/etc.),
	// not just one specific filter combination.
	//
	// Department and Workflow are deliberately excluded here even though the
	// DMS sidebar also links to them ("Departments", "Workflow Configuration")
	// — they're shared core doctypes used by HR and other modules, and
	// renaming their title globally would leak into those unrelated UIs.
	const ROUTE_TITLE_OVERRIDES = {
		"List/DMS Curriculum": "Curricula",
		"List/DMS Quiz": "Quizzes",
		"List/DMS Training Record": "Training Records",
		"List/DMS Training Session": "Training Sessions",
		"List/DMS Training Assignment Rule": "Assignment Rules",
		"List/DMS Audit Log": "Audit Logs",
		"List/CFR Part 11 Signature Log": "Signature Log",
		"List/Document Category": "Classifications",
		"List/Document Type": "Record Types",
		"List/Document Request": "Change Requests",
		"List/Document Revision": "Revision History",
		"query-report/Training Matrix Report": "Training Matrix",
		"query-report/Training Compliance Report": "Training Compliance",
		"query-report/Overdue Training Report": "Overdue Training",
	};

	// Query reports (and some list views) re-set their own page title
	// asynchronously after their data finishes loading, which can happen well
	// after any fixed setTimeout — a later re-render silently reverts a
	// one-shot override. A MutationObserver on the title element itself keeps
	// re-applying the override for as long as the matching route is active,
	// the same async-fights-back pattern already used for card accents below.
	let current_title_override = null;

	function apply_route_title_override() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		const key = `${route[0]}/${route[1]}`;
		current_title_override = ROUTE_TITLE_OVERRIDES[key] || null;
		if (current_title_override) {
			set_title_now(current_title_override);
		}
	}

	function set_title_now(title) {
		try {
			// Query reports don't use page.set_title()/.title-text at all —
			// frappe.breadcrumbs.update() (views/breadcrumbs.js) rebuilds the
			// breadcrumb's last <li> directly from frappe.query_report.page_title
			// on every call, including ones that happen well after page load as
			// the report's own data finishes loading. Overriding page_title and
			// re-running update() is the only override that survives that.
			if (frappe.get_route()[0] === "query-report" && frappe.query_report) {
				if (frappe.query_report.page_title !== __(title)) {
					frappe.query_report.page_title = __(title);
					frappe.breadcrumbs.update();
				}
				return;
			}
			const page =
				(cur_list && cur_list.page) ||
				(cur_page && cur_page.page);
			if (page && page.set_title && page.title !== __(title)) {
				page.set_title(__(title));
			}
		} catch (e) {
			// title override is cosmetic only — never break navigation over it
		}
	}

	const title_observer = new MutationObserver(() => {
		if (current_title_override) set_title_now(current_title_override);
		dms_render_notification_badge(dms_last_notification_count);
	});

	// ── Unread-notification badge on the sidebar "Notification" item and the
	// DMS app icon in the workspace grid (WhatsApp-style red count bubble).
	// The stock desk only shows a seen/unseen dot, not a number, so this adds
	// the count on top without touching core notification code.
	// Applied idempotently (skip when the DOM already matches) since it also
	// runs from the shared mutation observer below -- the workspace app-icon
	// grid renders asynchronously after the page's initial ready fires, so a
	// one-shot render on ready/route-change alone would miss it. A non-idempotent
	// version would re-trigger that same observer on every call, looping forever.
	function dms_apply_badge($el, label, badge_class) {
		if (!$el.length) return;
		const $existing = $el.find(".dms-notif-badge");
		// Some Frappe versions render their own native count badge in the
		// sidebar item's suffix (span.sidebar-notification-count) -- this dev
		// environment's version doesn't, so this went unnoticed until it
		// showed up doubled on a site running a newer core. When the native
		// one is present, it already does the job; adding ours on top would
		// just show the same number twice.
		const $nativeCount = $el.closest(".sidebar-notification").find(".sidebar-notification-count");
		if ($nativeCount.length) {
			$existing.remove();
			return;
		}
		if (!label) {
			$existing.remove();
			return;
		}
		if ($existing.length && $existing.text() === label) return;
		$existing.remove();
		$el.append(`<span class="dms-notif-badge ${badge_class || ""}">${label}</span>`);
	}

	// The app-icon tile is wider than the icon box itself (icon is centered,
	// caption sits below), and the icon box clips overflow at its own rounded
	// corners -- so the badge is appended to the tile (overflow: visible) but
	// positioned using the icon box's actual offset within it, not a fixed
	// CSS corner, otherwise it floats away from the icon at different tile sizes.
	function dms_apply_icon_badge($anchor, label) {
		if (!$anchor.length) return;
		const $existing = $anchor.find(".dms-notif-badge");
		if (!label) {
			$existing.remove();
			return;
		}
		const $icon = $anchor.find(".icon-container").first();
		if (!$icon.length) return;
		if ($existing.length && $existing.text() === label) return;
		$existing.remove();
		const $badge = $(`<span class="dms-notif-badge dms-notif-badge-icon">${label}</span>`);
		$anchor.append($badge);
		const badge_size = $badge.outerWidth() || 18;
		$badge.css({
			top: $icon.position().top - badge_size / 2,
			left: $icon.position().left + $icon.outerWidth() - badge_size / 2,
		});
	}

	let dms_last_notification_count = 0;

	function dms_render_notification_badge(count) {
		dms_last_notification_count = count || 0;
		const label = dms_last_notification_count > 0
			? (dms_last_notification_count > 99 ? "99+" : String(dms_last_notification_count))
			: null;

		dms_apply_badge($('.sidebar-notification[data-id="Notification"] .sidebar-item-control'), label);
		dms_apply_icon_badge($('a.desktop-icon[data-id="DMS"]'), label);
	}

	function dms_update_notification_badge() {
		if (!frappe.session || !frappe.session.user || frappe.session.user === "Guest") return;
		frappe.call({
			method: "frappe.client.get_count",
			args: {
				doctype: "Notification Log",
				filters: { for_user: frappe.session.user, read: 0 },
			},
		}).then((r) => {
			dms_render_notification_badge((r && r.message) || 0);
		});
	}

	$(document).ready(function () {
		apply();
		apply_locked_filter_ui();
		apply_route_title_override();
		dms_update_notification_badge();
		// Deferred to ready (not top-level) since this script loads via
		// app_include_js in <head> -- document.body may not exist yet at
		// parse time, and an error here would abort this whole IIFE,
		// silently disabling everything registered below it too.
		title_observer.observe(document.body, { childList: true, subtree: true, characterData: true });
		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", apply);
			frappe.router.on("change", apply_locked_filter_ui);
			frappe.router.on("change", apply_route_title_override);
			frappe.router.on("change", dms_update_notification_badge);
		} else {
			$(window).on("hashchange", apply);
			$(window).on("hashchange", apply_locked_filter_ui);
			$(window).on("hashchange", apply_route_title_override);
			$(window).on("hashchange", dms_update_notification_badge);
		}
		if (frappe.realtime && frappe.realtime.on) {
			frappe.realtime.on("notification", dms_update_notification_badge);
			frappe.realtime.on("indicator_hide", dms_update_notification_badge);
		}
		// Fallback poll in case the realtime socket connection is unavailable
		// (e.g. blocked/misconfigured websocket infra) — keeps the count from
		// going permanently stale for a logged-in session.
		setInterval(dms_update_notification_badge, 30000);
		// Marking read happens via clicks inside the notification dropdown
		// (an individual item, or "mark all as read") — refresh shortly after
		// so the badge drops immediately instead of waiting for the next poll.
		$(document).on("click", ".notification-list-body, .mark-all-read", () => {
			setTimeout(dms_update_notification_badge, 800);
		});
	});

	// Key Metrics cards: each Number Card doctype record already has its own
	// `color` field (set in the fixture JSON) but the stock widget only uses
	// it to tint the number text, not the card itself. Mirror that same
	// color onto the card wrapper as a CSS variable so quality_dms.css can
	// render a colored bottom accent, matching the Project Summary tab's
	// per-status stat cards. Matched by label text (not by patching
	// NumberCardWidget, which is bundled internally and not reachable from
	// an app_include_js script) via a MutationObserver, since cards render
	// asynchronously after their data fetch completes.
	const CARD_ACCENTS = {
		Documents: "#4C7CF3",
		Published: "#36AE7C",
		Review: "#E8A317",
		Approved: "#26A69A",
		Draft: "#ECAD4B",
		Obsolete: "#CB4B4B",
		"Pending Revision": "#FF6B6B",
		Revisions: "#6C63FF",
	};

	function apply_card_accents(root) {
		root.querySelectorAll(".number-widget-box").forEach((el) => {
			if (el.style.getPropertyValue("--card-accent")) return;
			const title_el = el.querySelector(".widget-title [title], .widget-title .ellipsis");
			const label = title_el && (title_el.getAttribute("title") || title_el.textContent).trim();
			if (label && CARD_ACCENTS[label]) {
				el.style.setProperty("--card-accent", CARD_ACCENTS[label]);
			}
		});
	}

	// "Documents by Status" donut chart: recolor to match the Key Metrics
	// palette above. Frappe Charts renders each slice as an SVG <path
	// class="donut-path"> with its color in an inline `stroke` style, and
	// each legend entry as a <rect fill="..."> immediately followed by a
	// text node with the status label -- both in the same index order, but
	// that order isn't stable (ties on count reshuffle it), so match by the
	// legend's own label text rather than assuming position.
	const STATUS_COLORS = {
		Draft: "#F4A623",
		"Documents in Review": "#4C7CF3",
		Review: "#4C7CF3",
		Approved: "#2E9E6C",
		Published: "#6C5CE7",
		Obsolete: "#D64550",
		Archived: "#6C757D",
		Rejected: "#A8324F",
	};

	function apply_status_chart_colors(root) {
		root.querySelectorAll(".widget-head").forEach((head) => {
			if (!head.textContent.includes("Documents by Status")) return;
			const widget = head.closest(".widget");
			if (!widget) return;

			const paths = Array.from(widget.querySelectorAll("svg path.donut-path"));
			const rects = Array.from(widget.querySelectorAll("svg rect"));
			if (!paths.length || !rects.length) return;

			// No "already done" guard: frappe-charts redraws the SVG (fresh
			// nodes) at least once after the first paint (ResizeObserver-
			// driven), which would silently revert a one-time recolor. This
			// runs on every relevant mutation instead -- cheap for 5 slices,
			// and a no-op once colors already match.
			rects.forEach((rect, i) => {
				const label = rect.nextSibling && rect.nextSibling.textContent && rect.nextSibling.textContent.trim();
				const color = label && STATUS_COLORS[label];
				if (!color) return;
				if (rect.getAttribute("fill") !== color) rect.setAttribute("fill", color);
				const path = paths[i];
				if (path) {
					const style = (path.getAttribute("style") || "");
					if (!style.includes(`stroke: ${color};`)) {
						path.setAttribute("style", style.replace(/stroke:\s*[^;]+;?/, `stroke: ${color};`));
					}
				}
			});
		});
	}

	// "Documents by Department" bar chart: frappe-charts only honors
	// custom_options.colors[0] for a single-series Bar chart (unlike a
	// Donut, which is inherently multi-segment) -- every bar renders in one
	// color no matter how many entries the colors array has. There's no
	// reliable department-name text in the DOM to match against (the x-axis
	// labels are truncated to "...", and the tooltip text isn't rendered
	// until hover), so bars are recolored by their stable data-point-index
	// instead, which matches the dataset's render order.
	const DEPARTMENT_COLORS = [
		"#4C7CF3", "#36AE7C", "#E8A317", "#26A69A", "#ECAD4B", "#CB4B4B", "#6C63FF", "#8E5CE6",
	];

	function apply_department_chart_colors(root) {
		root.querySelectorAll(".widget-head").forEach((head) => {
			if (!head.textContent.includes("Documents by Department")) return;
			const widget = head.closest(".widget");
			if (!widget) return;
			widget.querySelectorAll("svg rect.bar").forEach((rect) => {
				const idx = parseInt(rect.getAttribute("data-point-index"), 10);
				if (Number.isNaN(idx)) return;
				const color = DEPARTMENT_COLORS[idx % DEPARTMENT_COLORS.length];
				if (rect.style.fill !== color) rect.style.fill = color;
			});
		});
	}

	const card_observer = new MutationObserver((mutations) => {
		for (const m of mutations) {
			if (m.addedNodes.length) {
				apply_card_accents(document.body);
				apply_status_chart_colors(document.body);
				apply_department_chart_colors(document.body);
			}
		}
	});
	card_observer.observe(document.body, { childList: true, subtree: true });
})();
