# API design, validation, and errors

Universal API rules: resources, methods, body format, where validation happens, how
errors are modelled and rendered, lists, actions, concurrency, bulk, uploads,
long-running work, and versioning. Concrete choices (URL prefixes, `APIView`
versus `ViewSet`, pagination style and parameter names, limits) come from the
project policy's profile.

## Contents

1. What the profile decides
2. Resources and URLs
3. Methods and status codes
4. Body format
5. Validation layering
6. Domain errors
7. The error envelope and the exception handler
8. Constraint violations
9. The error catalog
10. Lists: filtering, sorting, search, pagination
11. State-transition actions
12. Optimistic concurrency
13. Bulk operations, uploads, long-running work
14. Views, serializers, OpenAPI
15. Versioning
16. Recipes: endpoint, list endpoint, action endpoint, error code

---

## 1. What the profile decides

Take these from the policy's profile, never invent them:
- the URL prefix and trailing-slash style;
- `APIView` versus `ViewSet`/routers;
- the pagination mechanism, its parameter names, the list shape, and page limits;
- header names beyond the standard ones;
- rendering of timestamps and money;
- throttle scopes and rates;
- request size limits.

With no profile, follow the repository's existing conventions.

## 2. Resources and URLs

- Resources are plural nouns (`/orders`), and path IDs are opaque public IDs (UUIDs).
- **Nesting is at most one level**, and only when the child cannot exist without the
  parent (`/orders/{id}/items`). Otherwise the child is top-level with a filter
  (`/shipments?order_id=`).
- URLs are declared explicitly in `<app>/urls/`.

## 3. Methods and status codes

| Operation | Method | Success |
|---|---|---|
| List | `GET /orders` | 200 |
| Retrieve | `GET /orders/{id}` | 200 |
| Create | `POST /orders` | **201**, `Location` header, the resource |
| Partial update | `PATCH /orders/{id}` | 200, the resource |
| Delete | `DELETE /orders/{id}` | **204** |
| State transition | `POST /orders/{id}/cancel` | 200, the resource (§11) |
| Accepted async work | `POST ...` | **202**, the resource in a pending status (§13) |

Every mutation response returns the full resource.

## 4. Body format

- JSON only. snake_case field names.
- Every documented field is always present; an unknown value is `null`.
- IDs are strings. Enum values are lowercase snake_case strings.
- Timestamps are ISO 8601 with an explicit offset. Dates are `YYYY-MM-DD`.
- Money is an object with the amount as a **string**:
  `{"amount": "1250000", "currency": "IRR"}`. Never a float.
- Every object carries `id`, `object` (the type name), and `created_at`.
- Unknown request fields are rejected (`file-organization.md` §7).
- No `?expand=` and no dynamic field selection unless the profile adds them.

## 5. Validation layering

| Layer | Validates | Fails with |
|---|---|---|
| Django/DRF parsing | Body size, content type, JSON syntax | `ParseError` → 400 |
| **Serializer** | Shape, types, formats, lengths, enum membership, unknown fields, cross-field rules that depend **only on the request** | `ValidationError` → 400 `validation_failed` |
| **Normalization** (first lines of the service) | Canonical forms of text, digits, phone numbers, identifiers | `DomainError` |
| **Policy** | Who may do it; whether the resource is in scope | `PolicyDenied` → 404 or 403 |
| **Service** | Rules needing database state or time: existence, transitions, limits, balances | `DomainError` |
| **Model `clean()`** | Single-row invariants for admin forms | `ValidationError` (admin) |
| **Database constraint** | Final truth: uniqueness, checks, foreign keys | `IntegrityError` → mapped `DomainError` (§8) |

- Order inside a service: normalize → resolve scope and authorize (scope failures
  are 404 first) → load and lock → business rules → write → emit events.
- **Each rule has one owning layer.** Others may mirror it for a friendlier
  message. A money, security, or resource limit is never owned by a serializer.
- Serializers never query the database for business validation.
- Validation never has side effects.

## 6. Domain errors

`common/errors.py` (from `assets/project/`) defines `ErrorCategory`, `DomainError`,
`DependencyUnavailable`, and `PolicyDenied`. An app's `exceptions.py`:

```python
class OrderNotCancellable(DomainError):
    category = ErrorCategory.CONFLICT
    code = "order_not_cancellable"
    default_message = _("The order cannot be cancelled in its current state.")
```

- One class per condition. A class that declares `code` is registered at import
  time, and a duplicate code raises `TypeError`.
- `default_message` is user-facing and translated. `DomainError(param=..., **context)`:
  `context` is logged, never returned, and never holds sensitive data.
- Expected conditions are `DomainError`s. A generic exception crossing a service
  boundary is a bug, and it becomes a 500.

## 7. The error envelope and the exception handler

Every error response has exactly this shape:

```json
{"error": {"type": "conflict_error", "code": "order_not_cancellable",
           "message": "The order cannot be cancelled in its current state.",
           "param": null, "details": [], "request_id": "req_4f2c9e"}}
```

`details` lists field errors for validation failures:
`[{"param": "items[0].quantity", "code": "min_value", "message": "..."}]`.

`REST_FRAMEWORK["EXCEPTION_HANDLER"] = "common.api_errors.exception_handler"` maps:

| Raised | Status | `type` | `code` |
|---|---|---|---|
| `DomainError` | its category | its category | its `code` |
| DRF `ValidationError` | 400 | `invalid_request_error` | `validation_failed` + `details` |
| `ParseError` | 400 | `invalid_request_error` | `malformed_request` |
| `NotAuthenticated` | 401 | `authentication_error` | `authentication_required` |
| `AuthenticationFailed` (incl. invalid JWT) | 401 | `authentication_error` | `invalid_token` |
| `PolicyDenied` (scope), `Http404`, `DoesNotExist` | 404 | `not_found_error` | `not_found` |
| `PolicyDenied` (role/credential), DRF `PermissionDenied` | 403 | `permission_error` | `permission_denied` |
| `MethodNotAllowed` / `UnsupportedMediaType` | 405 / 415 | `invalid_request_error` | `method_not_allowed` / `unsupported_media_type` |
| `Throttled` | 429 + `Retry-After` | `rate_limit_error` | `rate_limited` |
| Database connection errors | 503 + `Retry-After` | `service_unavailable_error` | `dependency_unavailable` |
| Unmapped `IntegrityError`, anything else | 500, logged with traceback | `server_error` | `server_error` |

- `type` and `code` are never translated; `message` follows the request language.
- A 500 never includes exception text, SQL, stack traces, provider payloads, or
  configuration. The `request_id` finds the log entry.
- Changing a status or code for an unchanged condition is a breaking change.

## 8. Constraint violations

```python
try:
    with transaction.atomic():          # a savepoint keeps the outer transaction usable
        order = Order.objects.create(...)
except IntegrityError as error:
    raise_for_constraint(error, {"orders_order_org_idempotency_key_uniq": DuplicateOrderRequest})
```

`common/constraint_errors.raise_for_constraint` reads psycopg 3's
`diag.constraint_name`. SQLite has no equivalent, so its tests are PostgreSQL-tier
tests.

## 9. The error catalog

`deploy/generate_docs.py` writes `docs/api/errors.md` from the registered codes and
the handler's built-in codes. Never edit it by hand; `--check` fails in CI when it
is stale.

## 10. Lists: filtering, sorting, search, pagination

- **Filtering**: each list view declares an explicit allowlist (a django-filter
  `FilterSet` with named fields). Unknown query parameters are rejected with 400.
  Several values are comma-separated, and ranges use `_after`/`_before` names.
- **Sorting**: a per-view allowlist, with a deterministic tie-breaker (`id`) always
  appended. With cursor pagination, sort keys must be unchanging and indexed.
- **Search**: only on endpoints that declare it. The query goes through the same
  normalization as the stored search column, which is indexed.
- **Pagination**: never offset or page-number pagination on a collection that can
  grow without bound. Use cursor or keyset pagination, with an ordering that ends
  in a unique column and a matching index, plus a maximum page size. The mechanism
  and response shape come from the profile.
- Every list endpoint has an `assertNumQueries` test proving the query count does
  not grow with the page size.

## 11. State-transition actions

A status change is **never** a `PATCH` of `status`. It is
`POST /<resources>/{id}/<verb>`, where the verb is a transition name
(`cancel`, `confirm`, `archive`). The body carries only the transition's inputs.
An illegal transition returns 409 with the transition's error code.

## 12. Optimistic concurrency

A resource edited by several actors exposes an integer `version`. `PATCH` must send
the `version` it read, and the service updates with
`filter(id=..., version=read_version).update(..., version=F("version") + 1)`.
Zero rows updated → 409 `version_conflict`.

## 13. Bulk operations, uploads, long-running work

- **Bulk**: none by default. When needed:
  - `POST /<resources>/bulk-<verb>` with `{"items": [...]}`, a maximum item count,
    and `Idempotency-Key` required;
  - response: `{"object": "bulk_result", "results": [{"index", "id", "status", "error"}]}`;
  - each item runs in its own transaction unless the endpoint is documented as
    all-or-nothing.
- **Uploads**: only the file resource accepts `multipart/form-data`
  (`files.md` §7). Other resources reference `file_ids`, and JSON never carries
  base64 files.
- **Long-running work**: return **202** with the resource in a pending status.
  Clients poll the resource, and completion emits a domain event that can drive a
  notification or webhook.

## 14. Views, serializers, OpenAPI

- Views do HTTP only (`file-organization.md` §6). Every view sets its throttle
  scope, pagination, and filters explicitly where they apply.
- Input and output serializers are separate classes.
- Authenticated responses carry `Cache-Control: no-store`, except file content
  (`files.md` §5).
- Every view method has an OpenAPI annotation with an operation id, summary, tag,
  request, responses (including the error envelope for each error status), and an
  example. The generated schema is committed and drift-checked.

## 15. Versioning

Within a version only **additive** changes: new endpoints, new optional request
fields, new response fields, and new error codes for new conditions. Removing or
changing anything a client reads needs a new version, or a documented deprecation
approved by the owner and recorded in an ADR.

## 16. Recipes

### 16.1 Add an endpoint

1. Register the policy action (`security.md` §15.1).
2. Write the service and its domain errors (§6).
3. Write the strict input serializer and the output serializer.
4. Write the view: principal → one service → presenter. Set the throttle scope.
   Handle `Idempotency-Key` for mutating POSTs (`data-integrity.md` §9).
5. Add the URL and the OpenAPI annotation.
6. Run `deploy/generate_docs.py` (OpenAPI, error catalog).
7. Tests:
   - contract: statuses, shape, error envelope;
   - validation errors;
   - cross-tenant 404 and role 403;
   - idempotent replay;
   - emitted events;
   - `assertNumQueries` for reads.
8. Verify the real flow (`workflow.md` §5).

### 16.2 Add a list endpoint

1. Everything in 16.1.
2. Pagination per the profile, and an ordering index (`models.md` §7).
3. A filter allowlist, and rejection of unknown parameters.
4. Sort keys that are unchanging and indexed.
5. Search only if needed, on a normalized, indexed search column.
6. Tests:
   - pagination across pages with concurrent inserts;
   - each filter, and an unknown parameter (400);
   - ordering;
   - cross-tenant isolation;
   - a query count independent of page size.

### 16.3 Add an action endpoint

1. The transition itself (`data-integrity.md` §10).
2. The endpoint per 16.1, as `POST /<resources>/{id}/<verb>`, with a body carrying
   only the transition's inputs.
3. It returns the full resource.

### 16.4 Add an error code

1. Add a `DomainError` subclass to the owning app's `exceptions.py`, with a category,
   a unique snake_case `code`, and a translated `default_message`.
2. If it maps a constraint, add the mapping at the write site (§8).
3. Add the translations.
4. Add the status to the view's OpenAPI responses.
5. Run `deploy/generate_docs.py` (error catalog).
6. Tests: the condition renders the right status, type, code, and message.
