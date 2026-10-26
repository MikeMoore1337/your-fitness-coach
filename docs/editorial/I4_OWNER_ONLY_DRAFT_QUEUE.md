# I4 — очередь образовательных статей: automation prepares, owner publishes

Owner policy 25 October 2026: automatic Research Scout collection, structured evidence-based writing, QC and draft transmission are permitted; **only a human Root-owner may decide to publish**. [Hermes plan #599](https://github.com/MikeMoore1337/hermes/issues/599) / [YFC work #1226](https://github.com/MikeMoore1337/your-fitness-coach/issues/1226).

## Existing production boundaries

- Hermes daily science metadata: `research_scout/daily_digest.py`, with correction/retraction handling. Metadata is **not** full-text proof and must never be elevated into invented effect sizes or qualified scientific signoff.
- YFC `POST /api/v1/hermes/articles/intake` accepts an HMAC-signed complete `HermesWebArticleIntakeRequest` and leaves the article in `draft`; needs a real candidate ID, provenance, idempotency and source matrix. Still the **only** Hermes→Web article handoff.
- YFC `POST /api/v1/admin/articles/publish` requires a verified Root session and `acknowledge_unverified_evidence=true`, logs real owner actor, preserves `pending` claim reviews honestly. This action is not callable by Hermes, any daily job, or a model provider.

## Root-only read API (first I4 stage)

- `GET /api/v1/admin/articles/drafts?limit=25&offset=0`: bounded (1–50 items, offset 0–5000) private list of `draft`, `review` and `update_required`, exact content hash/version, headline, risk/evidence, source and pending-claim counts, review blockers.
- `GET /api/v1/admin/articles/drafts/{article_id}`: read-only exact latest article source and claim matrix, limitations, generation provenance, content version/hash for owner inspection.
- Both require `require_root_admin`, cannot change article status or create approval; no auto-exposure in public routes or sitemap. No new credentials. Root dashboard visual UI **not implemented** until explicit visual approval.

## Remaining separate stages

1. Automate source collection and metadata dedup within existing Hermes boundaries, using only free sources.
2. Draft generation **only from actually retrieved, attributable source text**, not titles/abstracts alone as evidence of effectiveness. Unavailable full text or missing free provider → `HOLD` / `NEEDS_CONTENT`, not a fabricated long-form article.
3. Complete `HermesWebArticleProposal`, validate DOI/PMID, correction/retraction, licenses, topic taxonomy, source-to-claim matrix, injection/duplication/risk, exact source version.
4. Auto-provision or securely reuse existing candidate_id through an approved HMAC-only mechanism, then signed intake *into draft only*, with receipt and replay safety. Never use Root tokens in automation.
5. Submit PNG/HTML visual owner review of inbox and draft details, then implement owner-only UX actions. Only an explicit owner click can invoke the existing publish endpoint.
6. Prove on production: automated `draft` exists and is **not public**, owner approval creates audit entry and publication, rejected/unreviewed content stays private.

**Do not** create a second publisher, deploy paid AI, turn `review_status=pending` into `verified` without evidence, publish due to a timer, or misrepresent an owner editorial decision as external scientific review. The already published I3 article is not an automated publishing precedent.
