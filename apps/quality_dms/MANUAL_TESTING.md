# Quality DMS — Training Module Manual Testing Guide

Site: `http://localhost:8000` · Workspace: **/desk/dms** · Test as: Administrator plus at least one non-admin Employee user (with the Employee role) and one manager user.

**Test data prerequisites:** 2–3 Employees in different Departments (one reporting to a manager), at least one published document in Document Library, one DMS Quiz with 2+ questions and a passing score set.

---

## 1. Core assignment & completion flow

1. Open a published **Document Library** document → create a **DMS Training Record** for an employee, due date a week out.
2. Log in as that employee → open **/desk/dms** → confirm the record appears in their list (permission check: they should see only their own records).
3. Open the record → read the document link (verify the attachment/route opens — broken-link check).
4. Complete the acknowledgement via the **Sign Acknowledgement** button.
   - Expected: prompted for password (e-signature), a **CFR Part 11 Signature Log** entry is created, record status → Completed, completion date stamped.
5. As Administrator, verify the **DMS Audit Log** captured the event.

## 2. Quiz gating

1. Attach a **DMS Quiz** to the document/training record.
2. As the employee, attempt to sign off **without** passing the quiz. Expected: blocked with a validation message.
3. Take the quiz and deliberately fail (score below passing). Expected: completion still blocked; attempt recorded.
4. Pass the quiz, then sign. Expected: completion allowed, quiz score stored on the record.

## 3. Auto-assignment rules

1. Create a **DMS Training Assignment Rule** targeting a Department + document category.
2. Create a new Employee in that department. Expected: training records auto-created (onboarding hook).
3. Change an existing employee's department to match the rule. Expected: new assignments appear.
4. Set the employee's status to Left. Expected: open training records are cancelled/closed (offboarding hook), no new assignments.

## 4. Curricula

1. Create a **DMS Curriculum** with 2–3 documents, assign to an employee/role.
2. Expected: one training record per curriculum document; curriculum shows completion progress as records complete.

## 5. Retraining / expiry cycle

1. On a completed training record's document, set a short validity/retraining period.
2. Run the scheduler manually:
   `bench --site erp.local execute quality_dms.dms.doctype.dms_training_record.dms_training_record.check_training_expiry`
3. Expected: expired training flagged and a new training record created for the employee.

## 6. Document-revision-driven retraining

1. Create a new **Document Revision** of a document that employees have completed training on, and publish it.
2. Expected: new training records are created against the new revision for previously-trained employees; old completions remain intact for audit.

## 7. Overdue handling & escalation

1. Set a training record's due date to yesterday (or create one already past due).
2. Run: `bench --site erp.local execute quality_dms.dms.doctype.dms_training_record.dms_training_record.mark_overdue_training_records`
   Expected: status → Overdue.
3. Run: `...dms_training_record.escalate_overdue_training`
   Expected: escalation email queued to the employee's manager (check **Email Queue**).
4. Run: `...dms_training_record.send_manager_training_digest`
   Expected: manager digest email queued summarizing their team's open/overdue training.

## 8. Instructor-led sessions

1. Create a **DMS Training Session** with a trainer, date, and 2+ attendees.
2. Mark attendance (present/absent) and complete the session.
   Expected: present attendees' training records complete; absent attendees' do not.

## 9. Dual sign-off (countersign)

1. Complete a training record that requires countersigning.
2. As the trainer/manager, use **Countersign** — expected: password-verified signature, second CFR Part 11 Signature Log entry, record only fully closed after countersign.
3. Negative test: a user without the countersign role should be blocked.

## 10. Effectiveness check & proxy completion

1. On a completed training, record an effectiveness check (pass/fail). Expected: fail triggers follow-up/retraining per configuration.
2. As a manager, complete a training **on behalf of** an employee (proxy/delegated completion). Expected: record completes but audit trail clearly shows who actually performed the action.

## 11. Certificates

1. Open a completed training record → print with the certificate **Print Format**.
   Expected: renders employee, document, date, signature details correctly; PDF auto-attached to the record.

## 12. Reports, dashboard & links (regression for the fixed bugs)

Open each from the DMS workspace — all should load without a traceback (these three previously crashed with "DocType None not found"):

- **Training Matrix Report** — grouped per employee × category with compliance %.
- **Training Compliance Report** — one row per employee-training assignment (Sr. No., Training ID, Training Title, Training Type, Department, Trainer, Date of completion, Attendance %, Assessment Y/N, Assessment Score, Status, Next Due Date, Remarks, Employee Signature); row count matches total employee assignments, not training record count.
- **Overdue Training Report** — shows the overdue record from step 7.
- **Training Gap Analysis** (Report Builder) and **Training Record Status Board** (Kanban — drag a card between status columns and confirm the status field updates or is properly blocked).
- Dashboard chart(s) and Number Cards on the workspace render with sensible counts.
- Click through every workspace shortcut/link once — no "Not Found" pages.

## 13. Permissions sweep

As a plain Employee user, verify you **cannot**: see other employees' training records, edit assignment rules, countersign, or access Training Settings. As DMS Manager, verify you **can** see your team's records and reports.

---

### Environment notes

- If bench commands fail with Redis errors, the WSL VM likely restarted: `cd ~/frappe-bench && nohup bench start > /tmp/bench_start.log 2>&1 & disown`
- After crash/retry cycles, clear stuck jobs: `bench purge-jobs`
- This is a persistent dev DB — clean up test employees/records afterwards, and watch for stray "Test One" Employee fixtures.
