---
name: document-import-engineer
description: >
  Design, implement or review safe deterministic import of structured XLSX, CSV, DOCX or TXT data
  through validation, parsing, normalization, preview, matching and confirmed canonical writes.
  Use for document/spreadsheet import workflows. Do not use for generic uploads or exports that do
  not parse user files into domain entities.
---

# document-import-engineer

Import is an **untrusted ingestion pipeline**. Uploading a file must never immediately create canonical data.

## Mandatory pipeline

```text
upload
-> file validation
-> bounded parsing
-> neutral draft
-> preview
-> resolve warnings/ambiguity
-> validate domain rules
-> explicit confirm
-> transactional canonical write
```

Parsing and matching must not create programs, exercises, aliases or other canonical entities. Any failure before confirmation must leave canonical data unchanged.

## Before implementation

Inspect domain schemas, versioning, ownership, permissions, existing upload/storage/parsers, locale/units/design, runtime/deployment/temporary storage constraints, canonical template and supported variants. Do not add unsupported format parsers or promise arbitrary import "from any app".

## Allowlisted formats

Support only explicitly approved extensions and structures. Verify extension, untrusted MIME/type, actual signature/container, parser output and expected schema. Never use filename for storage path/identity; generate an internal random ID.

Define per-format maximum size, expanded archive size/compression ratio, sheet/row/column/cell/string counts, paragraph/table limits, parse timeout/memory budget, supported encoding/delimiters, formulas/relationships/objects policy, retention and cleanup.

## XLSX/DOCX security

These are ZIP containers. Before and during extraction protect against decompression bombs, excessive entries, oversized content, archive path traversal, nested archives, external relationships, embedded objects, macros, malicious XML/entity expansion and unexpectedly large shared strings/styles.

Never execute macros, formulas, links, OLE objects or embedded code. Formula cells must either be unsupported or use only bounded cached values under documented rules, with visible warnings; never calculate them server-side through an office application. DOCX text import, if introduced, must match predefined patterns; LLM-only silent structure creation is forbidden.

## CSV/TXT

Bound encoding/delimiter detection by supported candidates and sample size; handle BOM and documented fallback. Limit field/line counts and lengths. CSV is not inherently safe: prevent formula-marker values from silently becoming active formulas on subsequent spreadsheet export. Never execute template expressions, shell-like content or URLs. Ambiguous encodings/delimiters require explicit choice or a clear error.

## Temporary storage

Store uploads outside public web root with private permissions and unguessable identifiers; never use original filenames as paths. Delete temporary files after parse/cancel/expiry/error under a controlled lifecycle. Do not send confidential files to external scanners/LLMs without separate privacy approval, or log raw rows, notes or documents. Cleanup must be idempotent and observable.

## Neutral draft

Use a versioned draft separate from the canonical model containing import ID/owner/status/schema version, source format, parsed rows/entities, source sheet/row/cell/paragraph provenance, normalized values, warnings/errors, unresolved matches, parser/template version and creation/expiry times. Never expose raw parser objects as API/storage contracts.

Revalidate drafts safely across deployments. When versions are incompatible, require re-upload rather than guessing at migration.

## Template and schema

The canonical template must be versioned, contain required/optional columns, include only synthetic examples, use stable machine field identifiers, document aliases, open in target spreadsheet apps and pass round-trip tests. Localize aliases but keep canonical IDs stable. Define policies for duplicate/unknown columns. Do not infer column meaning from fuzzy similarity without a preview.

## Normalization and validation

Separate syntactic parse, normalization, field validation, cross-row/domain validation, matching and canonical transaction.

Handle locale decimal separators, whitespace/nonbreaking spaces, numeric ranges/types, units, empty vs zero, duplicates, supersets/group references and consistency. Errors must identify source row/cell and how to correct them.

## Entity matching

Use this predictable order:

1. Stable ID when supported and ownership valid.
2. Normalized exact visible name.
3. Approved global/user alias.
4. Token/fuzzy candidate search.
5. Domain hints (for example equipment/muscle).
6. Confidence category and candidates.
7. Manual resolution.

Only one uniquely high-confidence candidate may auto-match; ambiguity must remain visible. Fuzzy scores cannot create entities. Users select existing entities or create allowed personal entities explicitly. Confirmed personal aliases are user-scoped; a user cannot change the global catalog. Global aliases need separate moderation. Bilingual labels share one canonical ID; cross-user/private entries must not appear as candidates. Avoid uncalibrated confidence percentages; explain categories instead.

## Preview UX

A mandatory preview shows parse status, resulting structure, warnings/errors, matched/unmatched/ambiguous rows, source locations, normalized data, domain validity and what will/will not be created.

Allow cancel, resolution changes and re-upload. Disable confirm for blocking errors. Test mobile/TMA, keyboard, screen readers, long names and large but valid imports. Do not build an unnecessary raw spreadsheet editor in-browser.

## Confirmation and canonical writes

Recheck authorization/ownership and expiry; revalidate critical rules on the server. Use one explicit transaction without partial writes; protect confirm against duplicate submit/replay. Preserve audit/provenance without confidential raw contents. Create an editable draft domain entity instead of auto-assigning/activating/starting unless explicitly requested. On concurrent catalog changes, return to resolution instead of silently picking another match.

## Permissions and privacy

Self-import creates user-owned records. Trainer/coach imports recheck current capability and relationship **at confirm**, not only upload. Revoked access blocks confirm/download. Admin access does not imply access to private source files. Source and preview IDs must not be predictable/cross-user accessible. Define separate retention/export/deletion for files, drafts and canonical records.

## LLM and OCR boundary

Default to **no** LLM-only parsing, OCR, image/PDF extraction or arbitrary competitor migrations. An LLM may propose only untrusted candidates while deterministic parsing, visible uncertainty and mandatory human review remain. PDF/images/OCR require a separate owner decision, threat model, quality policy and task.

## Testing

Cover template round trips, minimal/full valid data, localized aliases/units, ambiguity/no match, personal custom entries, malformed archives/XML/CSV, ZIP bombs/traversal/external relationships/macros/formulas/objects, limits, encoding/delimiters, duplicates/replay/concurrent confirms, no partial writes, self/coach allow/deny/revoked, cleanup/expiry, private logging and mobile/TMA/accessibility preview.

Use `references/SAFE_IMPORT_CHECKLIST.md` for the full threat/test review.

## Skill collaboration

`$security-engineer`: upload/parser threats; `$privacy-engineer`: retention/sharing; `$backend-engineer`/`$data-engineer`: draft/transactions; `$frontend-engineer`/`$product-designer`: preview UX; `$localization-engineer`: aliases/units; `$fitness-domain-reviewer`: exercise/program semantics; `$qa-engineer`: adversarial regression.

## Final report

Include supported formats/template versions, limits and active-content policy, neutral draft/matching/confirm contracts, permissions/retention, **actually executed** adversarial/security tests, unsupported formats and known ambiguities.
