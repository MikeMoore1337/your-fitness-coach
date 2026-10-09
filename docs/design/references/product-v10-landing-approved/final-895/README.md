# Frozen #895 final-correction captures

These 20 PNGs are byte-for-byte copies of the owner-reviewed files from
`.artifacts/tasks/895/evidence/final-correction/`, captured at
`2026-10-09T09:24:16.697Z`. `MANIFEST.json` pins their immutable SHA-256 values.
No image was generated from the recovery candidate or automatically rebaselined.

Scope: first-screen header/hero/CTA and mobile-menu appearance only. They do not
approve lower athlete sections or the six restored trainer chapters. The canonical
Landing archive remains authoritative for unchanged sections; #852 full-page
references supply the six chapters absent from that archive.

The exact capture commit was not recorded. The manifest's `deliveryHead` is the
later PR delivery revision, not a claim about screenshot runtime provenance.
The captures predate commit `05277f8fb21695daf35d2b608f8d6843e1b76dc0`, which
increased the mobile hero-footer link's touch target to 44px. Consequently the
recovery's dedicated pixel suite reports four desktop PASS and sixteen mobile
FAIL at the unchanged 0.01 threshold. This known discrepancy is retained for
owner review; it must not be silently recaptured or waived as rendering noise.

Run `npm run e2e:landing-visual` from `frontend/` after a fresh build. The dedicated
configuration starts its own strict-port preview unless an explicit external
preview is supplied. This independent gate deliberately remains red while archive
regions differ and lower-scene visual proof is missing. Required functional CI
GREEN is not equivalent to this visual gate.
