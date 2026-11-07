---
name: telegram-engineer
description: >
  Design, implement or review Telegram Bot API, Aiogram, Telegram Mini App, BotFather,
  commands, deep links, channel publishing, moderation and broadcasts. Use when Telegram
  platform behavior or integration contracts change. Do not use for ordinary responsive web
  work or generic notifications that have no Telegram-specific behavior.
---

# telegram-engineer

Treat Telegram as a distinct platform without creating a separate product. Bot, Mini App and channel may share backend/domain services but have separate trust boundaries, limits and failure modes.

## First

Before changes read `AGENTS.md`, relevant documentation, task and configuration. Establish actual Bot API/Aiogram/Mini App versions, runtime, Router/Dispatcher/FSM storage, polling/webhooks, jobs/tests, login/linking, notifications, timezones, proxy and deep-link contracts, and the process owning the bot token.

Verify affected Bot API limits and BotFather procedures against current official documentation. Never change production bot token, channel, BotFather or real admin rights without explicit owner authorization. Do not create a parallel bot runtime/token/TMA for a new support/news/moderation feature.

## Platform surfaces

1. **Private bot chat**: commands, support/feedback, preferences, notifications and moderation.
2. **Telegram Mini App**: shared web UI with its own platform adapter.
3. **Channel**: publication only to configured allowlisted channels with verified permissions.

Bot polling and browser Telegram OAuth/login are separate network flows; do not combine them into implicit proxy/TLS configuration or break one to repair the other.

## Bot runtime and Aiogram

One bot token must have exactly one long-polling owner. For scale, assess whether webhook transport is justified and plan migration separately. Use `Dispatcher` for orchestration and small `Router` modules; keep business logic, SQL and integrations outside handlers. Use explicit services and testable Bot API adapters.

Startup metadata synchronization, registration and health checks must be idempotent and avoid endless restarts during temporary Telegram failures. Preserve existing polling locks, bounded retries/backoff, graceful shutdown and allowed-updates rules. Do not remove the legacy runtime before functions/tests are migrated and shutdown is controlled.

## Commands, menus and `/start`

Keep canonical commands in one place, reused by `setMyCommands`, `/help`, BotFather owner checklist and tests. Observe scopes/languages; visible commands are not authorization. Backend must recheck roles and rights.

Order `/start` payload handlers explicitly: sensitive/specific payloads (account linking) before generic menu fallbacks. Unknown payloads should fail safely with understandable state; unknown commands must not auto-forward to admins. Keep admin commands out of default public scope. Read Mini App/privacy URLs and public links from verified shared configuration, never production staging tunnels.

## FSM and multi-step flows

For support/editing/moderation, define states/transitions, `/cancel`, TTL/timeouts and restart policy. In-memory FSM alone is insufficient when restart loss breaks critical flows. Free text outside an active flow must not silently become a support ticket/admin action. Allowlist media with limits/fallback; use safe Bot API copy/forward instead of downloading files unnecessarily. Prevent cross-user state mixing and stale-state replay.

## Telegram Mini App

Reuse the shared frontend, APIs, authorization model and design system; implement a platform adapter rather than a second UI tree.

### Per-feature mobile gate

Every client-facing change must extend applicable shared TMA smoke tests and fix introduced TMA regressions **in its own scope**. Final platform hardening is not a substitute for per-feature verification.

Use `$mobile-engineer` for keyboard, safe areas, lifecycle, touch and performance; use `$telegram-engineer` for Bot/Mini App API, initData trust, BackButton, links and compatibility, guided by `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md`.

Required:

- Pass only raw `initData` to the trusted backend and verify signature, freshness and bot binding server-side.
- Never trust `initDataUnsafe`, query parameters, frontend `user_id` or `language_code` as identity.
- Never log/transmit raw `initData` to analytics, errors or external telemetry.
- Preserve account linking and allow valid TMA launches without inappropriate browser login.
- Handle `isActive`, `BackButton`, themes, `viewportHeight`/`viewportStableHeight`, keyboard and `safeAreaInset`/`contentSafeAreaInset`.
- Handle `viewportChanged`, `safeAreaChanged`, `contentSafeAreaChanged` without losing route/form/dialog state.
- Degrade gracefully on older/unsupported clients.
- Never use Telegram theme colors as the sole carrier of contrast/semantics.
- Preserve unfinished state across Web/TMA context switches when reasonable.
- Deep links must target permitted app context, never arbitrary URLs/paths.

## Callback queries and admin actions

Bind sensitive callbacks to actor, resource/draft/user scope, immutable revision/version, concrete action and relevant expiry/staleness checks. Validate all server-side because callback data is untrusted.

Idempotency must prevent duplicate replies, subscriptions, publications or mutations from retries/double taps. Stale callbacks must report that the original revision was replaced, not apply the action to a new version.

## Channel, moderation and publishing

- Channel IDs/usernames come from server allowlists, never arbitrary callbacks/commands/frontend.
- Verify membership and minimum admin rights before publishing; lack of rights is not an indefinitely retriable transient error.
- AI-generated material requires explicit moderation when the task specifies it.
- Bind approval to exact immutable revision and media hash. Regeneration invalidates the old approval.
- Retry publishing the **approved** revision only, not a newer draft.
- Keep idempotency key, resulting content hash, channel/message IDs and audit fields.
- Escape untrusted HTML; use safe entities/formatting.
- Verify active Bot API text/caption/media limits, never guess.
- When over limits use a defined concise/text-only fallback, not an unexpected multi-message thread.
- Images are optional; image-provider errors must not block the entire editorial flow.

## Broadcasts and anti-spam

Optional news/marketing digest defaults OFF and requires explicit opt-in; distinguish product notifications from optional digests. Unsubscribe must be immediate/idempotent without mandatory confirmation. Recheck opt-in directly before sending queued messages. Rate-limit below current free limits; honor `429`/`retry_after`, bound attempts and disable optional delivery to blocked/deactivated chats under policy. Never silently re-enable subscriptions. Bots cannot assume they can message accounts that have never interacted.

## Security and privacy

Never log bot/provider secrets, raw TMA initData, private support messages, subscriber/admin/member lists, user documents/photos or unnecessary Telegram IDs. Keep admin IDs in secure server config, not UI authorization. Make source fetch SSRF-safe with redirect/DNS/type/size/timeout bounds, clean up temporary media, preserve TLS verification and hide raw API errors from users. Also use `$security-engineer` and `$privacy-engineer` for sensitive changes.

## Tests

Select proportionate handler/service unit tests, `Dispatcher` routing without live polling, mocked Bot API adapters, FSM/jobs/subscription/idempotency integration, Web/TMA adapter browser tests, reusable TMA mock with version/platform/theme/viewport/safe-area/BackButton events, separate real Telegram Android/iOS smoke plus optional Desktop, explicitly configured test bot/channel manual smoke and owner-operated BotFather/channel checklist.

Use relevant portions of `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md` and existing bot tests. Never silently change production BotFather/channel settings.

## Collaboration and report

`$backend-engineer`: APIs/transactions; `$frontend-engineer`: shared UI; `$localization-engineer`: locale/bot messages; `$evidence-content-editor`: publishing; `$llm-engineer`: AI generation; `$platform-engineer`: runtime/deployment; `$observability-engineer`: safe metrics; `$qa-engineer`: regressions.

Do not substitute `$mobile-engineer` for Telegram API/security expertise merely because the flow runs on a phone; both often apply to TMA flows.

Final report: changed Telegram surfaces, polling/webhook ownership, commands/links/auth contracts, manual BotFather/channel actions, actual checks and smoke evidence, limits, rate limits and deployment implications.
