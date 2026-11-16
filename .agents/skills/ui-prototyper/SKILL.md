---
name: ui-prototyper
description: >
  Explicit-only design exploration skill. Build multiple genuinely different isolated UI directions
  for comparison without changing production code, then promote only an owner-selected direction.
disable-model-invocation: true
---

# ui-prototyper

Use **only** after an explicit request for variants or experiments.

## Goal

Explore genuinely different strong solutions to the same task, not three shades of one concept.

## Design freedom

Dedicated explorations may depart completely from Design V2/V2.1 while retaining sport-tech, mobile-first, lime/black/white brand core, product truth, accessibility and feasible performance.

Each direction should plausibly be shippable rather than a novelty concept made only to fill a quota.

## Workflow

### 1. Scope

Explore one meaningful surface or journey at a time.

### 2. Reconnaissance

Inspect actual product behavior, current stack, reusable components, baseline, target audience and mobile context.

### 3. Directions

Default to three, at most five. Differentiate explicitly by composition, density, interaction model, visual material, typography, motion, data representation or personality.

### 4. Isolation

Never modify production implementation during exploration. Use an isolated route, prototype folder, standalone harness or temporary development-only surface. Production code must not import prototypes.

### 5. Realistic context

Use realistic product-shaped labels/data, functioning interactions, mobile-first viewports, both themes when relevant and full-size previews rather than thumbnails alone.

### 6. Comparison

For each direction describe its core idea, distinguishing features, strengths, costs/risks, mobile behavior, motion role and implementation complexity. Do not choose for the owner unless asked for a recommendation.

### 7. Promotion

Only after owner selection, implement the chosen solution in a normal task, remove/archive the prototype as instructed, and update the design source when the choice changes the production visual system.

## Collaboration

`$product-designer` for quality/direction; `$motion-design-engineer` for motion-heavy options; `$landing-art-director` for Landing; `$frontend-engineer` for production; `$ui-audit` for final rendered validation.
