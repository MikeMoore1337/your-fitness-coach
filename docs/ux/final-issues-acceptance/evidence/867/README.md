# Issue #867: active workout dock clearance

The images in `after/` are real screenshots from the synthetic `mockActiveWorkout` fixture at runtime commit `be3d2a2a0ffac3e27c44029578f3354197387736` (PR #927). They cover Chromium and WebKit, 320/360/393/430 CSS px, and dark/light themes.

The BEFORE baseline is the owner-reported overlap captured at commit `c8ece94` in the existing [#914 acceptance package](../../..//issue-914-acceptance/README.md). The baseline is preserved for comparison; it is not reused as an AFTER proof.

`provenance.json` records the fixture, commands, viewport matrix, and geometry/touch invariants. The test checks the current completion action and any visible next-set action before the navigation tap, uses `elementFromPoint`, verifies rest-panel separation, keeps current set `202`, and observes no set mutation from the navigation tap.
