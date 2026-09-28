# opinionated-api: infrastructure

## Contents

1. PostgreSQL and PgBouncer
2. Redis
3. Celery
4. Application server
5. Image
6. Compose topology
7. Storage and media
8. Observability values
9. Local stack

---

## 1. PostgreSQL and PgBouncer

- PostgreSQL **17**, UTF8, storing `timestamptz`. There are no extensions by
  default; an operator script installs any extension, never a migration.
- Roles:
  - bootstrap superuser: init scripts only;
  - **migration** role: owns the schema and runs DDL, used by the `migrate` service;
  - **runtime** role: data changes only, used by web, workers, and beat.
- Runtime timeouts are set with `ALTER ROLE`, because PgBouncer rejects startup
  options:
  - `statement_timeout 30s`;
  - `lock_timeout 5s`;
  - `idle_in_transaction_session_timeout 60s`.

  The migration role uses `lock_timeout 5s` and `idle_in_transaction_session_timeout 300s`.
- PgBouncer 1.25.2 settings:
  - `POOL_MODE=transaction`, `AUTH_TYPE=scram-sha-256`;
  - `MAX_CLIENT_CONN=100`, `DEFAULT_POOL_SIZE=20`.

  Migrations bypass PgBouncer.

```python
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": env_str("POSTGRES_DB"), "USER": env_str("POSTGRES_RUNTIME_USER"),
    "PASSWORD": env_str("POSTGRES_RUNTIME_PASSWORD"),
    "HOST": env_str("POSTGRES_HOST", "pgbouncer"), "PORT": env_int("POSTGRES_PORT", 5432),
    "CONN_MAX_AGE": 0, "DISABLE_SERVER_SIDE_CURSORS": True, "ATOMIC_REQUESTS": False,
    "OPTIONS": {"sslmode": env_str("DATABASE_SSLMODE", "disable"), "prepare_threshold": None},
}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- `DATABASE_SSLMODE=disable` is allowed only on the private Docker network;
  otherwise use `require`, `verify-ca`, or `verify-full`.
- Backups of deployed environments: a daily `pg_dump -Fc`, kept 14 days off the
  host, with a monthly restore test.

## 2. Redis

| Service | DBs | Contents | Memory | Eviction | Persistence |
|---|---|---|---|---|---|
| `redis` (general) | 0: Celery broker · 1: default cache | broker, evictable caches | `maxmemory 1gb`, container 1280m | `volatile-lru` | AOF, `everysec` |
| `redis-critical` | 0 | JWT allowlist, OTP state, throttles, locks | `maxmemory 256mb`, container 384m | `noeviction` | AOF, `everysec` |

- Production refuses to start if both share a `host:port`. It uses `rediss://`
  (TLS), an ACL user and password per instance, and CA verification. Local uses a
  password without TLS.
- Cache aliases: `default` (general DB 1) and `critical` (critical DB 0).
  `KEY_PREFIX = "<project>"`.
- Pools:
  - `REDIS_DIRECT_MAX_CONNECTIONS=50` per process;
  - wait timeout 1s, connect and socket timeouts 2s;
  - health check every 30s.
- Env vars: `REDIS_SCHEME/HOST/PORT/USERNAME/PASSWORD/CA_CERT_PATH`, and the same
  set prefixed `CRITICAL_`.

## 3. Celery

| Setting | Value |
|---|---|
| Serializer / accept content | `json` / `["json"]` |
| `CELERY_TASK_ACKS_LATE`, `CELERY_TASK_REJECT_ON_WORKER_LOST` | `True` |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | 1 |
| `CELERY_TASK_IGNORE_RESULT` | `True` |
| Soft / hard time limit | 300 / 360 s |
| Broker `visibility_timeout` | 600 s |
| `CELERY_TIMEZONE` | the project `TIME_ZONE` |
| `DURABLE_JOB_MAX_ATTEMPTS` | 10 |
| `DURABLE_JOB_BACKOFF_SECONDS` / `_MAX_SECONDS` | 30 / 3600 |
| `DURABLE_JOB_LEASE_SECONDS` | 300 |
| `DURABLE_JOB_SWEEP_BATCH_SIZE` | 100 |
| `EVENTS_RETENTION_DAYS` | 30 |

**Queues** (set `CELERY_QUEUES` in `config/architecture.py` to exactly these):

| Queue | Worker service | Concurrency | Owns |
|---|---|---|---|
| `default` | `celery` | 1 | Sweepers, housekeeping, purges |
| `events` | `events-worker` | 2 | ASYNC event deliveries |
| `notifications` | `notification-worker` | 2 | Notification and webhook deliveries |
| `otp` | `otp-worker` | 2 | One-time-code SMS only |
| `files` | `files-worker` | 2 | File inspection and processing |

- Every worker runs with
  `-l INFO --prefetch-multiplier=1 --max-tasks-per-child=100 --max-memory-per-child=524288`.
- Exactly one `celery-beat` service. The delivery sweeper
  (`events.dispatch_due_deliveries`) runs every 60 s, and purges run daily at 03:30
  local time.

## 4. Application server

```text
gunicorn config.asgi:application --config deploy/gunicorn_conf.py --bind 0.0.0.0:8000
  --workers 3 --worker-class uvicorn.workers.UvicornWorker --no-control-socket
  --timeout 60 --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -
```

- `deploy/gunicorn_conf.py` releases dead workers' Prometheus multiprocess files.
- The app sits behind a TLS proxy: `TRUSTED_PROXY_COUNT=1` and
  `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.
- Static files are served by whitenoise and collected at image build.

## 5. Image

- Stages: `application` → `ci` (adds dev requirements) → `runtime` (pip removed).
- User `app`, uid/gid 10001, shell `nologin`.
- `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`.
- `pip install --require-hashes` from `requirements-bootstrap.txt`, then `pylock.toml`.
- The only OS package is `postgresql-client`.

## 6. Compose topology

| Service | Profile | Notes |
|---|---|---|
| `web` | default | `127.0.0.1:8000:8000`; healthcheck `/health/live` |
| `migrate` | `operations` | one-shot; `config.settings.migration`; direct to `db` |
| `celery`, `events-worker`, `notification-worker`, `otp-worker`, `files-worker` | `workers` | §3 |
| `celery-beat` | `scheduler` | exactly one |
| `db`, `pgbouncer` | `self-hosted-db` | mem 2g / 256m |
| `redis`, `redis-critical` | default | §2 |
| `prometheus`, `grafana` | `monitoring` | |

Every service has:
- `restart: unless-stopped`;
- `security_opt: ["no-new-privileges:true"]`;
- `mem_limit`, `cpus`, and `pids_limit`;
- a healthcheck.

Published ports bind to `127.0.0.1`, and secrets come from a git-ignored `./secrets/`.

## 7. Storage and media

- `FileSystemStorage` on the volume `<project>_media`, mounted at `/app/media` in web
  and workers.
- `FILES_DELIVERY_MODE = "proxy"`: files are served only through
  `GET /api/v1/files/{id}/content?token=...`. `MEDIA_URL` is not routed in production.
- `FILES_CLIENT_URL_TTL_SECONDS = 86400`, `FILES_PARTNER_URL_TTL_SECONDS = 900`.
- Media is backed up, and never deleted without the owner's instruction.

## 8. Observability values

- **Log fields**: `timestamp`, `level`, `logger`, `message`, `request_id`, `job_id`,
  `process`, plus the extras.
- **Levels**: production `INFO`, local `DEBUG` for first-party code, `WARNING` for
  noisy libraries.
- **Sentry**, only when `SENTRY_DSN` is set: `send_default_pii=False`,
  `release=<git sha>`, `traces_sample_rate` from settings (default 0.0), and no
  request bodies.
- **Metrics**: `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus`. Web serves `/metrics`
  with a Bearer scrape token; workers serve `WORKER_METRICS_PORT=9100` internally.
- Alert rules live in `monitoring/rules/<project>-alerts.yml`.

## 9. Local stack

- API at `http://localhost:8000`. Inside containers, use service names (`db`,
  `pgbouncer`, `redis`, `redis-critical`).
- `docker-compose.dev.yml` with bind-mounted code and `config.settings.local`.
- Volumes `<project>_postgres17_data`, `<project>_redis_data`,
  `<project>_critical_redis_data`, and `<project>_media` are kept by default.
- Backups go to `./backups/`, git-ignored and outside every volume.
- After changing code that workers import, restart the affected workers.
