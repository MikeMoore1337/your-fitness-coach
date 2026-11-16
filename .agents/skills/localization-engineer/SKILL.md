---
name: localization-engineer
description: >
  Design, implement or review internationalization and localization across UI, backend messages,
  domain dictionaries, formatting, public routes, SEO and Telegram Mini App. Use when adding or
  changing supported locales. Do not use for a one-off copy edit with no locale architecture impact.
---

# localization-engineer

Create localized variants of **one product**, not diverging apps.

## First inventory

Inspect all user-facing Web/TMA/Admin/Coach/Demo/AI surfaces, hardcoded text and formatters, backend errors/notifications/email/bot templates, public metadata/`<html lang>`/canonicals/sitemap/structured data, domain dictionaries/enums/statuses/exercises/equipment/goals, profiles/pre-auth storage, Telegram/browser locale signals, tests/snapshots/content source and existing i18n tooling.

Classify strings as `UI resource | domain label | public editorial content | user-generated | technical literal | out of scope`. Never modify business logic, formulas, permissions or security under cover of translation.

## Locale contract

Define supported locale IDs and preferences such as `auto | ru | en`. Separate **stored preference** (user choice), **effective locale** (active language) and **initial signal** (browser/Telegram language at first use).

Recommended priority:

1. Authenticated account preference.
2. Pre-auth local preference.
3. Platform signal on first launch.
4. Browser language list.
5. Product fallback.

Manual choice must override later platform signals. Preserve preference across Web/TMA and authentication handoffs without losing other state. Define conflict behavior across tabs/devices; avoid sync loops.

## Translation resources

- Reuse one locale infrastructure and typed keys when supported.
- Organize namespaces by durable product domains, not arbitrary components.
- Never use raw English/Russian sentences as resource keys.
- Do not concatenate translated sentence fragments; grammar/order differs.
- Use interpolation and locale-aware plural/select semantics.
- Type-check placeholders, markup and variables.
- Do not render untrusted translation content through unsafe HTML.
- Show missing keys in dev/test; production fallback must be safe/observable and never expose internal enums/codes.
- Remove orphan keys only after checking dynamic consumers and tests.

## Stable domain data

Keep machine identifiers and enum codes language-neutral:

```text
exercise_id=42
code="bench_press"
labels={ru: "Жим лёжа", en: "Bench press"}
```

Never duplicate an exercise for an English label, use translated text as a foreign key, change API codes on locale switches or automatically translate custom/user-generated names.

Localized catalog/search aliases must resolve to the same canonical entity, retain source/scope/ownership and never change identity during matching/import. APIs should return stable ID/code plus requested/fallback labels; exports/imports use machine-stable fields.

## Formatting

Use standard CLDR/Intl locale-aware formatters, not ad hoc templates. Verify plural categories, decimal/group separators, dates, timezones and DST, relative time, units/ranges, percentages, currencies where relevant and week starts/calendar conventions.

Store canonical machine values independently of presentation, without translating/rounding DB values for UI. For fitness verify `кг/lb`, `км/mi`, `см/in`, `ккал`, `г`, `уд/мин`, durations and ranges. Unit choice and locale are separate settings.

## Backend and notifications

Return stable machine-readable error codes; localize messages at a defined boundary. Translated messages alone must not form an API contract. Server notifications use the policy-defined user locale at generation time; background jobs must not depend on process-global locale. Store locale/version when replay must be reproducible; avoid logging full private notification text.

## Multilingual public SEO

Decide URL strategy before translating at scale; preserve default URLs. Index each locale only when full content is reviewed. Set appropriate same-locale canonical URLs (unless documented otherwise), reciprocal `hreflang` only for real equivalents, and sitemaps only for canonical/indexable/reviewed URLs. Preserve locale in internal links where practical. Title/description/OG/structured data must match displayed content. Do not index partial/empty/machine draft pages. Treat redirects as URL migration, not string translation.

Use `$seo-auditor` for technical SEO and `$evidence-content-editor` for public editorial material.

## Telegram Mini App and bot

Telegram `language_code` is an initial automatic hint, **not** trusted identity or permanent override. Web/TMA share account preferences/resources. Runtime language changes should preserve forms, workouts and navigation. BackButton, safe areas, theme and platform controls do not need separate localization trees. Localize bot commands/menus/profile only within current bot scopes. Do not create an English news/channel pipeline if the approved channel remains Russian.

Also load `$telegram-engineer` when relevant.

## User-generated content

Never automatically translate names, notes, trainer comments, messages, custom exercises or uploaded programs. Surrounding UI may be localized, and an explicit user-initiated translation feature could be added only under a separate task.

## Text review

Judge naturalness, domain terminology, audience clarity, voice, consistency, absence of ambiguous health claims and length/layout effects, not literal word-for-word match. Never claim native-speaker review unless performed and attributed; otherwise disclose the limit.

## UI and accessibility

Verify long strings/buttons, narrow mobile/TMA, wrapping/truncation, tables/charts/tooltips, form hints/errors, keyboard/focus, screen-reader names, alt text, themes, locale-switch accessibility and mixed-language states. Do not replace visible labels with tooltip-only translations.

## Tests

Cover resolver/manual override, pre-auth/auth persistence, fallback/missing keys, interpolation/plurals, dates/numbers/units/timezones, stable domain identities/bilingual search, backend messages, public routing/canonical/hreflang/sitemap, Web/TMA continuity, absent raw enum/keys, critical-flow language consistency, pseudo-localization/controlled long strings and build/type/lint/E2E.

Use `references/LOCALIZATION_ARCHITECTURE_CHECKLIST.md` and `references/LOCALIZATION_REGRESSION_MATRIX.md`.

## Do not

Create a frontend tree per language, use runtime machine translation as source of truth, translate user content automatically, override manual preferences on every detection, translate DB IDs, index machine drafts, mass-replace text without context/grammar review or invent native reviewer evidence.

## Final report

Record locale contract/precedence, changed resources/domain/public content, storage and Web/TMA continuity, formatting/SEO choices, actual text review, tests and untranslated/out-of-scope surfaces.
