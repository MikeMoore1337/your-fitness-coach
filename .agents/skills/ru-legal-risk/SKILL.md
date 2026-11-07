---
name: ru-legal-risk
description: >-
  Review and classify Russian Federation legal and regulatory risks for Your Fitness Coach;
  verify current primary sources, personal data law, health/AI/recommender obligations,
  user agreements, advertising, IP, minors, payments and cross-border processing.
  Propose SAFE/BALANCED/ACCEPT_RISK choices without deciding for the owner or fabricating compliance.
---

# ru-legal-risk

## Purpose

`$ru-legal-risk` assesses legal and regulatory **risks** for Your Fitness Coach (YFC), focused on Russian Federation law. Act in the owner's interests without promising "full legal compliance" or imposing automatic release blockers.

1. Establish actual facts and applicable norms.
2. Identify potential exposure, separating binding law from disputed interpretation.
3. Assess likelihood and consequences.
4. Consider mitigation by contracts, consent, disclaimers, UI, architecture or process.
5. Offer at least `SAFE`, `BALANCED` and `ACCEPT_RISK` options, plus `AVOID` where relevant.
6. Recommend a practical choice without deciding for the owner.
7. Record residual risk, recheck trigger and `LEGAL_COUNSEL_REQUIRED` if expert counsel is necessary.

This skill does not replace qualified legal representation or guarantee a legal outcome.

## Governing principle

Treat legal risk like engineering/business risk, without demanding perfection at any cost. Never imply that a contract, checkbox or disclaimer can waive statutory duties owed by an owner/operator/service provider.

Always distinguish user responsibilities that may lawfully be allocated by contract, mandatory law that cannot be waived, disputed applicability dependent on product facts, and risks consciously accepted by the owner **without making noncompliance legal**.

## Verified product context

Before material reviews, read `docs/private/legal/LEGAL_CONTEXT.md` if present and verify against current code, configuration, deployment and documents.

Previously known facts must not be hardcoded permanently:

- YFC uses web and Telegram Mini App on a shared backend.
- Its principal public domain uses `.ru`.
- Actual production hosting country is **unverified**; a historical imported note about Kazakhstan is not evidence without owner/deployment confirmation.
- Hosting country may change.
- Some intended users are in Russia.
- Workouts, nutrition, measurements, progress and AI Coach are in scope.
- Data categories and owner/operator legal status depend on actual implementation and documents.

The `.ru` domain is one link to Russia, not proof that every Russian regulation applies. Evaluate users' locations/citizenship, contractual relationships, data processing, advertising, payments, owner activity and real functionality.

## Mandatory verification of current law

Never rely only on model memory for legal conclusions. For each important finding:

1. State verification date.
2. Locate the operative edition of the law **on that date**.
3. Prefer primary official sources.
4. Verify amendment effective dates and distinguish adopted future rules from rules already in force.
5. Cite article/part/clause when invoking a specific obligation.
6. Never use a secondary summary as sole support for critical claims.
7. If current wording/source cannot be verified, use `CONFIDENCE: LOW` and do not assert legal certainty.

Source priority:

1. Official legal portal `publication.pravo.gov.ru`.
2. Government/regulators `rkn.gov.ru`, `fas.gov.ru`, `rospotrebnadzor.ru`, `nalog.gov.ru` and other bodies within jurisdiction.
3. `consultant.ru`, `garant.ru` for consolidated editions/navigation.
4. Court decisions and official interpretations when necessary.
5. Secondary publications only as supplements.

Refer to `references/RU_LEGAL_SOURCE_POLICY.md`.

## When to use

Use for personal and health/anthropometric/injury data; authorization/Telegram Login; accounts/export/deletion; cookies, analytics, tracking or attribution; sending data to external API/AI/cloud; moving hosting/database/backups/logging to another country; AI Coach and behavior/preferences-based recommendations; commercial features/subscriptions/refunds; trainer services/marketplace; advertising/affiliates/sponsorship; public fitness/health claims; copyrighted media, fonts, food databases or licensed content; minors; offers, terms, privacy policies, consents and recommendation rules; user-generated content; notification campaigns; changes to legal entity/sole proprietor/self-employed status or monetization; and related production gates.

Do **not** load for purely visual/internal refactoring with no material legal implications.

## Area 1: Personal data - Federal Law 152-FZ (152-ФЗ)

Verify:

- Who is the data controller/operator and who are the data subjects?
- What personal, special-category and health data is actually collected, and for which purposes?
- Are minimization and legal grounds satisfied?
- Are required consents distinguishable and provable?
- Is localization when collecting Russian citizens' data satisfied, where applicable?
- What cross-border transfers/third-party processing occur?
- Are Roskomnadzor notifications required?
- What are retention, consent withdrawal, destruction/deletion, export/access duties?
- Are extra copies in logs, backups, browsers/local storage, Telegram IDs, analytics SDKs and external AI/API providers covered?
- What incident/breach requirements apply?
- Do public policies match the actual data flow?

Do **not** assume any foreign server is automatically unlawful. Separately verify initial collection location, primary DB, foreign storage, cross-border transfer after localized collection, receiving countries/processors and applicable exceptions/grounds. Foreign-storage consent does not automatically replace statutory localization requirements.

## Area 2: Medical versus fitness boundary

Review behavior, not merely disclaimers: AI diagnosis, medications/treatment, medical interpretation of symptoms, medical-service positioning, medical promises in ads, advice under contraindications/uncertainty and relevant safe UX to stop activity/seek medical help.

A "not medical advice" statement mitigates risk only when the actual feature conforms to that scope.

## Area 3: AI Coach

Trace `user input -> context builder -> internal data -> provider -> provider country -> logs/retention -> response -> persistence`.

Verify exactly what personal and health data leaves YFC, minimization/pseudonymization, provider/subprocessor geography, retention/training policies, transfers, material user notices, prompt/tool boundaries, medical limits, contractual disclaimers, responsibility for choices based on AI and the feasibility of declining AI without losing the essential service.

## Area 4: Recommender technology - Federal Law 149-FZ (149-ФЗ)

Do **not** classify every personalized function as a regulated recommender system.

For adaptive nutrition/workouts/content/AI, assess whether user preferences are collected, organized/analyzed and used to provide information, user location in Russia, and the current legal definition and practice.

If disputed, return `LEGAL_COUNSEL_REQUIRED` and a precise question. If applicable, verify duties to inform users, publish operating rules and disclose other required information under current law.

## Area 5: Terms and allocation of risk

Reasonably allocate user choices where lawful, including accurate input, estimated calculations, absence of guaranteed fitness outcomes, the user's workout choices, known contraindications, judgment about symptoms, AI fallibility and non-medical nature, stopping unsafe activity, and effects caused **solely** by inaccurate user data, ignored warnings or misuse subject to statutory limits.

Always report `LIMITATION_EFFECTIVENESS: YES / PARTIAL / NO / UNCLEAR` and identify nonwaivable obligations. Never suggest a blanket exclusion of all liability as legally effective.

## Area 6: Consumer protection and payment

When monetization begins, verify seller/service provider, service definition, prepayment disclosures, price/recurrence, subscriptions/auto-renewal, cancellation, refunds, unilateral terms, e-receipts and applicable taxes according to verified owner status, invalid unfair clauses, offer acceptance and evidence of assent.

Do not invent the owner's legal form; if unknown report `UNKNOWN`.

## Area 7: Advertising and claims

Distinguish advertising from ordinary owned editorial content. Review promises of weight loss, muscle gain, health/guarantees, medical statements, medical-service advertising if relevant, online-ad marking/reporting when required, influencer/affiliate sponsorship, comparisons and substantiation of statistics, studies, testimonials and case studies.

## Area 8: Copyright and licenses

Verify provenance/rights for exercise illustrations, icons, fonts, photos/video, articles, food databases including Open Food Facts, AI imagery, OSS packages and provider logos/trademarks. Distinguish data use, copying content and attribution/share-alike obligations.

## Area 9: Minors

When minors can use or are targeted by the app, consider consent, information, marketing, health/fitness and personal-data duties under the actual model. An age number in Terms alone is insufficient. When the app excludes minors, assess whether age-gating would genuinely reduce risk.

## Area 10: Foreign infrastructure

Treat hosting country as mutable; on country changes review primary local storage, backups, logs, object storage, CDN/edge, analytics, email/push/Telegram, AI providers, subprocessors, transfers and foreign laws triggered by owner/user/market context. For full foreign-law interpretation state `OUT_OF_SCOPE_JURISDICTION` and request separate review.

## Evidence-first workflow

### 1. Define scope

State the specific product behavior reviewed and excluded.

### 2. Establish facts

Use current code, schemas, migrations, environment examples, deployment, privacy text, UI/API, provider documentation and live data flows. Do not treat roadmap items as implemented.

### 3. Build legal surface map

| Surface | Fact | Potential law | Review |
| --- | --- | --- | --- |
| Profile | Name + Telegram ID | 152-ФЗ | yes |
| Body metrics | Weight/measurements | 152-ФЗ; health classification | yes |
| AI provider | Payload abroad | 152-ФЗ, Art. 12/18 | yes |
| Adaptive recommendations | User preferences? | 149-ФЗ, 10.2-2 | uncertain |

### 4. Verify current legal norms

Save dated primary references and exact editions for every important finding.

### 5. Classify each finding

Required fields:

- `ID`.
- `STATUS: CONFIRMED / POTENTIAL / DISPUTED / NOT_APPLICABLE`.
- `AREA`, `FACTS`, `LEGAL_BASIS`, `EVIDENCE`.
- `LIKELIHOOD: HIGH / MEDIUM / LOW / UNKNOWN`.
- `IMPACT: CRITICAL / HIGH / MEDIUM / LOW / UNKNOWN`.
- `RISK: CRITICAL / HIGH / MEDIUM / LOW`.
- `CONFIDENCE: HIGH / MEDIUM / LOW`.
- `LIMITATION_EFFECTIVENESS: YES / PARTIAL / NO / UNCLEAR`.
- `OWNER_DECISION_REQUIRED: YES / NO`.
- `RECHECK_TRIGGER`.

Never invent precise likelihood percentages without actual data.

### 6. Offer at least three options for MEDIUM+ risks

- **SAFE**: maximally reduce substantiated legal exposure.
- **BALANCED**: pragmatic compromise among risk, cost and complexity.
- **ACCEPT_RISK**: leave implementation unchanged with explicit residual risk and consequences. Explain directly that the owner's acceptance **does not legalize** a statutory violation.
- **AVOID**: when a simple change can remove the risk surface.

For each, state changed code/docs, residual risk, effort `LOW/MEDIUM/HIGH`, qualitative cost if precise data is unavailable, benefits/drawbacks and verification.

### 7. Recommend without deciding

Consider severity, likelihood, audience size, commercial status, data sensitivity, real remediation cost, feasible avoidance, inspection/complaint risk, reputation and future-feature dependencies.

### 8. Owner decision

Never mark `ACCEPTED` without an explicit owner decision. Allowed dispositions: `FIX`, `MITIGATE`, `ACCEPT_RISK`, `AVOID`, `DEFER`, `LEGAL_COUNSEL`, `NOT_APPLICABLE`.

### 9. Recheck trigger

Accepted/deferred risks require triggers such as payment launch, server relocation, new AI provider, owner-defined user threshold N, minors, ad launch, owner/tax status change, effective new legislation, calendar date, complaint or regulator inquiry.

## Finding example

```markdown
### LR-XXX - <short title>

STATUS: CONFIRMED
AREA: Personal data localization
RISK: HIGH
LIKELIHOOD: MEDIUM
IMPACT: HIGH
CONFIDENCE: HIGH
OWNER_DECISION_REQUIRED: YES
LIMITATION_EFFECTIVENESS: NO

Facts:
- ...

Evidence:
- `path/to/file:line`
- deployment/config evidence

Legal basis checked:
- Федеральный закон ...
- article/part/clause
- edition/date of verification
- source URL

Why it matters:
...

SAFE:
- ...
Residual risk: LOW
Effort: HIGH

BALANCED:
- ...
Residual risk: LOW/MEDIUM
Effort: MEDIUM

ACCEPT_RISK:
- leave existing implementation
Residual risk: HIGH
- formal legal duties remain despite owner risk acceptance

Recommendation:
BALANCED

Recheck trigger:
...
```

## Final report

For a dedicated audit report executive summary, date/jurisdiction, verified context, scope/exclusions, confirmed risks, potential/disputed risks, risk heatmap, choices, owner questions, external-counsel items, proposed legal-document changes, dated sources/editions, actual checks and limitations. For narrow work avoid universal checklists.

## Durable legal register

Only when a task explicitly authorizes durable legal-document changes, update relevant:

- `docs/private/legal/LEGAL_RISK_REGISTER.md`.
- `docs/private/legal/LEGAL_DECISIONS.md` **after an explicit owner choice**.
- `docs/private/legal/DATA_FLOW_REGISTER.md` for changed data flows.
- `docs/private/legal/THIRD_PARTY_REGISTER.md` for providers.
- `docs/private/legal/LEGAL_CONTEXT.md` for material legal facts.

In read-only audits keep detailed findings under `.artifacts/legal-audit/` and propose diffs; do not commit documentation automatically.

## Collaborating skills

Select only relevant `$privacy-engineer`, `$security-engineer`, `$data-engineer`, `$llm-engineer`, `$billing-engineer`, `$backend-engineer`, `$frontend-engineer`, `$telegram-engineer`, `$seo-auditor`, `$technical-writer`, `$qa-engineer`. This skill cannot replace security/privacy engineering or expand task scope.

## Prohibited shortcuts

Never claim:

- User consent removes any legal exposure.
- All foreign hosting is unlawful.
- A `.ru` domain automatically imports every Russian rule.
- A disclaimer makes medical behavior nonmedical.
- An AI model's unsupported statement proves current law.

Never cite obsolete editions as current; invent fines/deadlines/procedures; silently change Terms/Privacy Policy; accept risk for the owner; auto-block release merely because `RISK: HIGH` without an applicable legal gate; hide statutory violations under `ACCEPT_RISK`; publish private data or secrets.

## Stop and escalation

State `LEGAL_COUNSEL_REQUIRED` with a **specific legal question** when disputed applicability substantially changes business/architecture, medical-activity classification is plausible, international private law is complex, critical third-party rights are disputed, a regulator issues a demand, a claim/lawsuit exists, individualized litigation strategy is needed, criminal exposure may exist, or authoritative sources cannot establish reliable interpretation. Never stop at a generic "consult a lawyer" statement.

## Completion gate

Verify facts versus assumptions, current effective legal editions and citations, nonwaivable obligations, options for MEDIUM+ risks, explicit residual exposure, no invented owner approval, recheck triggers, unknowns marked unknown and no unauthorized code/doc writes during read-only audits.
