# AI Coach: bounded adaptation proposals

Task #508 adds a thin proposal layer on top of the deterministic program engine.
The deterministic progression, lifecycle, ownership, revision and exercise rules remain
authoritative. AI output is advisory and cannot write durable program state directly.

## Contract

- `AI_COACH_ADAPTATION_ENABLED=false` and `AI_COACH_ADAPTATION_KILL_SWITCH=false` are
  fail-closed defaults. The adaptation switch is independent from deterministic programming
  and ordinary AI Coach chat.
- The provider receives only server-selected opaque references and bounded structured context.
  Personal use requires the existing personal consent and data-policy gates. Trainer use is
  generic/canonical context and does not silently add client consent scope.
- Every proposal has a typed schema, evidence references, deterministic-rule relationship and
  `requires_confirmation=true`. Unknown candidates, unsupported prescription shapes, unsafe
  output and stale revisions are rejected.
- Confirmation re-checks actor authorization and the exact program revision, then delegates any
  durable change to the existing program-versioning service. Reject and explanation-only results
  do not mutate the program. A signed, short-lived token carries the proposal; audit and runtime
  logs store metadata and hashes only, never prompts, answers or trainer/client notes.

## Versioned evidence

The implementation pins these values in the typed contract and provider request:

- prompt: `ai-coach-adaptation-v1`
- output schema: `ai-coach-adaptation-output-v1`
- validation policy: `ai-coach-adaptation-policy-v1`

Deterministic tests cover a valid explanation, bounded output validation, unknown candidate and
prompt-injection refusal, kill-switch behavior, privacy-safe audit details and idempotent reject.
Fixtures and test requests contain no production user data.

## Activation

Merging the code does not enable the provider. If production activation is requested, the only
new environment values are the two adaptation flags above; existing provider credentials and
AI Coach policy flags remain unchanged.
