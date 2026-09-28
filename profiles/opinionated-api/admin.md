# opinionated-api: Django admin

The admin is an operator tool, not a business-logic surface.

## Contents

1. Setup
2. Files
3. Every ModelAdmin sets
4. Hard rules
5. Tests
6. Recipe: add an admin page

---

## 1. Setup

- The theme is django-unfold.
- The URL is `/<ADMIN_URL_PATH>/` from settings, non-guessable in production. The
  header and title also come from settings.
- Staff users only. In production the proxy **should** restrict the path by IP
  allowlist or VPN.

## 2. Files

- A small app uses `admin.py`. With more than one aggregate, `admin/__init__.py`
  imports `admin/<aggregate>_admin.py`.
- Register with `@admin.register(Model)`, one `ModelAdmin` per model.

## 3. Every ModelAdmin sets

| Option | Rule |
|---|---|
| `list_display` | Explicit: a short ID, status, tenant, `created_at` |
| `list_select_related` | Every foreign key shown in the list |
| `search_fields` | Indexed columns only; `=field` for IDs and phone numbers |
| `list_filter` | Status and dates, never a high-cardinality foreign key |
| `ordering` | Explicit and index-backed (`("-created_at", "-id")`) |
| `list_per_page` | 50 |
| `show_full_result_count` | `False` on large tables |
| `readonly_fields` | Every server-controlled field: `id`, timestamps, `status`, hashes, sizes, tenant |
| `raw_id_fields` / `autocomplete_fields` | Every foreign key to a large table |
| `date_hierarchy` | Only on an indexed date column |
| `fields` / `fieldsets` | Explicit, never `"__all__"` |

## 4. Hard rules

- **Evidence models are read-only**: `has_add_permission`, `has_change_permission`,
  and `has_delete_permission` return `False`.
- The site-wide `delete_selected` action is disabled
  (`admin.site.disable_action("delete_selected")`). A model that truly needs it
  re-enables it, with a comment saying why.
- **Writes with business rules go through services**, with a staff service
  principal, so validation, events, and audit happen as for any caller:
  - `save_model`, `delete_model`, and custom actions all call services;
  - plain configuration models may use the default save.
- Every admin action and service-backed save writes an audit event with actor type
  `staff`.
- Secrets are never displayed, and sensitive identifiers are masked. Customer
  content is shown only to staff with the content capability.
- Custom actions are thin: they collect the IDs, call one service per object (or a
  bounded batch service), and report counts with `message_user`.

## 5. Tests

- Every `ModelAdmin` gets a smoke test: the changelist and change form render for a
  superuser, and the changelist has an `assertNumQueries` bound.
- Evidence-model tests assert that add, change, and delete are forbidden.

## 6. Recipe: add an admin page

1. Create the `ModelAdmin` per §3, in `admin.py` or `admin/<aggregate>_admin.py`.
2. For an evidence model, make every permission read-only.
3. Route business writes and custom actions through services, with audit.
4. Mask sensitive fields and exclude secret ones.
5. Add the smoke test (§5).
