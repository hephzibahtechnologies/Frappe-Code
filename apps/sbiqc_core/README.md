# SBIQC Core

Small app that is installed on **every** SBIQC site (existing tenants and newly
provisioned ones). It holds behaviour that must be identical across all apps and
must not live in a vendor app (Frappe / ERPNext) or in an app that only some
sites have.

## Global date format `dd-MMM-yyyy` (05-Nov-2026)

Adds `dd-MMM-yyyy` as an **optional** choice in *System Settings > Date Format*
(and in *Language > Date Format*). The site default is not changed; nothing
changes until an administrator selects it.

| Piece | File | Why |
|---|---|---|
| The option | `fixtures/property_setter.json` | Appends the choice to the two Select fields. |
| Server parsing | `date_format.py` | Frappe's `dateformats` table has no entry for the spelling Frappe itself formats correctly. |
| Calendar picker | `public/js/global_date_format.js` | The desk's date picker spells the short month `M`, so the Date and Date Range controls get `dd-M-yyyy`. |

The spelling is deliberately **`dd-MMM-yyyy`** (capital MMM). Frappe's
`format_date()` rewrites `mm` to `MM`, so a lowercase `dd-mmm-yyyy` turns the third
`m` into *minutes* and raises an error.

Helpdesk (a separate Vue app) follows the site format in its default displays, but a few
surfaces (ticket tooltips, call day labels, article timestamps, ...) used their own fixed English
pattern. Those are handled in Helpdesk itself, not here: `apps/helpdesk/desk/src/dateDisplayFormat.ts`
switches them to `DD-MMM-YYYY` only when a site selects this format; every other format keeps the
shipped pattern. Machine formats (`YYYY-MM-DD` in API filters) are never touched.

Known limitation: month names are English (`Nov`), as in the rest of the ERP.

## Tests

```
bench --site <site> run-tests --app sbiqc_core
node --test apps/sbiqc_core/sbiqc_core/tests/js/test_global_date_format.js
```

## Rollout

* **New tenants**: `sbiqc_provisioning.provisioner.engine.ALWAYS_INSTALL_APPS` makes the
  provisioning engine install this app on every new site.
* **Existing tenants**: the `v1_1_install_sbiqc_core_on_existing_tenants` patch of
  `sbiqc_provisioning` queues `ensure_required_apps_on_existing_tenants`, which installs it on
  every Active tenant that lacks it (idempotent; `dry_run=True` only reports).
* **Main QA / production site** (outside the provisioning flow; CI migrates it but never installs
  apps): **installed once by the release team**, deliberately not automated:
  `bench --site <site> install-app sbiqc_core`, then `bench --site <site> migrate`. Until then
  nothing changes on that site. The same two commands apply to any other site that is not a tenant.
