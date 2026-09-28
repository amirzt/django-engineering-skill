# opinionated-api: API and security values

## Contents

1. Paths and URL style
2. Views and routing
3. Format specifics
4. Lists: filters, sorting, search, pagination
5. Headers
6. JWT
7. One-time codes (if used)
8. Throttles
9. Passwords (if used)
10. Production security settings
11. Limits

---

## 1. Paths and URL style

| Surface | Path |
|---|---|
| Public API | `/api/v1/` |
| Back-office API | `/backoffice/api/v1/` |
| Liveness / readiness | `/health/live`, `/health/ready` (token) |
| Metrics | `/metrics` (Bearer scrape token) |
| Django admin | `/<ADMIN_URL_PATH>/` from settings |
| OpenAPI (non-production only) | `/api/schema/` |
| Inbound webhooks | `/api/v1/webhooks/<provider>` |

- **No trailing slashes**: `APPEND_SLASH = False`, and every `path()` is written
  without one.
- Resources are plural **kebab-case** (`/order-items`). Path IDs use `<uuid:...>`.

## 2. Views and routing

- Explicit `APIView`/`GenericAPIView` classes and `path()` entries in
  `<app>/urls/v1.py`. No `ViewSet` and no routers.
- `<Resource>ListView` handles GET list and POST create, `<Resource>DetailView`
  handles GET, PATCH, and DELETE, and `<Resource><Action>View` handles a POST action.
- `PUT` is not used.

## 3. Format specifics

- In production, only `JSONRenderer` is enabled.
- Timestamps are rendered in the project `TIME_ZONE` with an explicit offset.
- Money is `{"amount": "<string>", "currency": "<ISO 4217>"}`.
- Authenticated responses carry `Cache-Control: no-store`, set by a project
  middleware.

## 4. Lists: filters, sorting, search, pagination

- Parameters: filter fields by name, plus `limit`, `cursor`, `ordering`, and `q`.
  Anything else → 400 `unknown_query_parameter`.
- Several values: `?status=paid,fulfilled`. Ranges: `?created_after=` and
  `?created_before=` (ISO 8601).
- `ordering`: `created_at` or `-created_at` by default, from a per-view allowlist of
  unchanging indexed fields, with `id` always appended.
- `q`: minimum length 2 and maximum 100, matched against an indexed `search_key`
  column.
- Pagination: cursor only, through one class in `common/pagination.py`:

```python
class StableCursorPagination(CursorPagination):
    """Cursor pagination with a deterministic order and the project list shape."""

    cursor_query_param = "cursor"
    page_size_query_param = "limit"
    ordering = ("-created_at", "-id")

    def get_page_size(self, request):
        self.page_size = settings.API_DEFAULT_PAGE_SIZE
        self.max_page_size = settings.API_MAX_PAGE_SIZE
        return super().get_page_size(request)

    def get_paginated_response(self, data):
        link = self.get_next_link()
        cursor = parse_qs(urlparse(link).query).get("cursor", [None])[0] if link else None
        return Response({"object": "list", "data": data,
                         "has_more": cursor is not None, "next_cursor": cursor})
```

## 5. Headers

| Header | Meaning |
|---|---|
| `Authorization: Bearer <jwt>` | Authentication |
| `Idempotency-Key` | `data-integrity.md` §9 |
| `X-Request-ID` | Correlation |
| `X-Organization-ID` | Tenant selector (narrows only) |
| `Accept-Language` | Message language |
| `Retry-After` | On 429 and retryable 503 |
| `Location` | On 201 |

## 6. JWT

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ALGORITHM": "HS256",
}
JWT_REFRESH_ROTATION_GRACE_SECONDS = 60
```

The mechanism is in `references/security.md` §5.

## 7. One-time codes (if used)

| Setting | Value |
|---|---|
| Code length | 6 digits |
| `OTP_VALID_SECONDS` / `OTP_RESEND_SECONDS` / `OTP_CACHE_SECONDS` | 300 / 60 / 600 |
| `OTP_MAX_FAILED_ATTEMPTS` / `OTP_FAILED_ATTEMPT_LOCK_SECONDS` | 10 / 1800 |

## 8. Throttles

These live in the critical Redis. If it is unavailable, requests get 503.

| Scope | Rate |
|---|---|
| `tenant_requests` | 600/min |
| `user` / `anon` | 300/min / 60/min |
| `otp_generate` / `otp_verify` | 3/min / 10/min |
| `file_upload` | 10/min |
| `file_delivery_capability` / `file_delivery_global` | 30/min / 600/min |
| `inbound_webhook` | 600/min per provider |

## 9. Passwords (if used)

Django's four validators, with `MinimumLengthValidator(min_length=12)`.

## 10. Production security settings

```python
DEBUG = False
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/"]
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = SESSION_COOKIE_HTTPONLY = CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")   # explicit, no wildcards
CORS_ALLOW_CREDENTIALS = False
```

`SECRET_KEY` must be at least 50 characters, must not start with
`django-insecure-`, and needs at least 5 distinct characters.

## 11. Limits

| Setting | Value |
|---|---|
| `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` | 10 MiB / 10 MiB |
| `DATA_UPLOAD_MAX_NUMBER_FIELDS` | 1000 |
| `JSON_MAX_DEPTH` / `JSON_MAX_NODES` / `JSON_MAX_OBJECT_KEYS` | 32 / 10,000 / 1,000 |
| Metadata JSON | 16 KiB |
| `FILES_MAX_IMAGE_BYTES` / `_DOCUMENT_` / `_AUDIO_` / `_VIDEO_` | 15 / 50 / 25 / 100 MiB |
| `FILES_MAX_PER_REQUEST` / `FILES_MAX_TOTAL_BYTES_PER_REQUEST` | 10 / 50 MiB |
| Image width / height / pixels | 8192 / 8192 / 16,777,216 |
| Archive entries / uncompressed size | 10,000 / 100 MiB |
| `API_DEFAULT_PAGE_SIZE` / `API_MAX_PAGE_SIZE` | 20 / 100 |
| `API_BULK_MAX_ITEMS` | 100 |
| `IDEMPOTENCY_RECORD_TTL_SECONDS` | 86400 |
| Webhook connect / read timeout | 5 / 10 s |
| Webhook backoff base / cap, max attempts, auto-disable after | 5 s / 3600 s, 12, 20 consecutive failures |
| Outbound HTTP connect / read / total | 5 / 15 / 30 s |
| Outbound redirects, response size, DNS deadline | 3, 50 MiB, 2 s |
| Outbound retries | transient only, max 3, 0.5 s → 4 s with jitter |
| Inbound webhook timestamp tolerance / body / reconcile after | 300 s / 256 KiB / 900 s |
