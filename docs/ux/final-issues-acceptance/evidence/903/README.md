# Issue #903 — comparable browser evidence

The captures below come from the built YFC landing application at `/for-athletes`. Each state uses
the same fixture, viewport, theme, scroll offset, loaded fonts and reduced-motion setting. The
Playwright test also runs the same interaction contract on `/` and `/for-athletes`.

Runtime commits:

- BEFORE: `297ee2fd87f09ef6b5f7e2bd6753bd1ff7d38a55`
- AFTER: `733933a7` (the code commit that removes the competing rings)

Each cell contains a full viewport capture and a direct crop of the score scale.

| State | 390×844 dark | 390×844 light | 1440×900 dark | 1440×900 light |
| --- | --- | --- | --- | --- |
| BEFORE · no selected value | [viewport](./before/none-390-dark.png) · [scale](./before/scale-none-390-dark.png) | [viewport](./before/none-390-light.png) · [scale](./before/scale-none-390-light.png) | [viewport](./before/none-1440-dark.png) · [scale](./before/scale-none-1440-dark.png) | [viewport](./before/none-1440-light.png) · [scale](./before/scale-none-1440-light.png) |
| BEFORE · pointer selected 5 | [viewport](./before/before-390-dark.png) · [scale](./before/scale-pointer-390-dark.png) | [viewport](./before/before-390-light.png) · [scale](./before/scale-pointer-390-light.png) | [viewport](./before/before-1440-dark.png) · [scale](./before/scale-pointer-1440-dark.png) | [viewport](./before/before-1440-light.png) · [scale](./before/scale-pointer-1440-light.png) |
| BEFORE · keyboard focus | [viewport](./before/keyboard-390-dark.png) · [scale](./before/scale-keyboard-390-dark.png) | [viewport](./before/keyboard-390-light.png) · [scale](./before/scale-keyboard-390-light.png) | [viewport](./before/keyboard-1440-dark.png) · [scale](./before/scale-keyboard-1440-dark.png) | [viewport](./before/keyboard-1440-light.png) · [scale](./before/scale-keyboard-1440-light.png) |
| AFTER · no selected value | [viewport](./after/none-390-dark.png) · [scale](./after/scale-none-390-dark.png) | [viewport](./after/none-390-light.png) · [scale](./after/scale-none-390-light.png) | [viewport](./after/none-1440-dark.png) · [scale](./after/scale-none-1440-dark.png) | [viewport](./after/none-1440-light.png) · [scale](./after/scale-none-1440-light.png) |
| AFTER · pointer selected 5 | [viewport](./after/after-390-dark.png) · [scale](./after/scale-pointer-390-dark.png) | [viewport](./after/after-390-light.png) · [scale](./after/scale-pointer-390-light.png) | [viewport](./after/after-1440-dark.png) · [scale](./after/scale-pointer-1440-dark.png) | [viewport](./after/after-1440-light.png) · [scale](./after/scale-pointer-1440-light.png) |
| AFTER · keyboard focus | [viewport](./after/keyboard-390-dark.png) · [scale](./after/scale-keyboard-390-dark.png) | [viewport](./after/keyboard-390-light.png) · [scale](./after/scale-keyboard-390-light.png) | [viewport](./after/keyboard-1440-dark.png) · [scale](./after/scale-keyboard-1440-dark.png) | [viewport](./after/keyboard-1440-light.png) · [scale](./after/scale-keyboard-1440-light.png) |

The AFTER state keeps native radio semantics, uses one circular selected surface, and shows the
keyboard ring only for `:focus-visible`. A pointer click does not add a second focus ring.

Source commits and capture details are recorded in [provenance.json](./provenance.json).
