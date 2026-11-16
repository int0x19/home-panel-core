# Shared Core Roadmap

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
- [ ] Extend versioned schema/model/fixtures only as device runtime support and
  consumer compatibility tests are accepted. Do not infer device assets or RAM
  acceptance from host limits or package versions.
- [ ] Keep transport, canonical JSON and edit logic interoperable across
  explicitly supported consumer releases; never add generic service dispatch or
  hardware/network credentials to runtime JSON.

HA registry/editor work belongs to home-panel-ha. Native renderers, physical
capacity, storage recovery and OTA acceptance belong to the firmware repository.
The next shared-core work follows the first HA-edited room/sensor workflow;
firmware host tools remain pinned to 0.1.0 until their upgrade is tested.
