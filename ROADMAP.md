# Shared Core Roadmap

## Immediate Scope (2026-11-17)

Reuse HA administrator authorization, the existing panel access credential and
ESPHome state/action facilities. Core now supports bounded explicit Send-candidate
through the current HTTP job API. The subsequent HA source exposes it through
its administrator backend/editor. Core now also supports separate guarded
Apply/activation inspection; next expose those operations in HA. Keep imported-base/session/generation/digest conflicts, validation
and no automatic replay. Persistent multi-controller ownership/scoped-key
handover is deferred, not a prerequisite for this single-HA workflow. Its
private native backend remains inactive; no public handover, HA Apply control
or managed capability readiness is enabled. See firmware
`docs/IMPLEMENTATION_SCOPE.md` and the contract's scope correction below.

## Implementation History

- [x] Add explicit flash Apply with independent transport opt-in and bounded
  read-only activation inspection, still development 0.1.2. Use original
  paired candidate/base, exact export, mutation receipt rules and existing
  boot phases; distinguish unchanged/restarting/confirming/confirmed/rolled-back/
  unverified outcomes. Confirm only after the exact trial's local first-frame/
  health confirmation and verified active SHA/readback. No automatic Apply
  replay, new MCU fields/endpoints, HA Apply control or device deployment.
  See [Apply contract](docs/CANDIDATE_APPLY.md).
- [x] Add guarded flash candidate Send in development 0.1.2, using explicit
  transport opt-in, the original imported snapshot and existing Upload API.
  Verify exact candidate bytes and unchanged active/backup/loaded state; refuse
  stale imports and different candidates, do not rewrite an identical candidate,
  and never replay an uncertain write. No MCU source changes or Apply. See
  [Send contract](docs/CANDIDATE_SEND.md). HA exposure and physical acceptance
  remain separate gates.
- [x] Extract the pure model, codec, profiles, row planners and read/check client
  from esp32panel with subtree history and a standalone wheel.
- [x] Package the common JS draft module and synthetic protocol fixtures.
- [x] Test installed-wheel use without HA, ESPHome, YAML or sibling source trees.
- [x] Configure the public GitHub origin, Apache-2.0 license, CI and draft-release
  workflow. Core 0.1.1 passes 39 tests; HA 0.1.1 bundles its pinned source in the
  published Marketplace archive. A separate public core/PyPI release is not
  required for integration installation.
- [x] Support guarded flash-NVS status/export/validate without requiring SD,
  preserving legacy SD behavior and identity/session/digest checks. Read/check
  import passed against the physical panel on 2026-11-16; no managed writes,
  Apply or household commands are enabled by this change.
- [x] Add shared immutable numeric-sensor/group draft transactions in core
  0.1.2: names, entities, units/classes, optional group titles, stable room-local
  IDs, moves and orphan-group cleanup. Check mixed action/sensor row height,
  horizontal group fit and coalesced source limits against the existing model.
  Source tests pass; consumer UI/native acceptance is tracked separately.
- [ ] Extend versioned schema/model/fixtures only as device runtime support and
  consumer compatibility tests are accepted. Do not infer device assets or RAM
  acceptance from host limits or package versions.
- [x] Recognize the explicit unmanaged `esp32-readings-preview` capability target
  in development 0.1.2. Check its widget/features and combined binding/subscription
  ceiling, preserve the legacy action profile and keep all deployment/dispatch
  permissions false. Core source passes 50 tests; downstream and physical
  acceptance remain separate. See [profile contract](docs/READINGS_COMPATIBILITY.md).
- [ ] Keep transport, canonical JSON and edit logic interoperable across
  explicitly supported consumer releases; never add generic service dispatch or
  hardware/network credentials to runtime JSON.
- [x] Prepare typed `write-base.v1` status and read/check freshness checks in
  development 0.1.2. Reject malformed tokens and changed bases at the same
  generation without replay; preserve legacy read-only compatibility. Core
  source passes 52 tests. The firmware enforces the condition at its own writer;
  persistent ownership and HA Send/Apply remain separate. See [write base](docs/WRITE_BASE.md).
- [x] Track the firmware's private owner-journal preparation (2026-11-17):
  two-copy persistent epochs, Claim/Rotate/Release and a fresh leased native
  write gate are host-tested. This adds no public endpoint or core writer and
  does not enable managed readiness. Keep core/consumer 0.1.2 and the tested
  functional source pin. Public handover/scoped credentials are now deferred by
  the immediate scope above. See [authority boundary](docs/WRITE_BASE.md#private-authority-backend).

HA registry/editor work belongs to home-panel-ha. Native renderers, physical
capacity, storage recovery and OTA acceptance belong to the firmware repository.
Both local source consumers now pin 0.1.2. HA acceptance passes 212 tests and
the firmware's actual C++/LVGL path accepts shared sensor edits, including the
browser's exported JSON. These host checks do not widen the physical device's
action-only configuration profile. The subsequent explicit readings capability/
storage boundary now passes 50 installed-core, 213 HA and 70 scoped native
consumer checks, with one optional skip and no ESP32 deployment. The subsequent
HA Send extension shares the existing client/operation gate and tests the exact
checked bytes, stale tabs, lost replies and unchanged UI. The Apply client slice
now passes 79 installed-core, 232 HA and 114 scoped native checks (two optional
sanitizer skips), without MCU code/OTA. Next expose Apply/inspection in HA; the
write-base guard is prepared and multi-controller ownership is deferred.
