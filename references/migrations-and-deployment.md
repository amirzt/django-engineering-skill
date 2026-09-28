# Migrations and deployment

How schema changes are written, checked, and applied safely, and the principles
of deploying and rolling back. Step-by-step release, backup, and rollback
procedures are in `operations.md`. Topology and image details are in the profile.

## Contents

1. Writing migrations
2. The migration safety check
3. Expand, backfill, switch, contract
4. Contracts during rolling deploys
5. Deployment principles
6. Recipe: ship a schema change safely

---

## 1. Writing migrations

- Read **every generated migration line by line** before accepting it.
- Test it against a **populated** database; an empty one makes destructive
  operations look free.
- **Before applying a migration that alters existing tables** to any database whose
  data matters (including a local database you want to keep):
  - take a `pg_dump -Fc` backup to a location outside the database volume;
  - record where it is.
- Data migrations use historical models (`apps.get_model`) and bounded batches,
  never unbounded row-by-row loops.
- Indexes on large existing tables use `AddIndexConcurrently` in a migration with
  `atomic = False`. Before retrying a failed concurrent build, drop the invalid
  leftover index.
- PostgreSQL-only SQL uses `PostgresOnlySQL` (`testing.md` §4).
- Never drop a populated table or column, or delete rows, without an explicit,
  recorded owner decision.

## 2. The migration safety check

`deploy/check_migration_safety.py` (from `assets/project/`) reads every migration of
the project apps:
- **Expand operations pass**: `CreateModel`, `AddIndex`/`AddIndexConcurrently`,
  `AddConstraint`, `AddField` that is nullable or has a default, and model-option
  changes.
- **Every other operation fails** unless the migration module declares
  `CONTRACT_APPROVED = "<ADR number or reason>"`. That covers `RemoveField`,
  `DeleteModel`, `AlterField`, renames, `RunSQL`, and `RunPython`.

An `AlterField` that only changes `help_text` still needs a marker
(`CONTRACT_APPROVED = "metadata only"`). The marker records that a human looked.

## 3. Expand, backfill, switch, contract

Once real data exists, a schema change that is not purely additive ships across
separate deploys:
1. **Expand**: add the new shape (a nullable column, a new table).
2. **Backfill**: fill it in bounded, resumable batches (`operations.md` §5).
3. **Switch**: move readers and writers to the new shape.
4. **Contract**: remove the old shape in a later deploy, once no running version
   reads it.

A rename is add + backfill + remove, never a `RenameField` on a live table.

Before the first real user, the project policy may allow direct changes. It must
say so explicitly, and the backup rule still applies.

## 4. Contracts during rolling deploys

While two versions run at once, these are wire contracts. Change them only with
expand/contract:
- Celery task names and arguments;
- domain event names and payload versions;
- handler keys stored on pending deliveries;
- cache value shapes: bump the key version;
- settings keys: add new keys with defaults, and retire old ones after a deploy
  that no longer reads them.

## 5. Deployment principles

- One immutable image per commit, used by every service. Web and workers run the
  same version.
- Migrations run in a separate one-shot service, using the migration database role
  and connecting directly to PostgreSQL.
- Rollback means the application **and** schema **and** workers **and** queues
  **and** payload compatibility. Prefer forward repair once side effects have happened.
- Destructive operations on an environment holding real data need the owner's
  explicit instruction (`workflow.md` §3).

## 6. Recipe: ship a schema change safely

1. Write the model change (`models.md` §18), and read the generated migration.
2. Run `deploy/check_migration_safety.py`.
   - If it fails, decide with the owner: split into expand/contract, or approve with
     a marker and an ADR.
3. Test against populated data, then take a backup (with the owner's approval)
   before applying.
4. For a backfill, write a resumable command (`operations.md` §5).
5. Release in order (`operations.md` §1), and remove the old shape in a later deploy.
