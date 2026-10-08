// Toggles the navy sidebar theme on only when the Desk workspace sidebar
// currently resolved is "CRM" -- the sidebar is one persistent DOM element
// shared by every workspace (frappe/public/js/frappe/ui/sidebar/sidebar.js),
// so it can't be scoped by a static CSS selector the way the page canvas can.
// frappe.app.sidebar.sidebar_title is the same canonical "what workspace is
// showing" value Frappe itself sets, so this piggybacks on that rather than
// re-deriving the workspace from the route (which is private/internal logic
// that could change between Frappe versions).
(function () {
	// Catches a live theme toggle (Light/Dark/System switcher) independent of
	// any chart content change -- without this, switching to dark mode while
	// an empty-state overlay is showing would leave it visible (now unstyled,
	// since the CSS is light-mode-scoped) until some unrelated chart mutation
	// happened to trigger a recheck.
	new MutationObserver(function () {
		apply_crm_chart_empty_states();
	}).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

	function apply_crm_sidebar_theme() {
		var is_crm = frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title === "CRM";
		$(".body-sidebar-container").toggleClass("crm-desk-sidebar", !!is_crm);

		// Every page type (Dashboard, List, Form, Report, Setup) gets its own
		// .page-container (container.js's add_page(label) creates one per
		// route), and Frappe keeps previously-visited ones in the DOM, just
		// hidden, for faster revisits. So on every route change: strip the
		// class from all of them first (otherwise a page visited while in CRM
		// would keep the class forever, even after leaving CRM or if revisited
		// from a different workspace), then add it back only to the one
		// that's actually showing right now, and only while still in CRM.
		$(".page-container").removeClass("crm-desk-canvas");
		if (is_crm) {
			$(".page-container:visible").addClass("crm-desk-canvas");
		}

		apply_crm_dashboard_enhancements(is_crm);
	}

	// Dashboard-only additions (intro/greeting, Quick Actions, section labels).
	// /desk/dashboard-view/<name> is controlled by the `Dashboard` class in
	// frappe/core/page/dashboard_view/dashboard_view.js (a Frappe Page, NOT
	// the unrelated frappe.views.DashboardView list-view class of the same
	// name used elsewhere) -- its constructor builds
	// `.dashboard > .dashboard-graph` once, and show_dashboard() calls
	// `this.container.empty()` (.dashboard-graph) and rebuilds both
	// WidgetGroups only when switching to a *different* Dashboard record,
	// which is itself a route change (dashboard-view/<name>), so
	// router.on("change") alone already covers it -- confirmed live, this
	// page's widget options all set allow_edit/allow_sorting/etc. to false,
	// so there is no in-place customize/save re-render to additionally
	// handle. The MutationObserver below is kept only as a defensive no-op
	// safety net (e.g. "Refresh All" refreshes widgets in place and does not
	// trigger it), not because it's load-bearing for a real interaction.
	var dashboard_observer_attached = false;
	var chart_group_observer = null;
	var chart_group_observer_node = null;

	function apply_crm_dashboard_enhancements(is_crm) {
		var route = frappe.get_route();
		var on_dashboard = route[0] === "dashboard-view";

		// The dashboard-view page-container (and its Page object, including
		// page.custom_actions) is the one shared singleton reused by every
		// workspace with a Dashboard view (confirmed in the canvas/sidebar
		// work), so leaving CRM must explicitly remove what was added here --
		// render_dashboard()'s own .empty() would eventually clear the intro/
		// labels, but page.custom_actions lives outside that wrapper and
		// would otherwise leak the CRM-only Quick Action buttons onto another
		// workspace's dashboard.
		if (!is_crm || !on_dashboard) {
			$(".crm-dashboard-intro, .crm-section-label").remove();
			var page_obj = frappe.container.page && frappe.container.page.page;
			if (page_obj && page_obj.custom_actions) {
				page_obj.custom_actions.find("[data-crm-quick-action]").remove();
			}
			return;
		}

		var $wrapper = $(".dashboard-graph:visible");
		if (!$wrapper.length) return;

		// A. Intro/greeting -- real logged-in user, never a hardcoded name.
		if (!$wrapper.find(".crm-dashboard-intro").length) {
			var hour = new Date().getHours();
			var greeting =
				hour < 12 ? __("Good morning") : hour < 17 ? __("Good afternoon") : __("Good evening");
			var user_label = frappe.session.user_fullname || frappe.session.user;
			$(
				'<div class="crm-dashboard-intro">' +
					'<div class="crm-dashboard-intro-greeting">' +
					frappe.utils.escape_html(greeting + ", " + user_label) +
					"</div>" +
					'<div class="crm-dashboard-intro-subtitle">' +
					__("Here's what's happening with your sales pipeline.") +
					"</div>" +
					"</div>"
			).prependTo($wrapper);
		}

		// D. Section labels -- inserted as siblings only, never wrapping or
		// reparenting the native .widget-group (Frappe's own customize-mode
		// drag/sort reads that DOM directly).
		var $numberCardGroup = $wrapper
			.find(".widget-group")
			.filter(function () {
				return $(this).find(".number-widget-box").length > 0;
			})
			.first();
		if ($numberCardGroup.length && !$numberCardGroup.prev(".crm-section-label").length) {
			$('<div class="crm-section-label">' + __("Overview") + "</div>").insertBefore(
				$numberCardGroup
			);
		}

		var $chartGroup = $wrapper
			.find(".widget-group")
			.filter(function () {
				return $(this).find(".dashboard-widget-box").length > 0;
			})
			.first();
		if ($chartGroup.length && !$chartGroup.prev(".crm-section-label").length) {
			$('<div class="crm-section-label">' + __("Activity") + "</div>").insertBefore($chartGroup);
		}

		// A per-chart action (its own "Refresh"/"Reset Chart" menu item) calls
		// make_chart() again, which replaces that one chart's chart_wrapper
		// node entirely (confirmed live) without any route change -- this
		// group-level observer re-runs apply_crm_chart_empty_states() whenever
		// anything changes anywhere under the chart widget-group, so
		// crm_setup_chart_empty_state() notices the new wrapper (via its own
		// isConnected check) and re-attaches to it. Guarded by node identity,
		// not a plain boolean: $chartGroup itself is recreated on a route
		// change away from and back to this Dashboard (the whole
		// .dashboard-graph is torn down and rebuilt), which would otherwise
		// leave this observer watching a detached, dead node forever.
		if ($chartGroup.length && chart_group_observer_node !== $chartGroup.get(0)) {
			if (chart_group_observer) chart_group_observer.disconnect();
			chart_group_observer = new MutationObserver(function () {
				apply_crm_chart_empty_states();
			});
			chart_group_observer.observe($chartGroup.get(0), { childList: true, subtree: true });
			chart_group_observer_node = $chartGroup.get(0);
		}

		// B. Quick Actions -- page.custom_actions lives outside .dashboard-view
		// (it's the Page object's own action bar), so it survives the
		// customize/save/discard rebuild untouched; only needs adding once.
		var page = frappe.container.page && frappe.container.page.page;
		if (page && page.custom_actions && !page.custom_actions.find("[data-crm-quick-action]").length) {
			[
				{ label: __("New Lead"), make: () => frappe.new_doc("Lead") },
				{ label: __("New Opportunity"), make: () => frappe.new_doc("Opportunity") },
				{ label: __("New Customer"), make: () => frappe.new_doc("Customer") },
				{ label: __("New Appointment"), make: () => frappe.new_doc("Appointment") },
			].forEach(function (action) {
				page
					.add_button(action.label, action.make, { btn_class: "btn-default" })
					.addClass("crm-quick-action-btn")
					.attr("data-crm-quick-action", action.label);
			});
		}

		// Re-run (idempotently) whenever render_dashboard() empties/rebuilds
		// .dashboard-view, since that happens without a route change.
		if (!dashboard_observer_attached && $wrapper.get(0)) {
			var observer = new MutationObserver(function () {
				apply_crm_dashboard_enhancements(
					frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title === "CRM"
				);
			});
			observer.observe($wrapper.get(0), { childList: true });
			dashboard_observer_attached = true;
		}

		apply_crm_chart_empty_states();
	}

	// Empty-state overlay for the 3 named time-series charts only (not
	// generalized to every chart type). Deliberately never touches
	// chart_wrapper's own visibility: ChartWidget.render() (chart_widget.js)
	// calls chart_wrapper.show() unconditionally whenever the fetched data
	// has a valid labels/datasets shape -- which is true even when every
	// value is zero, since Frappe's own "empty" check only looks at the data
	// *shape*, not its values. If we called .hide()/.show() on chart_wrapper
	// ourselves, every native render (including the ones for in-place filter/
	// period changes) would immediately re-show it over us, racing our own
	// state and risking exactly the "stuck hidden" / flicker failure modes
	// this task explicitly warns against. Instead this inserts one additive
	// sibling overlay per chart, toggled purely by our own read of
	// widget.data -- the native chart underneath is never altered, so there
	// is nothing to "restore": removing/hiding our overlay IS the restore.
	var CRM_EMPTY_STATE_CHART_NAMES = ["Incoming Leads", "Opportunity Trends", "Won Opportunities"];

	function crm_chart_is_all_zero(widget) {
		if (!widget.data || !Array.isArray(widget.data.datasets)) return false;
		var saw_a_value = false;
		for (var i = 0; i < widget.data.datasets.length; i++) {
			var values = widget.data.datasets[i] && widget.data.datasets[i].values;
			if (!Array.isArray(values)) continue;
			for (var j = 0; j < values.length; j++) {
				saw_a_value = true;
				var v = values[j];
				if (v !== 0 && v !== null && v !== undefined && !isNaN(v)) {
					return false;
				}
			}
		}
		// Only claim "all zero" once we've actually seen a dataset with
		// values to judge -- an empty/not-yet-loaded dataset is not the same
		// claim as a confirmed all-zero one, and must defer to Frappe's own
		// native "Loading..."/"No Data" states instead of showing ours.
		return saw_a_value;
	}

	function crm_update_chart_empty_state(widget) {
		if (!widget.$crm_empty_state || !widget.chart_wrapper) return;
		// The CSS only positions/styles this overlay under
		// html:not([data-theme='dark']) -- dark mode must stay completely
		// native, not just differently-styled, so the JS mirrors that scoping
		// here rather than relying on CSS alone. Without this check, dark
		// mode would still show the overlay as an unstyled block (no absolute
		// positioning, no background) stacked below the native chart instead
		// of over it -- confirmed live, a real defect, not a hypothetical.
		var is_dark = document.documentElement.getAttribute("data-theme") === "dark";
		var is_empty = !is_dark && crm_chart_is_all_zero(widget);
		widget.$crm_empty_state.toggle(is_empty);
	}

	function crm_setup_chart_empty_state(widget) {
		if (!widget.chart_wrapper || !widget.chart_wrapper.length) return;

		var current_wrapper_node = widget.chart_wrapper.get(0);

		// A one-time flag tied to the widget object is not enough: the chart
		// menu's "Refresh" action (and "Reset Chart") call make_chart() again,
		// which re-runs setup_container() -- that does this.body.empty() and
		// creates a brand-new chart_wrapper element, detaching the old one
		// (and our overlay, inserted as its sibling) from the document.
		// Confirmed live: after a refresh, the old chart_wrapper node and our
		// old overlay both end up with isConnected === false. So re-create
		// (and re-observe) whenever the wrapper identity has changed or our
		// previous overlay is no longer actually in the document, rather than
		// trusting a flag that only reflects "did we ever run once".
		var already_current =
			widget._crm_last_wrapper_node === current_wrapper_node &&
			widget.$crm_empty_state &&
			widget.$crm_empty_state.get(0) &&
			widget.$crm_empty_state.get(0).isConnected;
		if (already_current) {
			crm_update_chart_empty_state(widget);
			return;
		}

		if (widget._crm_observer) {
			widget._crm_observer.disconnect();
			widget._crm_observer = null;
		}

		widget.$crm_empty_state = $(
			'<div class="crm-chart-empty-state">' +
				'<svg class="icon icon-md crm-chart-empty-state-icon"><use href="#icon-small-file"></use></svg>' +
				'<div class="crm-chart-empty-state-title">' +
				__("No activity yet") +
				"</div>" +
				'<div class="crm-chart-empty-state-subtitle">' +
				__("Activity will appear here once records are created.") +
				"</div>" +
				"</div>"
		)
			.hide()
			.insertAfter(widget.chart_wrapper);

		// Re-check on every mutation the chart's own render()/dashboard_chart.
		// update() makes to chart_wrapper. attributes+subtree is needed, not
		// just childList: an in-place chart.update() (the path taken for
		// filter/time-interval/timespan changes on an already-rendered chart)
		// can mutate existing SVG element attributes (e.g. path "d") without
		// adding/removing any nodes, which a childList-only observer would
		// silently miss.
		var observer = new MutationObserver(function () {
			crm_update_chart_empty_state(widget);
		});
		observer.observe(current_wrapper_node, { childList: true, subtree: true, attributes: true });
		widget._crm_observer = observer;
		widget._crm_last_wrapper_node = current_wrapper_node;

		crm_update_chart_empty_state(widget);
	}

	function apply_crm_chart_empty_states() {
		// Guard independently of apply_crm_dashboard_enhancements's own check,
		// since this also runs from standalone staggered timeouts (route
		// change / document ready) that can fire after the user has already
		// navigated away from the CRM dashboard.
		var is_crm = frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title === "CRM";
		var route = frappe.get_route();
		if (!is_crm || route[0] !== "dashboard-view") return;

		var dashboard = frappe.dashboard;
		var group = dashboard && dashboard.chart_group;
		if (!group || !Array.isArray(group.widgets_list)) return;

		group.widgets_list.forEach(function (widget) {
			var chart_name = widget.chart_doc && (widget.chart_doc.chart_name || widget.chart_doc.name);
			if (CRM_EMPTY_STATE_CHART_NAMES.indexOf(chart_name) === -1) return;
			crm_setup_chart_empty_state(widget);
		});
	}

	// setTimeout defers to the next tick, after sidebar.js's own
	// router.on("change") listener (registered earlier, during desk boot)
	// has already resolved and set sidebar_title for the new route.
	frappe.router.on("change", function () {
		setTimeout(apply_crm_sidebar_theme, 0);
		// Charts fetch their permitted list via a separate xcall
		// (Dashboard.render_charts() in frappe/core/page/dashboard_view/
		// dashboard_view.js) and only then construct chart_group, so a
		// single immediate check after a route change can land before any
		// chart widgets exist yet. Staggered retries (same pattern as the
		// sidebar/canvas toggle) give that fetch time to land without
		// polling indefinitely; each call is a cheap no-op once already set
		// up (_crm_empty_state_setup guard).
		setTimeout(apply_crm_chart_empty_states, 600);
		setTimeout(apply_crm_chart_empty_states, 1500);
		setTimeout(apply_crm_chart_empty_states, 3000);
	});
	$(document).on("page-change", function () {
		setTimeout(apply_crm_sidebar_theme, 0);
	});

	// A cold page refresh can finish document.ready before the dashboard
	// widgets (and their page-container) have actually rendered, so the
	// canvas-side toggle would silently find nothing to apply to. The
	// function is idempotent (toggleClass with a boolean), so re-running it
	// once more shortly after is a plain no-op everywhere else.
	$(document).ready(function () {
		setTimeout(apply_crm_sidebar_theme, 0);
		setTimeout(apply_crm_sidebar_theme, 800);
		setTimeout(apply_crm_chart_empty_states, 1500);
		setTimeout(apply_crm_chart_empty_states, 3000);
	});
})();
