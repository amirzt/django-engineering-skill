# Redis and caching

How Redis is used safely: instances split by failure semantics, bounded pools,
atomic operations, locks, failure behavior, key naming, and caching discipline.
The number of instances, memory limits, and pool values come from the profile.

## Contents

1. Split by failure semantics
2. Bounded, instrumented pools
3. Atomic operations
4. Locks
5. Failure behavior is a decision
6. Keys
7. Caching discipline
8. Recipe: add a Redis key or cache

---

## 1. Split by failure semantics

- **Evictable** state (broker messages, caches) and **non-evictable** state
  (session allowlist, one-time-code state, throttles, locks) have different
  failure costs. Keep them in separately configured Redis roles:
  - evictable: `volatile-lru` or `allkeys-lru` with `maxmemory`;
  - non-evictable: `noeviction`, with persistence.
- The profile decides whether the roles are separate instances or separate
  configurations. Production settings refuse a configuration that mixes them when
  the profile requires separation.
- Use separate cache aliases (for example `default` and `critical`), and reach
  critical state only through one module (`common/critical_cache.py`).
- Production connections use TLS, ACL users, and passwords.
- Never flush the non-evictable Redis. It holds sessions, and losing it logs
  everyone out (`operations.md` §7).

## 2. Bounded, instrumented pools

- Every client uses `redis.BlockingConnectionPool` with a maximum size and a wait
  timeout, plus `socket_connect_timeout` and `socket_timeout`.
- Pool exhaustion increments a metric and logs a warning.

## 3. Atomic operations

Multi-step operations run as a Lua script or `MULTI`. The sliding-window rate
limiter:

```lua
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  redis.call('PEXPIRE', key, window_ms)
  return {0, count, tonumber(oldest[2]) or now_ms}
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, count + 1, 0}
```

DRF throttles are backed by the non-evictable Redis with this script, so concurrent
requests cannot overshoot a limit.

## 4. Locks

- Locks carry an owner token and a TTL (redis-py's `client.lock(name, timeout=...,
  blocking_timeout=...)` does both).
- A Redis lock is an **efficiency** tool (stampede protection, avoiding duplicate
  work), never the correctness guarantee. Correctness comes from database
  constraints and guarded updates (`data-integrity.md`).

## 5. Failure behavior is a decision

For every use, decide and record one of these in `docs/features/redis.md`:
- **Fail closed** for security state (sessions, throttles, one-time codes): return
  503, never allow the request.
- **Fall back to the database** for caches: compute from PostgreSQL, log, and count
  the fallback.

## 6. Keys

- Format `<app>:<purpose>:v<N>:<id>`, for example `accounts:jwt-access:v1:<jti>`.
  Bump `vN` when a value's shape or serializer changes, so old and new code never
  misread each other.
- Every key has a TTL unless the Redis map documents it as permanent.
- Tenant-specific keys include the tenant ID.
- `docs/features/redis.md` lists every prefix: instance, owner, TTL, invalidation,
  and failure behavior. It also lists the state deliberately **not** cached.

## 7. Caching discipline

Add a cache only when all of these are defined:
- the key scope (including the tenant);
- freshness;
- invalidation;
- stampede behavior;
- failure fallback;
- measured evidence that the cache is needed.

Otherwise, do not cache.

## 8. Recipe: add a Redis key or cache

1. Choose the Redis role by failure semantics (§1).
2. Name the key with a version, and add the tenant ID if the data is tenant-specific (§6).
3. Define the TTL, invalidation, stampede behavior, and failure behavior (§5, §7).
4. Add a row to `docs/features/redis.md`:
   `| Prefix | Instance | Owner | TTL | Invalidation | On failure |`.
5. Tests: a hit, a miss, invalidation, and Redis-unavailable behavior.
