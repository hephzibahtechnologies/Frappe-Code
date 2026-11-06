# Staging release runbook (qa.sbiqc.com, 72.167.140.185)

Build -> deploy -> (if needed) rollback. All manual, all from the Actions tab.

| Step | Workflow | What it does |
|---|---|---|
| 1. Build | **Build & Push Images** (runs on push to `staging-deployment`) | Builds the image, tags it with the commit SHA (first 12 chars) and `latest-staging`. Never deploys. |
| 2. Deploy | **Deploy to Staging** (Run workflow) | Default deploys the newest successfully built commit; or give a SHA. Checks free disk, takes a verified backup, pulls that exact SHA image, recreates, migrates, runs smoke checks, records the deployment. |
| 3. Roll back | **Rollback Staging** (Run workflow) | `target=previous` (or a SHA) and type `ROLLBACK`. Backs up the current state first, then redeploys the earlier version the same way. Code only: the database is NOT restored. |

## Where to look
- **Which version is running / history:** repo -> **Deployments** -> staging (SHA, who, when, result, run link).
- **Backups:** `/home/htipladmin/backups/crm/<UTC>_to-<tag>/` on the server (newest 7 kept), each with a `MANIFEST.txt`
  (previous and deployed image, run id, who). About 87 MB each. Owner-only permissions.
- **Run log:** Actions -> the run -> job -> step log. A safety failure prints `ABORT:` and nothing on the server has changed.

## Notes
- Only one staging deploy/rollback runs at a time (others queue).
- `skip_backup` on Deploy is for emergencies only.
- Backups are on the staging server only (no off-server copy yet).
- Restoring a database backup is a manual, deliberate step (not automated yet).
