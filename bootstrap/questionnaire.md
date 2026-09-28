# Bootstrap questionnaire

Ask these questions in one message, with the default answers shown. The defaults
are the owner's usual choices; the owner may reply "use the defaults" except where
there is none. Record the answers in the policy's `## Decisions` section.

| # | Question | Default |
|---|---|---|
| 1 | Project name (short, lowercase) and one-sentence purpose? | none (required) |
| 2 | Multi-tenant? None, organizations, or organizations + projects? | organizations, each user starting with a personal one |
| 3 | Who calls the API: public clients, internal only, or both? Is there a staff back-office API? | public API + back-office |
| 4 | How do users log in (phone + one-time code, password, SSO, API keys, a combination)? Staff login requirements? | none (required; project-specific) |
| 5 | Does the product move money or finite reservations (balances, stock, seats)? | no |
| 6 | Which external services does it call with side effects (payments, SMS, email, others)? | none |
| 7 | Does it need background work (Celery)? | yes |
| 8 | Does it accept files from users or generate files? | yes |
| 9 | Does it need real-time communication (WebSockets)? | no (would need an ADR and a profile override) |
| 10 | Object storage, or local storage served through the app? | local storage, proxy delivery |
| 11 | Locale, currency, jurisdiction? | Iran: `iran` profile |
| 12 | Retention and deletion requirements (what "delete my data" must remove, how long logs and events are kept)? | tombstone content, keep evidence, purge operational data after 30 days |
| 13 | Before launch, may schema changes be direct, or must they follow expand/contract from day one? | direct before launch, with backups; expand/contract after launch |
| 14 | Expected scale and availability (requests per second, users, uptime target)? | small start; one web instance, one worker per queue |
| 15 | Customer-facing outgoing webhooks? | no |
| 16 | Profiles to apply? | `opinionated-api`, `iran` |

## What the answers add

| Answer | Adds |
|---|---|
| Always | `common/`, `events`, `config/architecture.py`, `deploy/` tooling, enforcement tests, the project policy, `AGENTS.md` |
| Any user accounts (4) | `accounts`, with the custom user before the first migration, and sessions (`references/security.md` §5) |
| Tenancy or roles (2) | `access`: principal, policy, scoping, audit (`references/security.md` §1–§4, §11) |
| Money or reservations (5) | the ledger and reservation patterns (`references/data-integrity.md` §6, §8), plus idempotency records |
| External services (6) | a gateway package per provider, inbound webhooks, reconciliation (`references/security.md` §12–§13) |
| Background work (7) | the Celery workers and queues from the profile |
| Files (8) | `files` (`references/files.md`) |
| Notifications or outgoing webhooks (6, 15) | `notifications` (`references/events-and-jobs.md` §11) |
| Back-office (3) | `backoffice/` resource packages (`references/file-organization.md` §11) |
| Iran (11) | `common/persian_text.py`, `common/iran_identifiers.py`, `fa`/`en` catalogs (`profiles/iran.md`) |

**Small internal tools** (answers: no tenancy, no money, no external services, no
files): keep `common/`, `events`, the enforcement tests, and the quality gate. Skip
`access`, `files`, and `notifications`, and use a single worker for all queues.
Record these reductions as overrides in the policy.
