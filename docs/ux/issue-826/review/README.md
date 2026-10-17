# Issue #826 - owner visual review (NOT YET APPROVED)

Synthetic Playwright Chromium screenshots of the current implementation, 393x844 mobile CSS pixels, taken on Windows on 2026-10-17 from PR #1055 after fixing the workout replacement action width.

| State | Light | Dark |
| --- | --- | --- |
| Collapsed | [PNG](./after-light-393-collapsed.png) | [PNG](./after-dark-393-collapsed.png) |
| Expanded | [PNG](./after-light-393-expanded.png) | [PNG](./after-dark-393-expanded.png) |

- The replacement action is full-width within the mobile workout action region.
- "What to do now?" is a single disclosure header; the pain/injury action stays inside its expanded content.
- The chevron is rendered by shared Icon with canonical Lucide geometry.
- These are browser fixtures, NOT production/private-user captures, NOT real Safari/Telegram/VoiceOver proof.
- Layout and behavior have additional targeted Chromium/WebKit checks, including 320/360/393/430px.
- Owner visual acceptance and merge/deploy approval are still pending.
