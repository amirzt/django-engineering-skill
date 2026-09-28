# Operations

Step-by-step procedures. Each one is the source for a project runbook in
`docs/runbooks/` (template: `comments-and-docs.md` §4), with environment details
added. **Every step on a deployed environment requires the owner's instruction**
(`workflow.md` §3).

## Contents

1. Release and rollback
2. `SECRET_KEY` rotation
3. Database and Redis password rotation
4. Backup and restore drill
5. Data backfill
6. Dead-letter triage
7. Losing the non-evictable Redis
8. Reconciling ambiguous outcomes
9. Adding or upgrading a dependency
10. Incident response

---

## 1. Release and rollback

**Before**
1. CI is green on the exact commit, and its image exists.
2. Review the `check_migration_safety.py` output:
   - expand-only migrations ship directly;
   - contract operations need their approved ADR and must not be read by the
     running version.
3. Take a database backup (§4) and record where it is.

**Release**
1. Run migrations with the new image, in the one-shot migrate service.
2. Roll the web service and wait for `/health/ready`.
3. Roll every worker, then the beat scheduler last.
4. Verify readiness, error rate, queue depths, dead-letter counts, and one smoke
   request per critical endpoint.

**Rollback**
- If the migrations were expand-only, roll the application and workers back to the
  previous image.
- **Never reverse a migration that loses data.** Prefer a forward fix.
- If the new version wrote events, tasks, or cache entries the old one cannot read,
  roll forward instead (`migrations-and-deployment.md` §4).

## 2. `SECRET_KEY` rotation

**What depends on the key:**
- keyed hashes and signed URLs verify with `SECRET_KEY_FALLBACKS`;
- simplejwt signs with `SECRET_KEY` by default and has **no fallback**, so rotating
  it logs everyone out unless a separate JWT signing key is configured;
- encrypted fields: check how the installed library derives its keys, and
  re-encrypt before removing the old key.

**Phase 1**
1. Put the new key in `SECRET_KEY` and the old key first in `SECRET_KEY_FALLBACKS`.
2. Deploy every service.
3. Keyed hashes that verify with a fallback are re-hashed with the current key on use.
4. Re-encrypt encrypted fields, if any.
5. Announce the forced logout, if JWTs are signed with the key.

**Wait** at least the longest lifetime of anything signed with the old key.

**Phase 2**
1. Remove the old key from the fallbacks and deploy.
2. Verify logins, API keys, and file URLs issued after phase 1.

## 3. Database and Redis password rotation

- **Redis ACL** (a user may have several passwords):
  1. `ACL SETUSER <user> >new`;
  2. update the secret and restart the services;
  3. `ACL SETUSER <user> <old`;
  4. check `/health/ready`.
- **PostgreSQL** (one password per role):
  1. in a short window, run `ALTER ROLE ... PASSWORD`;
  2. update the secret and restart the pooler and all services together;
  3. check `/health/ready` and a write path.

## 4. Backup and restore drill

1. `pg_dump -Fc`, plus a copy of the media storage. Store both off the host.
2. Restore into a **separate** database or container, never over a live one.
3. Run `manage.py check`, a migrations check, and row-count and recent-row queries
   against the restore.
4. Record the date, source, duration, and result in the runbook log. A backup that
   was never restored is not a backup.

## 5. Data backfill

1. Write a management command that:
   - uses the owning service or historical-model logic;
   - processes **batches by primary key range**;
   - is idempotent and resumable (it starts after the last processed key).
2. Run `--dry-run` for counts, then run it on a restored copy first (§4).
3. With the owner's instruction, take a backup and run it on real data in batches,
   pausing between them. Watch database load and lock waits.
4. Verify with prepared queries (counts, sample rows), and record the evidence.
5. Write an audit event with the run summary.

## 6. Dead-letter triage

1. On the alert, list dead rows grouped by model and `last_error_code`.
2. Classify each group:

| Cause | Action |
|---|---|
| A bug in our code | Fix, test, release, then requeue |
| An external outage | After recovery, requeue |
| Bad data | Fix the data through the owning service, then requeue or cancel |
| Truly permanent | Leave it dead, and document why |

3. Run `requeue_dead_jobs ... --dry-run` first, then for real.
4. Verify the requeued jobs succeed and the dead count returns to baseline.

## 7. Losing the non-evictable Redis

**Symptoms:** 503 `dependency_unavailable` on authenticated requests, and throttle
or one-time-code failures.

1. Restore service from the persisted AOF. **Never flush.**
2. If the data is lost:
   - every session is invalid, so users must log in again;
   - throttle counters and lockouts are reset;
   - locks expire.
3. Announce the forced logout, and watch for abuse while the counters are reset.
4. Afterwards, check the persistence settings and the pinned Redis version notes in
   the profile.

## 8. Reconciling ambiguous outcomes

1. List rows in `reconciliation_required`, grouped by provider and operation.
2. For each, query the provider's status API **with our idempotency key or
   reference**. Never re-send the operation.
3. Settle through the owning service:
   - success → complete;
   - failure → fail and release any reservation;
   - still unknown → leave it and escalate.
4. Record each outcome in an audit event. Alert if rows stay in this state past a
   threshold.

## 9. Adding or upgrading a dependency

1. **Only with the owner's approval.** State the reason, the alternatives (including
   writing it ourselves), the license, the maintenance status, and the size.
2. Pin it exactly, regenerate the lock file, and run `pip-audit`.
3. Update the project policy's `## Pinned versions` table (and the profile if it is
   a profile default), and add an ADR for a significant technology choice.
4. Run `deploy/check_version_drift.py`, the full quality gate, both test tiers, the
   real flow, and an image rebuild.
5. Ship lock-file changes as their own pull request.

## 10. Incident response

1. **Detect**: the alert or report, and when it started.
2. **Stabilize** with the smallest safe action: scale a queue's workers to zero,
   stop the beat scheduler, or roll back an expand-only release (§1).
3. **Investigate** with the `request_id` in the logs, and with durable state (rows,
   outbox, deliveries, audit).
4. **Fix forward**: a test reproducing the cause (`workflow.md` §9), then a release.
5. **Repair data** with a backfill (§5) or reconciliation (§8). Correct evidence
   rows with compensating entries only.
6. **Write up** the timeline, cause, impact, fix, and follow-ups in
   `docs/runbooks/incidents/YYYY-MM-DD-<slug>.md`, and add or improve an alert.
