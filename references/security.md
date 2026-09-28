# Security, tenancy, and integrations

Authorization (principal, policy, scoping), sessions, data classification, secrets,
configuration safety, input hardening, audit, external integrations, inbound
webhooks, and supply chain. Concrete values (token lifetimes, throttle rates,
limits) come from the profile. The login flow itself is project-specific and is
recorded in `AGENTS.md`.

## Contents

1. The request principal
2. The policy registry
3. Scoping before lookup
4. Authorization tests
5. Sessions
6. One-time codes (if the login flow uses them)
7. Data classification
8. Secrets and keyed hashes
9. Configuration and request-path rules
10. Input hardening
11. Audit log
12. External integrations
13. Inbound webhooks
14. Supply chain
15. Recipes: permission action, integration, inbound webhook

---

## 1. The request principal

No view or service compares owner IDs directly. Everything starts from one principal:

```python
@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    user: Any                           # actor, audit identity
    organization_id: uuid.UUID          # the tenant boundary
    role: str                           # role in that organization
    project_id: uuid.UUID | None = None
    credential_id: uuid.UUID | None = None   # set when authenticated by API key
    credential_scopes: frozenset[str] = frozenset()
    is_service: bool = False            # background/system principal
```

- Resolved **once per request** and cached on the request.
- Selection order: a credential pin is absolute → an explicit selector header (only
  among the caller's own memberships) → the default. **A selector narrows scope,
  never widens it.** A header that conflicts with a pin is refused.
- `service_principal(...)` builds a principal for background work from the scope
  stored on the durable record, never from current memberships.
- A project without organizations keeps the same API, using the user's personal
  scope as the "organization". Adding organizations later is then additive.

## 2. The policy registry

```python
@dataclass(frozen=True, slots=True)
class ActionPolicy:
    scope: Literal["organization", "project", "principal"]
    minimum_role: str
    administrative: bool = False        # never allowed to API keys


ACTIONS: Final[dict[str, ActionPolicy]] = {
    "order.read":   ActionPolicy("organization", Role.VIEWER),
    "order.create": ActionPolicy("principal", Role.MEMBER),
    "order.cancel": ActionPolicy("organization", Role.ADMIN),
}


def require(principal: RequestPrincipal, *, action: str, resource: Any = None) -> None:
    policy = ACTIONS.get(action)
    if policy is None:
        raise PolicyConfigurationError(action)                               # fail closed
    if resource is not None and _organization_id(resource) != principal.organization_id:
        raise PolicyDenied(action, "scope", is_not_found=True)               # 404
    if principal.credential_id is not None and (
        policy.administrative or not credential_allows(principal.credential_scopes, action)
    ):
        raise PolicyDenied(action, "credential_scope", is_not_found=False)   # 403
    if ROLE_RANK[principal.role] < ROLE_RANK[policy.minimum_role]:
        raise PolicyDenied(action, "role", is_not_found=False)               # 403
```

- `PolicyDenied` is defined in `common/errors.py` so the exception handler can
  render it: a scope failure is 404, a role or credential failure is 403.
- An unknown action fails closed.
- Action names are `<resource>.<verb>` and double as audit action names.
- With per-project access, the **effective role = min(organization role, grant
  role)**: a grant widens *which* projects someone reaches, never *what* they may do.
- API key scopes: a write scope implies read, the empty list means the documented
  default, and administrative actions are always refused to keys.
- Staff access is separate:
  - staff roles and capabilities, with interactive authentication only;
  - no impersonation;
  - metadata is visible, customer content needs a capability;
  - secrets have no read path at all.

## 3. Scoping before lookup

```python
def scope_by_organization(queryset, principal, *, field: str = "organization_id"):
    return queryset.filter(**{field: principal.organization_id})
```

- **Every list and detail query is scoped before `.get()` or iteration.** Object
  permissions alone never secure a list.
- Each owning app exposes one sanctioned queryset builder per resource (for example
  `visible_assets(principal)`).
- Nested resources verify the parent-child relation.

## 4. Authorization tests

- A **cross-tenant matrix**: a foreign ID returns 404 on every endpoint, and lists
  never include foreign rows.
- A **role matrix**: each role × action gets the expected allow or 403.
- A test that every `require(..., action="...")` string exists in `ACTIONS`.

## 5. Sessions

The mechanism depends on the authentication chosen in the policy.

**JWT (the opinionated-api profile): allowlist in non-evicting Redis**
- A login issues an access + refresh pair. Each token's `jti` is allowlisted in the
  **critical** Redis with a TTL equal to the token's remaining lifetime, plus a
  per-user session index for "log out everywhere".
- Tokens carry `session_version = user.auth_session_version`. Incrementing it
  (password change, logout-all, account disabled, incident) invalidates every token
  at once.
- A token is accepted only if the signature and expiry are valid **and** its `jti`
  is allowlisted **and** `session_version` matches **and** the user is active.
- **Fail closed**: if the session store is unavailable, return 503.
- **Refresh rotation**:
  - a refresh atomically consumes the old refresh `jti`, issues a new pair, and
    records a short-lived rotated marker;
  - reusing the old token inside the grace window returns 409
    `refresh_token_recently_rotated`;
  - after the window, reuse is treated as theft and revokes the session.
- An auth audit records login, refresh failure, logout, and logout-all, with hashed
  `jti`s only.

```python
class RevocableJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        try:
            present = get_critical_redis().exists(access_key(token["jti"]))
        except RedisError as error:
            raise SessionStoreUnavailable() from error        # 503, fail closed
        if not present:
            raise InvalidToken("Token has been revoked.")
        return token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get("session_version") != user.auth_session_version:
            raise InvalidToken("Session is no longer valid.")
        return user
```

**Django sessions** (same-origin web apps):
- secure, HTTP-only cookies and CSRF protection;
- revocation through the session store, plus a `session_version` check for
  "log out everywhere".

## 6. One-time codes (if the login flow uses them)

- Codes are stored hashed, expire quickly, and are single-use (consumed with a
  guarded update).
- A per-identifier attempt row enforces lockout and returns `retry_after`.
- Sending is rate-limited per identifier and per IP.
- The response is identical for known and unknown identifiers.
- Identifiers are normalized before lookup.
- Delivery runs on a dedicated queue.

## 7. Data classification

Every model field has a class, recorded in the model contract (`models.md` §3).

| Class | Examples | Logs | Redis | Domain events | At rest | Staff |
|---|---|---|---|---|---|---|
| **Public** | catalog data | yes | yes | yes | plain | yes |
| **Internal** | statuses, counts, IDs, error codes | yes | yes | yes | plain | yes |
| **Personal** | names, phone numbers, addresses, email | masked | no | no (IDs only) | encrypted when kept long term, if the owner decides | with a content capability |
| **Sensitive** | national IDs, card numbers, IBANs, documents | **never** | **never** | **never** | **encrypted** | masked only |
| **Secret** | passwords, tokens, API keys, OTP codes, signing secrets | **never** | hashed only | **never** | hashed | **never** |

A new field without a class is an incomplete change. Retention per class follows
`models.md` §13.

## 8. Secrets and keyed hashes

- Stored secrets (API keys, invitation and reset tokens, OTP codes) are stored only
  as keyed hashes, shown once, and compared with `hmac.compare_digest`.
  Verification does the same work whether or not the record exists.
- Keyed hashes and signatures verify against `SECRET_KEY` **and** every
  `SECRET_KEY_FALLBACKS` entry, so a rotation is not destructive
  (`operations.md` §2). Re-hash with the current key on successful use.

```python
def keyed_hash(value: str, *, purpose: str, key: str | None = None) -> str:
    secret = (key or settings.SECRET_KEY).encode()
    derived = hmac.new(secret, purpose.encode(), hashlib.sha256).digest()
    return hmac.new(derived, value.encode(), hashlib.sha256).hexdigest()


def verify_keyed_hash(value: str, stored: str, *, purpose: str) -> bool:
    keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return any(hmac.compare_digest(keyed_hash(value, purpose=purpose, key=k), stored) for k in keys)
```

## 9. Configuration and request-path rules

- Production settings **fail fast** at import on:
  - a weak or development `SECRET_KEY`;
  - `DEBUG=True`, or an empty `ALLOWED_HOSTS`;
  - plaintext database transport outside the private network;
  - two Redis roles sharing one instance when the profile requires separation;
  - a missing required secret.
- Least-privilege database roles: runtime (data only) and migration (schema).
- An incoming `X-Request-ID` is accepted only if it matches
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`; otherwise a new one is generated.
- Cookie-authenticated mutations keep CSRF protection. CORS is browser policy, not
  authentication.
- Never log secrets, authorization headers, cookies, tokens, OTP codes, payment
  data, or raw third-party bodies.

## 10. Input hardening

- **Bounded JSON**: any endpoint accepting free-form JSON validates depth, node
  count, and object width iteratively, without recursion. Limits come from settings.
- **Server-side fetches** (`common/network_security.py`), for any URL supplied by a
  user or tenant:
  - allow `https` only, and no credentials in the URL;
  - resolve DNS **with a deadline**, and reject if **any** resolved address is
    private, loopback, link-local, multicast, reserved, unspecified, or denylisted;
  - pin the validated IP for the connection where possible;
  - follow redirects manually and re-validate every hop, with a cap;
  - stream the body with a size cap, set connect/read/overall timeouts, and check
    `Content-Type` against an allowlist;
  - store only a bounded failure classification, never raw bodies.
- Identifiers and text are normalized by one function each before uniqueness checks.
- Numbers: bounded ranges; money parsed from strings to integers or `Decimal`;
  `NaN` and `Infinity` rejected.

## 11. Audit log

`AuditEvent` inherits `AppendOnlyModel` and records: organization, `actor_type`
(`user`/`staff`/`api_key`/`system`), `actor_id`, `action` (a policy action name),
`target_type`, `target_id`, sanitized `metadata`, and `request_id`.

1. **Record inside the transaction that made the change**, by calling
   `audit.record(...)` in the service's `atomic()` block.
2. **If recording fails, the change fails.** Never swallow audit exceptions.
3. **Sanitize metadata**: an allowlist of keys per action, bounded sizes, no
   sensitive or secret data, IDs instead of payloads.

Audit is read through an API guarded by `audit.read`, with pagination and filters.

## 12. External integrations

- One gateway sub-package per external system (`file-organization.md` §10):
  - a `Protocol` in `base.py`;
  - the real implementation;
  - a **fake** used by tests;
  - a registry;
  - `exceptions.py` raising `RetryableError`/`PermanentError`/`AmbiguousOutcomeError`.
- Explicit connect, read, and overall timeouts. Configurable URLs pass the SSRF
  checks (§10). Credentials come from settings, never code or logs.
- Send our idempotency key with every call when the provider supports one.
- Calls run in workers (durable jobs), never inside a request's transaction.
- A reconciliation command resolves ambiguous outcomes (`operations.md` §8).

## 13. Inbound webhooks

1. **Verify first**: check the signature (or the provider's verification) on the
   **raw body**, with a timestamp tolerance. Failure → 400 with no detail, logged
   with the provider and reason class.
2. **Store once**: an `InboundWebhookEvent` row (`provider`, `provider_event_id`
   unique per provider, `event_type`, the bounded payload, `received_at`,
   `status`). A duplicate returns 200 without processing.
3. **Answer fast**: return 200 right after storing. No external calls or business
   logic in the request.
4. **Process in a worker** as a durable job, through the owning service. Processing
   is idempotent and tolerates out-of-order delivery by comparing with current
   durable state.
5. **Do not trust the payload for money**: confirm amounts and statuses with the
   provider's verification API before settling.
6. **Reconcile**: a sweeper queries the provider for operations with no callback
   after a window.
7. The endpoint skips JWT authentication, is restricted to the provider's published
   IP ranges where they exist, and is throttled.

## 14. Supply chain

- Base images pinned by digest.
- Dependencies hash-locked.
- The container runs as a non-root user.
- CI runs `pip-audit`, `bandit`, and a secret scan over git history.
- Versions live in the project policy, and `scripts/check_version_drift.py`
  compares them with the repository.

## 15. Recipes

### 15.1 Add a permission action or change a role

1. Add the action to `ACTIONS` with its scope, minimum role, and `administrative` flag.
2. Call `require(principal, action=..., resource=...)` in the service, and scope the
   queryset before lookup.
3. If API keys exist, decide the required credential scope.
4. Update the cross-tenant and role matrices.
5. Tests: both matrices, and the test that every action string exists.

### 15.2 Add a third-party integration

1. **Ask first** if it adds a dependency or a paid service (`workflow.md` §3).
2. Create the gateway sub-package (§12), with a fake.
3. Set timeouts, SSRF validation for configurable URLs, and settings for credentials.
4. Pass our idempotency key when supported, and make calls from durable jobs.
5. Add a reconciliation command for ambiguous outcomes.
6. Add metrics by error class, an alert, and a runbook.
7. Tests: the fake everywhere, plus classification tests for each provider error shape.
8. A real call only with the owner's approval, in a sandbox where one exists.

### 15.3 Receive inbound webhooks

1. Create the endpoint without JWT authentication, throttled, with a body size limit.
2. Verify the signature on the raw body with the timestamp tolerance.
3. Store the event, deduplicated by `(provider, provider_event_id)`, and return 200.
4. Process it in a durable job through the owning service. Confirm money with the
   provider's API.
5. Add a reconciliation sweeper.
6. Tests:
   - a bad signature (400, nothing stored);
   - a duplicate (200, processed once);
   - out-of-order and stale events;
   - reconciliation.
