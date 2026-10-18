# Solution

- Start from `origin/master` at `ace951a13c2672189fdc464e92bd12b6371f3914`, reconcile the existing implementation PR #1096 branch, and keep all work in the same remote PR branch.
- Reuse the existing `ProgramTemplate` response and `GET /api/v1/programs/templates/{template_id}` authority. Derive preview facts only from explicit source fields:
  days from `days`, frequency from assigned weekdays or explicit metadata, level from the known template/metadata enum, equipment only from a complete source list, duration only from explicit source/assignment values, and `Нет данных` otherwise.
- Keep view, select, copy, edit and schedule assignment separate. Preserve server-side authorization, conflict handling and replacement confirmation. Before scheduling, fetch the current template and compare a content/ownership/revision signature; on a changed source show the preview again and do not mutate assignment.
- Preserve existing modal accessibility infrastructure. Focus the actual preview opener before opening so Escape returns focus consistently in Chromium and WebKit, including recommendation and active-program entry points.
- Keep the approved composition and separate the scrollable preview content from the compact action footer; make the primary action full-width and prevent the footer from covering exercises or source notes on narrow screens. Correct the visible exercise plural in the existing card metadata.
- Extend deterministic unit/E2E fixtures only with synthetic own, legacy/incomplete, trainer-assigned, stale and replacement-confirmation states. Do not commit screenshots or use private/production data.
