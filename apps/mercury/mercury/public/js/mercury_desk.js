/* Mercury desk JS overrides.
 *
 * Loaded on every desk page via hooks.app_include_js. Additive only - we wrap
 * core functions instead of editing them, so removing the hook line reverts
 * everything. No frappe/erpnext file is patched.
 *
 * =========================================================================
 * PROTECTED - DO NOT DELETE OR "CLEAN UP" WHEN MERGING.
 * Full rationale + verification checklist: documents/PROJECT_UI_CHANGES.md
 * =========================================================================
 */

frappe.provide("mercury.breadcrumbs");

/* ------------------------------------------------------------------------
 * Breadcrumb destinations on desk list/form routes.
 *
 * Stock v16 builds three crumbs from three independent sources
 * (frappe/public/js/frappe/views/breadcrumbs.js):
 *
 *   1. home icon      clear() :278                 -> "/desk"
 *   2. workspace      set_workspace_breadcrumb() :136-141 -> the workspace
 *   3. doctype list   set_list_breadcrumb() :216   -> "/desk/<doctype>"
 *
 * Two problems on a Task form (/desk/task/TASK-2026-00007):
 *
 *   a. The home icon points at "/desk", which workspace.js:137-155 resolves to
 *      localStorage.current_page - the LAST WORKSPACE THE BROWSER VISITED. So it
 *      usually lands on the same page as crumb 2, and its destination is not
 *      stable across machines or browsers. On a fresh QA browser it falls back
 *      to this.workspaces[0], which is not Projects.
 *
 *   b. Crumb 2 ("Projects", the workspace) and crumb 3 ("Project"/"Task", the
 *      doctype) read as near-duplicates, and neither reaches the Project LIST
 *      from a Task form.
 *
 * Wanted instead:
 *      home icon  -> the module's workspace home  (stable, never "last visited")
 *      "Projects" -> the Project list
 *      "Task"     -> the Task list  (already correct in core, left alone)
 *
 * We do not re-implement the breadcrumbs: we let core build them, then rewrite
 * two hrefs. That way any upstream change to labels, translation, ordering or
 * the Custom-breadcrumb path keeps working.
 *
 * Keyed on the workspace ROUTE, not the visible label: the label is passed
 * through __() so it changes under a non-English locale, and the map would
 * silently stop matching.
 * ------------------------------------------------------------------------ */

// workspace route  ->  where its breadcrumb crumb should actually go.
// Add an entry per module that wants its crumb to reach a list instead of the
// workspace. No entry = stock behaviour (crumb keeps pointing at the workspace).
mercury.breadcrumbs.CRUMB_TARGETS = {
	"/desk/projects": "/desk/project",
};

mercury.breadcrumbs.retarget = function () {
	// NOTE: "worksapce-breadcrumb" is misspelled in frappe core
	// (breadcrumbs.js:140). Do NOT "correct" it here or the selector misses.
	$(".navbar-breadcrumbs").each(function () {
		const $container = $(this);
		const $workspace_crumb = $container.find("li a.worksapce-breadcrumb");

		// No workspace crumb: a Custom-breadcrumb page (breadcrumbs.js:56), or a
		// doctype whose module is blocked/hidden. Leave it entirely alone.
		if (!$workspace_crumb.length) return;

		const workspace_route = $workspace_crumb.attr("href");
		if (!workspace_route) return;

		// 1. Home icon -> the module workspace, instead of the stateful "/desk".
		//    The home icon is always the first <li> (appended by clear() :278).
		const $home = $container.find("li").first().find("a");
		if ($home.length && $home.attr("href") === "/desk") {
			$home.attr("href", workspace_route);
		}

		// 2. Workspace crumb -> the module's list page, where one is mapped.
		const target = mercury.breadcrumbs.CRUMB_TARGETS[workspace_route];
		if (target) {
			$workspace_crumb.attr("href", target);
		}
	});
};

// Wrap rather than replace: core owns the building, we only adjust the result.
// update() runs on every route change and after rename(), so this stays applied.
(function () {
	if (!frappe.breadcrumbs || frappe.breadcrumbs.__mercury_wrapped) return;

	const core_update = frappe.breadcrumbs.update;
	frappe.breadcrumbs.update = function () {
		core_update.apply(this, arguments);
		try {
			mercury.breadcrumbs.retarget();
		} catch (e) {
			// Never let a breadcrumb tweak break navigation.
			console.error("mercury: breadcrumb retarget failed", e);
		}
	};
	frappe.breadcrumbs.__mercury_wrapped = true;
})();

/* ------------------------------------------------------------------------
 * White-label the About dialog.
 *
 * frappe/public/js/frappe/ui/toolbar/about.js hardcodes the Frappe wordmark,
 * the "Open Source applications for the web." tagline, frappe.io / github /
 * discuss links, a "Frappe Framework Version" row and the copyright footer.
 * None of it is hookable, so the whole function is replaced here rather than
 * editing the core file.
 *
 * The app list also showed letter tiles because render_app_icon() falls back to
 * a letter whenever get_versions() (frappe/utils/change_log.py:117-123) finds
 * neither add_to_apps_screen[0].logo nor app_logo_url on the app. Rather than
 * add a hook to each of erpnext/hrms/helpdesk - core apps we do not patch - the
 * logos are mapped here.
 *
 * Footer attribution reads Hephzibah Technologies, per Paul on 2026-08-20.
 * The LICENSE files and source copyright headers in apps/frappe and
 * apps/erpnext are untouched - that is where GPLv3 requires the notice.
 * --------------------------------------------------------------------- */

frappe.provide("mercury.about");

mercury.about.BRAND = "SBIQC";
mercury.about.TAGLINE = "Small Business Intelligent, Quality & Compliance";
mercury.about.MARK = "/assets/mercury/images/htipl_logo.png";

mercury.about.APP_LOGOS = {
	erpnext: "/assets/mercury/images/htipl_logo.png",
	hrms: "/assets/quality_dms/images/desktop_icons/frappe_hr.png",
	quality_dms: "/assets/quality_dms/images/desktop_icons/sbiqc.png",
	sbiqc_provisioning: "/assets/quality_dms/images/desktop_icons/sbiqc_provisioning.png",
	mercury: "/assets/mercury/images/desktop_icons/mercury.png",
	helpdesk: "/assets/helpdesk/icons/desktop_icons/solid/helpdesk.svg",
	telephony: "/assets/mercury/images/desktop_icons/sbiqc_erp.svg",
};

(function () {
	if (!frappe.ui || !frappe.ui.misc || frappe.ui.misc.__mercury_about) return;

	// Core appends the checkout's git branch to every version, which leaks our
	// internal branch names to customers - "(paul-update)" locally and
	// "(staging-deployment)" on QA. Only a release line like "version-16" is
	// meaningful to show, so everything else is dropped.
	const RELEASE_BRANCH = /^version-\d+$/i;

	const version_text = function (app) {
		return app.branch && RELEASE_BRANCH.test(app.branch)
			? `${app.version} (${app.branch})`
			: app.version;
	};

	const app_icon = function (app_name, app) {
		const logo = mercury.about.APP_LOGOS[app_name] || app.logo;
		const letter = (app.title || app_name).charAt(0).toUpperCase();
		if (logo) {
			return `<img src="${frappe.utils.escape_html(logo)}" class="about-app-logo" alt="${letter}">`;
		}
		const palette = frappe.get_palette(app_name);
		return `<div class="about-app-icon" style="background-color: var(${palette[0]}); color: var(${palette[1]});">${letter}</div>`;
	};

	frappe.ui.misc.about = function () {
		if (frappe.ui.misc.about_dialog) {
			frappe.ui.misc.about_dialog.show();
			return;
		}

		const dialog = new frappe.ui.Dialog({ title: __("About") });
		$(dialog.wrapper).addClass("about-dialog");

		$(dialog.body).html(
			`<div class="about-body">
				<div class="about-frappe-section">
					<img src="${mercury.about.MARK}" alt="${mercury.about.BRAND}"
						class="about-frappe-wordmark" style="height:56px;width:auto;">
					<p class="about-tagline" style="font-weight:600;letter-spacing:.02em;">
						${__(mercury.about.BRAND)}
					</p>
					<p class="about-tagline">${__(mercury.about.TAGLINE)}</p>
				</div>

				<div class="about-section-label">${__("Installed Apps")}</div>
				<div id="about-app-versions" class="about-app-list"></div>
			</div>`
		);

		$(dialog.footer)
			.removeClass("hide")
			.prepend(
				`<div class="about-footer">
					${__("&copy; {0} {1}. All rights reserved.", [
						new Date().getFullYear(),
						mercury.about.BRAND,
					])}
					<div style="opacity:.55;font-size:11px;margin-top:2px;">
						${__("&copy; Hephzibah Technologies Pvt. Ltd.")}
					</div>
				</div>`
			);

		const show_versions = function (versions) {
			const $wrap = $("#about-app-versions").empty();
			for (const app_name in versions) {
				// the framework row is deliberately gone; do not list it as an app either
				if (app_name === "frappe") continue;
				const app = versions[app_name];
				$(
					`<div class="about-app-row" title="${app_name}: ${app.version}">
						${app_icon(app_name, app)}
						<div class="about-app-info">
							<div class="about-app-name">${__(app.title)}</div>
							<div class="about-app-version">${app_name}: ${version_text(app)}</div>
						</div>
					</div>`
				).appendTo($wrap);
			}
			frappe.versions = versions;
		};

		dialog.on_page_show = function () {
			if (frappe.versions) return show_versions(frappe.versions);
			frappe.call({
				method: "frappe.utils.change_log.get_versions",
				callback: (r) => show_versions(r.message),
			});
		};

		frappe.ui.misc.about_dialog = dialog;
		dialog.show();
	};

	frappe.ui.misc.__mercury_about = true;
})();
