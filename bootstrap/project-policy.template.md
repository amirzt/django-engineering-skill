---
status: template
skill: django-backend-engineering
profiles: opinionated-api, iran
---

# Project policy: <project name>

The decisions this project made at bootstrap, and every later change to them. Coding
agents read this file first (after the repository instructions). Change it only with
the owner's approval, and keep `python deploy/validate_project_policy.py` and
`python deploy/check_version_drift.py` passing.

## Decisions

| # | Question | Answer |
|---|---|---|
| 1 | Name and purpose | <answer> |
| 2 | Tenancy | <answer> |
| 3 | API audience, back-office | <answer> |
| 4 | Login | <answer> |
| 5 | Money or reservations | <answer> |
| 6 | External side-effecting services | <answer> |
| 7 | Background work | <answer> |
| 8 | Files | <answer> |
| 9 | Real-time | <answer> |
| 10 | Storage | <answer> |
| 11 | Locale, currency, jurisdiction | <answer> |
| 12 | Retention and deletion | <answer> |
| 13 | Schema change policy before and after launch | <answer> |
| 14 | Scale and availability | <answer> |
| 15 | Outgoing webhooks | <answer> |

## Profiles and overrides

Selected profiles: the `profiles` front-matter entry.

| Profile file and section | Override | Reason |
|---|---|---|
| <none, or one row per override> | | |

## Apps and layer order

Lowest layer first. Must match `config/architecture.py`.

| App | Owns | May import |
|---|---|---|
| `common` | infrastructure primitives | nothing first-party |
| `events` | domain events, outbox, deliveries | `common` |
| <app> | <what it owns> | <lower apps> |

Accepted exceptions: <none, or each with its ADR>.

## Authentication

<The login flow(s), registration and verification, recovery, API keys, and staff login.>

## External integrations

| Provider | Purpose | Gateway module | Queue | Sandbox |
|---|---|---|---|---|
| <none, or one row per provider> | | | | |

## Pinned versions

Copied from the selected profile at bootstrap, with every "pin at bootstrap" entry
resolved. `deploy/check_version_drift.py` compares this table with the repository.

| Kind | Name | Version |
|---|---|---|
| python | Django | <version> |

## Deferred decisions

| Decision | Reason for deferring | Owner | Revisit when |
|---|---|---|---|
| <none> | | | |
