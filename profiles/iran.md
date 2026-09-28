# Profile: iran

Locale, text, identifier, and currency conventions for products serving Iran. It
applies only when the project policy lists `iran`. Normalization lives in
`common/persian_text.py` and `common/iran_identifiers.py`, as pure, fully tested
functions, applied at the start of the service (`references/api.md` §5) before
validation, uniqueness checks, and storage.

## Contents

1. Time
2. Languages
3. Characters
4. Digits
5. Mobile numbers
6. Identifiers
7. Currency
8. Calendar
9. Search keys
10. Recipe: add a translated string

---

## 1. Time

```python
USE_TZ = True
TIME_ZONE = "Asia/Tehran"
CELERY_TIMEZONE = "Asia/Tehran"
```

- The database stores UTC `timestamptz`. The API renders in `Asia/Tehran` with an
  explicit offset: `2026-09-27T13:45:30+03:30`.
- Iran has **no daylight saving time** (abolished in 2022), so the offset is
  +03:30. Always use `zoneinfo`/`tzdata`, never a hardcoded offset.
- Day, month, and report boundaries, retention cut-offs, and crontab schedules are
  computed in `Asia/Tehran` (`timezone.localdate()`).
- The week starts on **Saturday**, and the weekend is **Friday**. Business-day logic
  uses a seeded holiday calendar table, never a hardcoded list.

## 2. Languages

```python
LANGUAGE_CODE = "fa"
LANGUAGES = [("fa", "فارسی"), ("en", "English")]
USE_I18N = True
LOCALE_PATHS = [BASE_DIR / "locale"]
# LocaleMiddleware: after SessionMiddleware, before CommonMiddleware.
```

- The request language comes from `Accept-Language` (`fa` or `en`), defaulting to `fa`.
- User-facing strings (error messages, notifications, validation messages, admin
  labels, verbose names) use `gettext_lazy`. Both catalogs stay complete.
- Never translated: error `type`/`code`, enum values, log events, metric names,
  audit actions, event names, API field names.
- **Stored data is single-language.** There are no translated database fields.
- Right-to-left rendering is a client concern.

## 3. Characters (`normalize_persian_text`)

| From | To | Applies to |
|---|---|---|
| `ي` U+064A, `ى` U+0649 | `ی` U+06CC | stored text |
| `ك` U+0643 | `ک` U+06A9 | stored text |
| `ة` U+0629 | `ه` U+0647 | search keys |
| Tatweel `ـ` U+0640 | removed | stored text |
| Arabic diacritics U+064B–U+065F, U+0670 | removed | search keys |
| Repeated ZWNJ U+200C, or ZWNJ next to a space | one ZWNJ / removed | stored text |
| ZWNJ | space | search keys |
| Surrounding or repeated whitespace | trimmed / collapsed | stored text |

Normalize Unicode to NFC first.

## 4. Digits

- Persian `۰–۹` (U+06F0–U+06F9) and Arabic-Indic `٠–٩` (U+0660–U+0669) become ASCII
  `0–9` in **every numeric and identifier input**: phone numbers, codes, national
  code, postal code, card numbers, IBAN, amounts, quantities, dates.
- Free text keeps its digits as entered, and its search key uses ASCII digits.
- The API returns ASCII digits in numeric fields.

## 5. Mobile numbers (`normalize_ir_mobile`)

- Canonical form: `09` + 9 digits (11 characters).
- Accepted input: `+989…`, `00989…`, `989…` (12 digits), `9…` (10 digits), and `09…`,
  after removing spaces and dashes and converting digits.
- Anything else → `invalid_phone_number`.
- Stored canonical, unique on the canonical form, and logged with the last 4 digits only.

## 6. Identifiers (`common/iran_identifiers.py`)

| Identifier | Rule |
|---|---|
| National code (کد ملی) | 10 digits, not all identical. With `c = d[9]`, `s = Σ d[i] × (10 − i)` for i = 0..8, and `r = s mod 11`: valid if `(r < 2 and c == r) or (r ≥ 2 and c == 11 − r)` |
| Postal code (کد پستی) | 10 digits |
| IBAN (شبا) | `IR` + 24 digits (26 characters, uppercase, no spaces). ISO 13616 mod 97: move the first 4 characters to the end, map `I`=18 and `R`=27, and the number mod 97 must be 1 |
| Card number | 16 digits, Luhn check |
| Landline | `0` + area code + number, 11 digits |

These are **sensitive** (`references/security.md` §7): never logged, masked in the
admin and API (card: `6037-****-****-1234`), and encrypted at rest when stored.

## 7. Currency

- The internal unit is the **Rial (IRR)**: whole Rials in a `BigIntegerField` named
  `*_irr`. Set `MONEY_INTEGER_SUFFIXES = ("_irr",)` in `config/architecture.py`.
- The API returns `{"amount": "<rials>", "currency": "IRR"}`.
- **Toman is display only** (1 Toman = 10 Rials): never stored, never accepted by the
  API, never mixed into calculations.
- Exchange conversions store the rate, its source, and its timestamp on the
  resulting row, and pass configured sanity bounds.

## 8. Calendar

- Storage and the API use the Gregorian calendar with ISO 8601.
- A Jalali value is only an explicit, read-only display field
  (`created_at_jalali: "1405/07/05"`), added when a client needs it and computed with
  `jdatetime` in `Asia/Tehran`. Jalali input is accepted only where a feature
  explicitly specifies it.
- Monthly reports state whether their months are Gregorian or Jalali.

## 9. Search keys

`persian_search_key(text)` applies the search-key rules of §3, ASCII digits,
lowercase Latin, and collapsed whitespace. Stored `search_key` columns and incoming
`q` values both go through it.

## 10. Recipe: add a translated string

1. Wrap the string with `gettext_lazy` (or `gettext` at runtime) where it is defined.
2. Run `python manage.py makemessages -l fa -l en`.
3. Fill both entries, following §3.
4. Run `python manage.py compilemessages`.
5. Test that the message renders in both languages where it matters (errors,
   notifications).
