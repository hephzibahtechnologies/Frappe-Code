# Mercury ERP (Frappe Bench) — Change & Deployment Log

Internal tracking of everything pushed to GitHub and the features shipped, so we
can roll back cleanly if a future change goes wrong.

- **Repository:** https://github.com/hephzibahtechnologies/Frappe-Code
- **Primary branch:** `paul-update` (our working branch, also on the remote)
- **Other branches of interest:** `DMS` (project-module customisation), `staging-deployment`, `main`
- **Deprecated remote:** `origin` = `Lijishwilson-HTIPL/Frappe-Code` — do **not** push there. Use remote `hephzibah`.
- **Local working copy:** `\\wsl.localhost\Ubuntu-22.04\home\paul\frappe-bench` (a real git repo, unlike the xellabs ZIP)
- **Platform:** ERPNext v16 / Frappe v16 · **Demo site:** `mysite.local` · login `Administrator`
- **Author rule:** Paul Sahaya Doss is the sole commit author — never add a Claude/Anthropic co-author trailer.
- Related but different: `CHANGELOG_DRAFT.md` (repo root) is a repo-wide feature log by
  date/branch with no commit IDs. **This** file is the Mercury project log with commit IDs
  and rollback targets.

---

## Current state

**Latest on `paul-update`:** `5ca629a0e` — the SBIQC white-labelling / desk-icon round
(2026-08-18 → 20). Pushed.

**On staging and live on QA:** PR **#29** (merged as `5db2d3cbd`), then PR **#30**
(ponnambalaraju, merged as `a01626d2f`) on top of it. `a01626d2f` contains `5db2d3cbd`, so
the image built from it carries both. **Deploy to Staging #59** ran 2026-08-19 15:58 and
succeeded — the icon, white-labelling and SBIQC Support work is live on `qa.sbiqc.com`.

> ### ⚠️ NOT YET ON STAGING
> Four commits are on **`paul-update` only** — the About-dialog round
> (`7184eb288` → `5ca629a0e`). Not merged, not deployed.

> ### The trap this round exposed: local ≠ repo
> For most of 2026-08-18 the icon and branding work existed **only in the working tree and
> the local database**, so the desk looked finished while the repo had nothing. PR #28 was
> handed to the admin team in that state and deployed exactly what it contained: nothing.
> Nobody did anything wrong. **Before asking for a deploy, run `git status` and confirm the
> commits are on the remote** — a green desk locally proves nothing.

**Previously deployed to QA:** PR **#16** (`paul-update` → `staging-deployment`, merged as
`f1e3606`), then a **manual** Deploy to Staging run. Verified live on `qa.sbiqc.com`:
Assign tab, real ToDo assignment, Assign To list column.

> ### ⚠️ THE CI NO LONGER DEPLOYS ON PUSH
>
> `6a309a4a3` (ponnambalaraju) split the workflows:
> - **`build.yml`** — runs on push to `staging-deployment` / `production`. **Build only**, pushes images to GHCR.
> - **`deploy-staging.yml`** / **`deploy-production.yml`** — **`workflow_dispatch` only.** *"this never runs on push."*
>
> Merging to `staging-deployment` therefore does **not** reach the QA server. Someone
> must run **Actions → Deploy to Staging** (tag `latest-staging`) once the build is green.
> The deploy script runs `bench --site all migrate`, force-reimports the DMS fixtures, and
> clears the server cache. Assets are baked into the image — no separate `bench build`.

> ### ⚠️ NOTICE — two known blockers, deliberately NOT fixed
>
> Both were found on 2026-08-06 while answering how to fill the Task date columns.ok 
> Paul tested the demo path and it works for him, so these were left alone rather
> than changed the night before. They are **latent, not cosmetic** — each has a
> definite trigger:
>
> **1. `PROJ-0001.expected_end_date = 2026-08-03` — in the past.**
> `task.py:120-136 validate_parent_project_dates` throws if *any* task date
> (expected **or** actual) is after the project's expected end date. Triggers when
> someone types an Expected Start/End Date on a Mercury task, **or submits a
> Timesheet** — `timesheet.py:182` saves the Task and re-runs the same validation.
> *Fix:* push PROJ-0001's Expected End Date into the future. One field.
>
> **2. `Delivered` → `Overdue`, overnight.**
> `task.py:319-325 update_status` (nightly `set_tasks_as_overdue`) flips anything
> not `Cancelled`/`Completed` with a past `exp_end_date`. **`Delivered` is not on
> that safe list**, and `TASK-2026-00001` is Delivered. Cannot fire today because
> every Mercury task has `exp_end_date = NULL`; fires the first night after any
> end date is set. *Fix:* override `update_status` **from the mercury app** — do
> not patch erpnext core.
>
> Related: `timesheet.py:178-181` force-sets a Task to `Completed`/`Working` on
> Timesheet submit, which **destroys a Delivered status**. Do not log a Timesheet
> against `TASK-2026-00001`.

**Rollback targets (newest first):**

| Tag / commit | What it is |
|---|---|
| `b8d5110cc` | last state before the template-assignee exemption |
| `2f2e3d065` | last state before the 2026-08-06 Project/Task UI round |
| `96eda0dd3` — tag **`pre-staging-merge-2`** | last state before the *second* `staging-deployment` merge |
| `38932a7b4` — tag **`pre-staging-merge`** | last state before the first `staging-deployment` merge |
| `3c8dd4878` — tag **`pre-dms-merge`** | last state before the `DMS` merge |
| `b5583b40d` (2026-07-22) | Mercury baseline, before any Mercury work |

**Phase status:** Phase 1 = COMPLETE (all 8 stages, config-only; only custom code is the
~3-line QR jinja helper in `apps/mercury/mercury/utils.py`). Management feedback item #1
delivered. Phase 2 (Shipment Acknowledgement DocType + QR portal) not started.

---

## `5ca629a0e` — SBIQC white-labelling + desktop/sidebar icons (2026-08-18 → 20) · PUSHED

Started as "the ten Projects sidebar entries share one generic glyph" and turned into the
full white-label pass. Delivered as `after_migrate` hooks in **mercury** plus a JS override,
so erpnext is not patched — it re-asserts these records on **every** migrate (each run
reports changes being re-applied, which is the proof the hooks are needed).

**Shipped**

- Ten Projects sidebar icons; `frappe` substitutes `list` when `icon` is blank
  (`sidebar_item.js:93`). Names validated against the live lucide sprite.
- Desk grid: erpnext nests its workspaces under one ERPNext tile via `parent_icon`, and
  `get_desktop_icons()` drops anything with a parent — flattened, real image on all 24.
- Favicon, page loader, login logo, window title — all were **unset**, so frappe/erpnext
  defaults showed through. Now the HTIPL mark and "SBIQC".
- Help dropdown "Frappe Support" → **SBIQC Support** → `https://docs.sbiqc.com`.
- About dialog white-labelled, app icons mapped, internal branch names suppressed.
- Login page lost both scrollbars; `mercury`/`sbiqc_provisioning` released as **1.0.0**.

**Five traps, each of which cost real time — do not rediscover these**

1. **`logo_url` is a plain URL and need not live in the record's own app.** Repointing a
   standard Desktop Icon's `app` instead gets it **deleted** by migrate's orphan sweep
   (`model/sync.py:211,250` — filters `standard=1`, requires a matching
   `desktop_icon/<scrub>.json`). This destroyed Accounting, DMS and SBIQC Settings; they
   were restored from their owning apps' fixtures.
2. **The `/desk` grid renders a per-user `Desktop Layout` JSON snapshot, not the Desktop
   Icon table.** The sidebar flyout reads the live records. Change one and the two
   disagree — this is why the grid "ignored" every fix for hours.
3. **Never sync `label` into that snapshot.** Folders are keyed by *label* but children
   reference the parent by *name*, so relabelling a parent orphans every child onto the
   root grid (~18 loose tiles).
4. **A Folder can never show an icon.** `render_folder_thumbnail()` (`desktop.js:1057`)
   clears `.icon-container` and rebuilds it from the children — the collage *is* the icon.
   Accounting had to stop being a Folder.
5. **A record's `name` is not its `label`.** "SBIQC Settings" is really the doc
   `ERPNext Settings`. Any snapshot lookup must fall back to a label match.

Also: `import_file` skips a standard record whose `modified` timestamp has not moved, so a
workspace JSON edit silently no-ops until you bump it. Mercury2 removal is pinned to
`LOCAL_SITES` — it deletes a Workspace and the hook runs on every site.

**Rollback:** `3ef011dbc` is the last state before this round.

---

## `a50434f20` — delivery-acknowledgement scoping + staging round-trip (2026-08-18) · PUSHED

**Design and documentation only. No application behaviour changed.**

First batch of suggestions from the Alex demo: a minimal customer delivery-acknowledgement
view, and one that works at remote sites with no connectivity. Scoped, not built.

- `documents/alex_questions_delivery_ack.md` — seven questions written **for Alex**, ready
  to send. The decisive one is *whose phone does the scanning* — if deliveries go by
  third-party freight, it cannot be the driver's, so it falls to the customer's receiving
  clerk, and that answer changes the entire build.
- `workprogress_mercury.txt` §20 — the full record: Paul's answers (per-item scanning, no
  signature, same flow online and offline, notify immediately when online), the proposed
  architecture, and three risks flagged before anyone builds against them.

**The constraint that breaks the obvious design**, recorded so nobody rediscovers it the
hard way: *a web page cannot be opened on a device that has never loaded it.* Offline
storage keeps a page working **after** first load; it cannot put the page on a phone that
has never seen it. So the requirement is not "internet at the delivery" but **"internet at
least once, ever, on that device"** — much softer, and probably satisfiable.

Proposed architecture: the Stage 6 QR labels carry a **self-contained signed payload**, so
the phone learns about the delivery *from the box* rather than from our server — a delivery
created today can then be acknowledged by a phone that has been offline a week. The phone is
a dumb capture device; the **server does all verification and reconciliation on sync**.

Risks flagged: **iOS clears script-writable storage after ~7 days of non-use** (the most
likely way this design loses data); device clocks are unverifiable offline, so
`acknowledged_at` and `synced_at` must be stored separately; and Mercury is blind between
delivery and sync, hence the proposed *"delivered, not yet acknowledged"* report.

Merged `staging-deployment` (4 commits: PR #26 = our own work coming back, PR #27 DMS,
`fb9610536` moving **Defect (Issue)** into the Projects sidebar, and a CI change that
force-reimports the Projects/Support workspaces). **No conflicts.** Verified rather than
assumed, because a forced workspace reimport is exactly how the aurora cards would silently
revert: `bench migrate` clean, markers **28/28**, `mercury_desk.css` still **LAST** in
`app_include_css` (8 of 8), Mercury sidebar still carries *Project Update*, **0** labels
containing `(via …)`, Assign tab present with `custom_assign_to.mandatory_depends_on =
eval:!doc.is_template`, Task `Delivered` present, both print formats still the DocType
defaults, both Client Scripts enabled, `demo_hide` still wired.

Rollback-before-this: `pre-staging-merge-7` (= `3f28f3cd3`)

---

## `fdc852185` … `c28b9ee95` — Alex / job 1105VS10 (2026-08-11 → 13) · **MERGED TO `staging-deployment`**

**On staging since 2026-08-14** via PR #26 (merge commit `341535c95`). The earlier
"not on staging" warning no longer applies.

⚠️ **Merging did not deploy.** `deploy-staging.yml` is `workflow_dispatch` only — the
staging *site* runs the old build until someone runs the workflow by hand.

⚠️ **Assignee is now mandatory on Task.** Existing tasks on staging/QA have none and will
fail validation the moment anyone edits one. Only the local bench was backfilled.

Mercury's own two client documents, regenerated from live data for Alex's demo. Configuration
only: print formats, Property Setters, Custom Fields, fixtures. No custom doctypes — the QR
acknowledgement app remains Phase 2. Front-end walkthrough is in
`web docs/mercury_phase1_stepbystep_guide2` PART 2.

**Documents built**

| Print Format | On | Reproduces |
|---|---|---|
| `Mercury Project Schedule` | Project | document **103-1105VS10** — 10 phase groups, 81 tasks, Days, Status %, all 5 progress payments and both customer hold points, General Notes, job footer |
| `Mercury Progress Report` | Project Update | **1105VS10-PR-250623-EVP** — navy band, Project/Customer/PO block, A–F narrative, signature, attachments |

Both defaulted per DocType, so the print view opens straight into them.

**Data** — Company `Mercury1`, Customer `Evapco Dry Cooling Inc.`, Item `MP-640CH`,
Project `PROJ-0006` (91 tasks = 10 groups + 81), SO `SAL-ORD-2026-00004` (draft, PO 536POR22825),
`Mercury 1105VS10 Progress Payments` (5 milestones named exactly as the schedule prints them),
Activity Cost `Execution` 65/95, Fiscal Years 2024-25 and 2025-26.

### The bugs found along the way — all pre-existing or engine-level

- **Sales Orders could not be saved at all on this branch.** `sales_order.json` in our *committed*
  tree had lost `is_subcontracted` while `sales_order.py` still reads it unsafely at lines 230,
  295 and 654 → `AttributeError` on every save, in the UI too, and on QA. Stage 1 of the Mercury
  flow *is* "create a Sales Order". Audited the whole controller: 7 fields are missing from the
  JSON, only that one is read unsafely. Restored that field alone, hidden and read-only.
- **`custom_format = 1` is what makes a Jinja print format render.** Without it frappe silently
  falls back to the standard field-by-field layout and reports no error (`printview.py:200`).
- **wkhtmltopdf drew no table borders** — every border width was sub-pixel (0.5/1.2/1.6px), which
  that engine renders as nothing at print DPI while Chrome rounds up. All widths now whole pixels.
- **wkhtmltopdf cannot render flexbox.** The report's navy band collapsed in the PDF while the
  preview looked correct. Rebuilt with `display: table` / `table-cell`.
- **Arial is not installed on this bench**, so wkhtmltopdf substitutes the wider DejaVu Sans.
  Three rounds of column-width "fixes" were measured against the wrong typeface. Re-measured the
  real strings in the substituted font; every column now clears by 2.5–7mm.
- **`doc.date` is a string in print context** — `.strftime()` cannot work. Built from the ISO
  string instead.
- **Text Editor fields come back wrapped in Quill markup** (`.ql-editor`), which carries the
  *editor's* font — so any field edited in the UI printed in a different typeface. Neutralised
  inside the print container, for all future edits.

**Standing lesson recorded:** the browser preview and the PDF use *different engines*, so
anything verified only in the preview is not verified.

### Demo data shaped for the walkthrough

Statuses re-cut so the job reads as **in flight, not finished**: 67 Completed · 1 Working
(System Wiring, 60%, ending next week) · 13 Open with future dates · **0 Overdue** · project
**81.3%**. Timesheets re-logged at 8h per working day — hours fell from 23,064 to 5,976 and cost
from 1.5M to 388,440, with every Actual date still matching plan. `Project Update` moved directly
under `Project` in the Mercury sidebar.

**Known placeholders, not derivable from the client documents:** the 20% payment split, the 65/95
labour rates, and the Sales Order rate (left at 0, document kept in draft).

Rollback-before-this: `1fef86302`

---

## Push history (newest first)

| # | Commit | Date | Pushed | Summary |
|---|--------|------|--------|---------|
| 46 | `c28b9ee95` | 2026-08-13 | `paul-update` | print formats: drop flexbox — wkhtmltopdf cannot render it |
| 45 | `81af8aa03` | 2026-08-13 | `paul-update` | progress report: edited narrative inherits the letter typography |
| 44 | `80a72065c` | 2026-08-13 | `paul-update` | Project Update: default print format |
| 43 | `7295e38da` | 2026-08-13 | `paul-update` | Project: default print format |
| 42 | `3537bf6f6` | 2026-08-13 | `paul-update` | Task: drop "(via Timesheet)" from the costing labels |
| 41 | `a60c1cfa9` | 2026-08-12 | `paul-update` | Mercury sidebar: Project Update under Project; revert the Projects sidebar change |
| 40 | `a16b19c74` | 2026-08-12 | `paul-update` | Projects sidebar attempt + progress report polish — *sidebar part reverted by 41* |
| 39 | `a040708c2` | 2026-08-12 | `paul-update` | schedule: size columns to the font the PDF actually uses |
| 38 | `7210933c3` | 2026-08-12 | `paul-update` | print formats: integer border widths so wkhtmltopdf draws the table |
| 37 | `1fb513783` | 2026-08-12 | `paul-update` | schedule: date padding and logo/title alignment |
| 36 | `a6c836bef` | 2026-08-12 | `paul-update` | schedule: title no longer overlaps the table; wider S.No |
| 35 | `dbc3fa6fa` | 2026-08-12 | `paul-update` | print formats: logo placement; stop task text wrapping |
| 34 | `51db39821` | 2026-08-12 | `paul-update` | print formats: real Mercury logo, footer mark, fix the date crash |
| 33 | `d1ecf0b05` | 2026-08-12 | `paul-update` | **Alex/1105VS10: schedule + progress report regenerated from data** |
| 32 | `4ec20100c` | 2026-08-10 | `paul-update` | docs: Adam's scope answers, `sbiqc_provisioning` audit |
| 31 | `fdc852185` | 2026-08-10 | `paul-update` | tasks: fix the two known blockers from §17.11 |
| 30 | `5b3d7e6ce` | 2026-08-10 | yes | docs: open the Adam stream, add a session-start prompt |
| 29 | `1d1854a3f` | 2026-08-06 | yes | sidebar user avatar: initial was white-on-white, made visible |
| 28 | `4a3ec8800` | 2026-08-06 | yes | remove the square outline around avatars |
| 27 | `323e1b85a` | 2026-08-06 | yes | list view: **actually** bold the headers and freeze them (27a was a no-op) |
| 27a | `daf844cb0` | 2026-08-06 | yes | list view: bold + freeze — *no-op, superseded by 27* |
| 26 | `5088c7186` | 2026-08-06 | yes | merge `staging-deployment` into `paul-update` (CI build/deploy split) — tag `pre-staging-merge-3` |
| 25 | `9883806eb` | 2026-08-06 | yes | docs: the two known blockers as a standing notice |
| 24 | `51887868a` | 2026-08-06 | yes | Task: exempt template tasks from the mandatory assignee |
| 23 | `b8d5110cc` | 2026-08-06 | yes | docs: log the Project/Task UI round in `workprogress_mercury.txt` §17 |
| 22 | `6bfd4f123` | 2026-08-06 | yes | revert the DMS drift fix (files **and** DB) at the user's request |
| 21 | `1d97ef045` | 2026-08-06 | yes | quality_dms: bump 9 stale `modified` stamps — *reverted by 22* |
| 20 | `36619b420` | 2026-08-06 | yes | quality_dms: DMS sidebar stamp bump — restores My Training Dashboard + Training Analytics |
| 19 | `d315b0199` | 2026-08-06 | yes | Task "Assign" tab between Dependencies and More Info, assignee mandatory |
| 18 | `56207b6f4` | 2026-08-06 | yes | Projects workspace: cut the top inset above "Project Overview" |
| 17 | `6c8ca9c78` | 2026-08-06 | yes | Projects workspace: 3% board inset |
| 16 | `6b423ec90` | 2026-08-06 | yes | Projects workspace: make the aurora wash actually apply; undo chart padding |
| 15 | `b09330592` | 2026-08-06 | yes | Projects workspace: "Light Aurora" glass card design |
| 14 | `94d6516fd` | 2026-08-06 | yes | quality_dms: number cards share the row instead of a hardcoded 12.5% |
| 13 | `bb7a58eca` | 2026-08-06 | yes | revert: keep the workspace crumb on list routes |
| 12b | `f260af6b1` | 2026-08-06 | yes | breadcrumbs: drop the duplicate crumb on list routes — *reverted by 13* |
| 12a | `af1e2d9a2` | 2026-08-06 | yes | breadcrumbs: each crumb goes somewhere distinct and stable |
| 12 | `7c748dc33` | 2026-08-06 | yes | task list: clean actual-date labels, fix the clipped % Progress header |
| 11 | `fa134009b` | 2026-08-05 | yes | merge: `staging-deployment` #2 — DMS training analytics, login CSS fixes, CRLF pinning |
| 10 | `96eda0dd3` | 2026-08-05 | yes | docs: log the Delivered task status, rewrite the handoff |
| 9 | `015e556ae` | 2026-08-05 | yes | proj module UI defects fixed + Task "Delivered" status, gated per company |
| 8 | `80be0a9a2` | 2026-08-05 | yes | docs: rewrite the Mercury handoff block for the next session |
| 7 | `03a8a49b5` | 2026-08-05 | yes | merge: `staging-deployment` (DMS versioning/metrics, SBIQC login redesign, prod deploy job) |
| 6 | `38932a7b4` | 2026-08-05 | yes | docs: protect the Project/desk UI fixes from being lost in a merge — tag `pre-staging-merge` |
| 5 | `01ea91644` | 2026-08-04 | yes | merge: `DMS` — sidebar relabel + Summary tab stat tile styling |
| 4 | `c23b650eb` | 2026-08-04 | yes | merge: DMS project-module UI updates (sidebar relabel + status-accented stat tiles) |
| 3 | `3c8dd4878` | 2026-08-04 | yes | mercury: rename QI template `Mercury Steel Casting QC.` → without trailing period |
| 2 | `a609a8cef` | 2026-08-04 | yes | mercury: per-component QR shipping labels + logo, export phase-1 fixtures |
| 1 | `03c7f0d68` | 2026-08-03 | yes | mercury thin app phase 1 — configurable 8 stages |
| 0 | `b5583b40d` | 2026-07-22 | yes | (baseline before our Mercury work) merge staging-deployment into the branch |

---

### `5cbb13884` … `7f7776ce1` — Project module + desk form-shell UI fixes (2026-08-04/05) · PUSHED
17 commits fixing UI defects on the Project Summary tab and the desk form shell:
collapsible Tasks/Defects accordions (Defects closed on every login), a single
scrollbar instead of three, a genuinely pinned page head, a pinned tab bar with no gap
above it, and the right form sidebar no longer clipped at the viewport edge.

**Documented separately in [`PROJECT_UI_CHANGES.md`](PROJECT_UI_CHANGES.md)** — that file
is the re-apply guide, because `project.js` is an **erpnext core file** that a future
pull/merge can clobber. It records the root cause of each defect (most trace to
`hrms/layout_global.css` and `quality_dms.css` overriding core layout with
`!important`), the verification checklist, and the exact cherry-pick commands.

Only `apps/erpnext/.../project/project.js` is at risk; the desk CSS lives in the mercury
app as additive overrides and no frappe/erpnext/hrms file is patched.
Rollback-before-this: `3db8740fd`

## Features by commit

### `daf844cb0` … `1d1854a3f` — list-view polish (2026-08-06) · PUSHED

Bold + frozen column headers, and two avatar defects. All in `mercury_desk.css`
(`?v=23`). Detail in `workprogress_mercury.txt` §17.12.

| Symptom | Root cause |
|---|---|
| Headers not bold after the first attempt | they were **already** 600 — `quality_dms.css:575` sets it at **(0,3,1)** and a bare `.list-row-head .list-row-col` is (0,2,0). They read light because they're 11px uppercase grey, not because of weight. Now 700 + `var(--text-color)` |
| Header didn't freeze after the first attempt | `list.scss:592-598` makes `.result-container` a scroll container (`overflow-x: auto`), so sticky resolved against it — and it only scrolls *horizontally*. **Third occurrence of the overflow/sticky trap.** Fixed by giving that container its own vertical scroll and pinning at `top: 0` inside it |
| Square outline around avatars | `quality_dms.css:924-927` rings them with `box-shadow`; a spread follows the element's own `border-radius`, and frappe rounds only the inner pieces — so it drew a square around a circle |
| Sidebar avatar initial invisible | `quality_dms.css:125-129` paints `.body-sidebar-bottom *` for a navy background, but the avatar sits on its own light circle → white on white. **An external `!important` outranks a non-important inline style**, which is why frappe's inline avatar colour lost |

Rollback-before-this: `5088c7186`

### First QA deploy of this work

PR **#16** merged as `f1e3606`, then a manual Deploy to Staging. Two QA-only symptoms,
**neither caused by our changes**:

1. **Assign To column blank on QA** — browser cache. The form showed the value and the
   ToDo existed; only the list was stale. The deploy clears the *server* cache, not the
   browser's doctype meta. `Ctrl+Shift+R` fixed it.
2. **No quick-entry popup on QA** — QA-side setting. `quick_entry.js:79-86` builds the
   dialog from `reqd || allow_in_quick_entry`; our field is `reqd=0 / allow=0`, so it is
   invisible to that logic (verified locally: `Task.quick_entry = 1`, dialog fields are
   exactly subject/project/is_template). `is_quick_entry()` only bails on
   `quick_entry != 1`, a mandatory child table, or no eligible fields — so QA's Task has
   **`quick_entry = 0`**. Fix there: Customize Form → Task → tick *Allow Quick Entry*.

**⚠️ OPEN — QA / production backfill.** `custom_assign_to` is mandatory on real Tasks, but
only this bench's 9 Tasks were backfilled. Every other environment still holds Tasks with
no assignee, which will **refuse to save on first edit**. Offered but not built: an
`after_migrate` hook in mercury so any environment self-heals on deploy. Decide before
anyone edits an old Task on QA or production.

### `7c748dc33` … `51887868a` — Project/Task module UI round (2026-08-06) · PUSHED

Boss-requested changes ahead of the Project-module demo. All config or files under
`apps/` — **no frappe/erpnext core file is patched**. Full detail with root causes in
`workprogress_mercury.txt` §17.

| Change | Root cause worth remembering |
|---|---|
| "(via Timesheet)" off the actual-date labels | list-header-only is impossible — `list_view.js:782` renders the header *from* `df.label`. Changed doctype-wide via Property Setter; meaning moved to a field description |
| `% PROGRESS` header clipped | class-name **collision**, not layout: `list_view.js:774` stamps the fieldname as a CSS class and Task's field is named `progress`, matching Bootstrap's progress-bar (`line-height:0`, 10px, clipped) |
| Breadcrumbs | home icon pointed at `/desk` → `localStorage.current_page`, i.e. *the last workspace that browser visited* — unstable across machines. Now the module workspace; "Projects" → Project list |
| KPI cards filled half the row | **our own** `quality_dms.css` forced `flex: 0 0 12.5%` — right for DMS's 8 cards, wrong for Projects' 4. Fixed at source with `flex: 1 1 0` (N cards → 100/N) |
| "Light Aurora" card design | first attempt silently did nothing: `quality_dms.css:399` `background: transparent` is **(0,3,1)** and out-ranks a (0,2,1) selector *regardless of load order* — and the `background` shorthand resets `background-image` |
| Task **Assign** tab + mandatory assignee | the "Add to ToDo" popup can't be moved — it writes a **ToDo**, not Task fields — and can't be made mandatory (needs a saved doc ⇒ deadlock). Rebuilt as Custom Fields + `task_assign.py` mirroring to a real assignment |
| Template tasks exempt from the assignee | **`mandatory_depends_on` is JS-only.** No python implementation exists in frappe, so it is bypassed by REST / Data Import / `db.set_value`. Proven by probe. Needs the server hook alongside it |
| DMS training pages "missing" | they were never missing — the *sidebar links* were. `import_file` **skips** a standard record whose JSON `modified` stamp isn't newer than the DB row, and migrate still reports success |

**Reverted within the round (deliberate, both kept in history):** `f260af6b1` → `bb7a58eca`
(hiding the duplicate crumb on list routes) and `1d97ef045` → `6bfd4f123` (the wider DMS
drift fix — reverted in **both** the files and the database, since the migrate had already
written to it).

**Still unapplied and real:** the DMS drift sweep found **nine** standard records whose JSON
has never reached any database — the DMS workspace's 4th KPI card, 7 number-card labels, and
the `Documents by Status` chart palette. Findings are recorded in `1d97ef045`'s message.
Raise with James rather than re-applying unasked.

Rollback-before-this: `2f2e3d065`

### `fa134009b` — second `staging-deployment` merge (2026-08-05) · PUSHED
5 commits, merge base `cb1875648`, **clean — no conflicts**: DMS training score
history + self-service dashboards + analytics, two login CSS fixes, and CRLF pinning
for shell scripts.

Scoped before merging. **None of the protected files are touched by the incoming
side** — `project.js`, all of `apps/mercury/`, `CLAUDE.md`, `documents/` and
`workprogress_mercury.txt` are byte-identical to `pre-staging-merge-2`.

Two things that looked risky and were checked rather than assumed:

- `quality_dms/hooks.py` **is** in the diff, and it owns `app_include_css` — but the
  change is only a `?v=` bump 26→31 plus two permission-hook entries for the new
  doctype. `mercury_desk.css` still loads **last** (slot 7), so its `!important`
  overrides still win.
- `quality_dms.css` is **not** in the diff. The `body.dms-theme .page-head
  { position: relative }` rule at :862 that we override is untouched.

Post-merge verified: 20/20 protected UI markers pass, `bench migrate` clean (new
DocType `DMS Training Score History`, Pages `my-training-dashboard` and
`training-analytics` all created), Task options still include `Delivered`, Mercury
still ticked, PROJ-0001 still 78.57%, `MAT-DN-2026-00003` still draft.

Rollback-before-this: `96eda0dd3` (tag `pre-staging-merge-2`)

### `015e556ae` — Task "Delivered" status, gated per company (2026-08-05) · PUSHED
- **Why:** management asked for a `Delivered` status on Task, but only for the Mercury
  work — not for the DMS/SBIQC projects that share this Task doctype.
- **The constraint:** Frappe `Select` options are **DocType metadata**, so an option
  cannot be offered to only some records. There is no per-record variant in v16. The
  option is therefore added DocType-wide and scoped by two separate mechanisms:

  | Layer | Record / file | What it does |
  |---|---|---|
  | Option | Property Setter `Task-status-options` | appends `Delivered` between `Completed` and `Cancelled` |
  | Gate (config) | Custom Field `Company.allow_delivered_task_status` | the opt-in checkbox — ticked on **Mercury** only |
  | Scope (UI) | Client Script `Mercury - Delivered Task Status` | removes the option from the dropdown when the company hasn't opted in |
  | Scope (real) | `mercury/task_status.py` via `doc_events` | **rejects the write** — this is the actual control |

- **The Client Script is cosmetic; the `validate` hook is the enforcement.** A REST call,
  a Data Import or `frappe.db.set_value` never runs client JS. Both are required — the
  script alone is not a permission boundary. A warning to that effect is in the script
  header so nobody deletes the hook as redundant.
- **Gated on a checkbox, not a company name.** `Company` is a Link field, so its value is
  always the exact record name and `company == "Mercury"` would work today — but it would
  also match a future *"Mercury Freight Ltd"*, and enabling a second company would mean a
  code change instead of a click. Case-insensitive matching was considered and rejected
  for the same reason: link values cannot vary in case.
- **Known trade-off:** the checkbox **value** lives on the Company record, which is master
  data and *not* a fixture. On a fresh machine the field imports **unticked**, so
  `Delivered` stays hidden on Mercury tasks until someone ticks it. Either document the
  step or add an `after_migrate` hook — not yet decided.
- **Latent issue, not currently reachable:** `set_tasks_as_overdue`
  (`erpnext/hooks.py`, `daily_maintenance`) flips any task **not** in
  `("Cancelled", "Completed")` with a past `exp_end_date` to `Overdue` — which would
  silently un-deliver a Delivered task. Every PROJ-0001 task has `exp_end_date = None`,
  so it cannot fire today. **If end dates are ever added, this must be handled** (override
  `update_status` from the mercury app; do not patch erpnext core).
- Also cosmetic: `task_list.js` has a hardcoded status→colour map with no `Delivered`
  key, so the list-view indicator renders without a colour.
- Fixtures exported (`.claude/rules.md`): `custom_field.json`, `property_setter.json`,
  `client_script.json`, all filtered by `module = Mercury`.
- **Verified:** `Delivered` saves on a Mercury task; blocked with a validation error on a
  *Hephzibah Technologies India* task. Both tests rolled back — PROJ-0001 untouched at
  78.57%.
- Rollback-before-this: `80be0a9a2`

### `<pending>` — collapsible Tasks/Defects sections on the Project Summary tab (2026-08-04) · PUSHED in `015e556ae` and earlier
- **Why:** the Mercury demo shouldn't show a "Defects" panel (DMS/SBIQC terminology,
  always 0 for a manufacturing project). Rather than hard-hide it, both sections on the
  Project Summary tab are now **accordions**, so it can be folded away for the demo and
  unfolded again after.
- Header (chevron + icon + title + **count badge** + View All) is clickable; panel uses
  the `grid-template-rows: 0fr → 1fr` trick so it animates to natural height without a
  hardcoded max-height. Keyboard accessible (`role=button`, `tabindex=0`,
  `aria-expanded`, `aria-controls`, Enter/Space), and honours
  `prefers-reduced-motion`.
- **Default is EXPANDED** and the collapsed state is stored per section in
  `localStorage` (`project_summary_collapsed::<title>`). Deliberate: this file is shared
  with the DMS/SBIQC project module, so nobody else's view changes until they collapse it
  themselves — and Paul collapses Defects once and it stays collapsed for the demo.
- Styled with frappe theme variables (`--fg-hover-color`, `--control-bg`, `--text-muted`,
  `--primary`) rather than fixed hex, so it is correct in dark mode.
- `View All` sits inside the clickable header, so its click is `stopPropagation`'d —
  otherwise opening the list would also toggle the section.
- File: `apps/erpnext/erpnext/projects/doctype/project/project.js`
  (`show_task_defect_summary_tab`). Doctype client script — no `bench build` needed,
  just `bench clear-cache` + hard reload.
Rollback-before-this: `3db8740fd`

### `<pending>` — Outgoing QIs for the whole kit + Stage 6 guide rewrite (2026-08-04) · PUSHED
- **Unblocked `MAT-DN-2026-00003` for submission.** All 4 kit items carry *Inspection
  Required before Delivery*, and erpnext (`stock_controller.py:1463`) requires a
  **submitted QI on every row** (`Delivery Note Item.quality_inspection`), not one per
  shipment. Created + submitted 4 Outgoing QIs against the DN:
  `MAT-QA-2026-00003` pump (sample 1), `-00004` BFV-8 (2), `-00005` LG-01 (1),
  `-00006` EJ-8 (3) — all Accepted, each linked on its row.
  Verified by running `submit()` inside a transaction and rolling back:
  **submits cleanly, DN left in draft on purpose** (Packing Slips need a draft DN).
- **New QC template "Mercury Accessory Final QC"** (Visual / Surface Finish, Dimensional /
  Flange Fit, Marking / Tag Present) — the pump's leak/performance/paint checks don't
  apply to a valve or gauge. One shared template rather than three per-item ones.
- **Closed a reproducibility gap:** template rows link to **Quality Inspection Parameter**
  records that were in no fixture, so a fresh `bench migrate` would have failed the
  template import with `LinkValidationError`. Added a `Quality Inspection Parameter`
  fixture (9 records), listed **before** the template entry since fixtures import in
  hooks order.
- **Stage 6 of `web docs/mercury_phase1_stepbystep_guide.txt` rewritten** for the
  per-unit-QR flow so it can be practised from scratch: revised 6a–6e, new 6f
  (Packing Slip → submit), a "what changed from v1" section, and the new gotchas
  (td-img width override, serial naming-series conflict, QI Parameter links,
  exact-match non-numeric readings, wkhtmltopdf/PATH). Guide 643 → 776 lines.
Rollback-before-this: `733f94aba`

### `c23b650eb` — merge DMS project-module UI updates (2026-08-04) · PUSHED
- Merged `hephzibah/DMS` into `paul-update` with `--no-ff` (explicit, revertable merge point).
- Only **2 commits** were actually new — DMS's heavy project rework was already in our
  branch (merge base `65e41eb82`, which includes `90f263546` "rebuild overview home page,
  rename Issue to Defect, brand as SBIQC"):
  - `00f1bcd84` style(project): Summary tab stat cards → status-accented tiles
  - `85d9baa17` rename(dms): relabel sidebar sections/links
- Files touched: `apps/erpnext/erpnext/projects/doctype/project/project.js`,
  `apps/quality_dms/quality_dms/workspace_sidebar/dms.json`. **Zero conflicts.**
- Verified `git diff pre-dms-merge HEAD -- apps/mercury workprogress_mercury.txt .gitignore`
  was **empty** — no Mercury work altered.
- ⚠ **Watch:** `project.js` is the Project doctype client script that Mercury Stage 4 and
  the Stage 8 Monthly Progress Report rely on. Changes are cosmetic but SBIQC/DMS-branded
  ("Defect" instead of "Issue") and will show on `PROJ-0001` in the Mercury demo.
Rollback-before-this: `3c8dd4878` (= tag `pre-dms-merge`)

### `3c8dd4878` — rename QI template, drop trailing period (2026-08-04)
- `Mercury Steel Casting QC.` → `Mercury Steel Casting QC` via `frappe.rename_doc`, so the
  submitted Quality Inspection `MAT-QA-2026-00001` was relinked automatically (verified: 0
  stale references).
- Re-exported `fixtures/quality_inspection_template.json`.
Rollback-before-this: `a609a8cef`

### `a609a8cef` — per-component QR labels + Mercury logo + fixtures (2026-08-04)
**Management feedback #1:** one QR for the whole bundle meant the customer could not
confirm each loose component. Every physical unit now gets its own label and QR.

- **Kit changed:** dropped `BOLT-M16` / `NUT-M16` from the shipment (Item records still
  exist, just not in the kit); added 3 serial-tracked accessories so every unit has a
  unique identity — `BFV-8` 8" Butterfly Valve ×2, `LG-01` Level Gauge ×1,
  `EJ-8` 8" Expansion Joint ×3, plus `MERCURY-001` pump ×1 = **7 units**.
- **Print Format "Mercury Shipping Label" rewritten:** page 1 = shipment manifest
  (`Label 1/7…7/7`, serial, "Unit 2 of 3"); then **one full label page per unit** with the
  serial in large mono, `LABEL n OF 7`, and its **own QR**.
- **QR payload now per-unit and Phase-2 ready:**
  `{site}/shipment-ack?dn=<DN>&item=<code>&sr=<serial>` (was `doc.name`, i.e. identical on
  every label). Verified all 7 payloads distinct.
- **Logo** added to all 8 headers, stored as a **file** in the app
  (`apps/mercury/mercury/public/images/mercury_logo.png` + `.svg`), served via the existing
  `sites/assets/mercury` symlink. Size is one jinja var: `logo_w = 106`.
- **Fixtures exported** (per `.claude/rules.md`) — enabled the 3 commented hooks and ran
  `bench --site mysite.local export-fixtures --app mercury`: both print formats, the
  30/40/30 Payment Terms Template, and both QI Templates now live in git instead of only
  in the local DB. This cleared export debt carried since 2026-07-29.
- `.gitignore`: added `.env` (machine-local honcho PATH injection for wkhtmltopdf).
Rollback-before-this: `03c7f0d68`

### `03c7f0d68` — Mercury thin app, Phase 1, 8 configurable stages (2026-08-03)
- Thin `mercury` app as a config container (fixtures in git; JSON = source of truth).
- "Mercury" Workspace + Workspace Sidebar + Desktop Icon navigation.
- Stage 2 workflow "Mercury RTM Approval" on Sales Order + its states/actions, exported.
- Stages 1–8 built config-only; the only custom code is the ~3-line QR jinja helper
  (`mercury.utils.qr_base64`) registered via `hooks.jinja`.
Rollback-before-this: `b5583b40d`

---

## Gotchas worth not re-learning

- **Print format images:** frappe injects a legacy hack
  `body:last-child .print-format td img { width:100% !important }`. An image inside a `<td>`
  therefore ignores any inline width, making the **desk preview and the PDF disagree**.
  Fix: wrap the `<img>` in a fixed-width `<div>` and give the img `width:100%`.
- **Logo sizing:** never hardcode both width and height (stretches the image). Set width
  only, `height:auto`. Also crop transparent padding first — a logo that is mostly padding
  gets "sized by its padding".
- **Serial naming series:** if `tabSeries` has no counter row for a prefix but serials
  already exist, auto-generation throws "naming series conflict". Supply serials explicitly
  (`use_serial_batch_fields=1` + `serial_no`) and sync `tabSeries`.
- **Packing Slip** can only be attached to a **draft** Delivery Note.
- **wkhtmltopdf:** must be **0.12.x with patched qt**. Frappe calls it by bare name with no
  site_config override, so it must be on the PATH of the bench processes. Installed
  without root at `~/opt/wkhtmltox`; PATH injected via `~/frappe-bench/.env` (honcho reads
  it on `bench start`). **`bench restart` does not pick this up — fully restart
  `bench start`.** Both are machine-local and NOT in git.

---

## How to roll back

This repo is a real clone, so rollbacks happen here directly.

Undo the DMS merge but keep everything else (safest — history preserved):

```
git revert -m 1 c23b650eb
```

Move the branch back to the last known-good commit (local only, nothing pushed yet):

```
git reset --hard pre-dms-merge      # = 3c8dd4878
```

If a bad commit was already pushed, prefer a revert over a force-push, since this branch
is shared:

```
git revert <bad-commit-id>
git push hephzibah paul-update
```

Force-push only if you are certain nobody else has the branch:

```
git push --force-with-lease hephzibah paul-update
```

> After any rollback that changes DocType/config JSON, run
> `bench --site mysite.local migrate` so the database matches the fixtures again.

---

## Log new entries here as we push

<!--
Template:
### <commit-id> — <short title> (<date>)
- what changed / features
Rollback-before-this: <previous commit-id>
-->
