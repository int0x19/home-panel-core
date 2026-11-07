# Shared Core Roadmap

- [x] Extract the pure model, codec, profiles, row planners and read/check client
  from esp32panel with subtree history and a standalone wheel.
- [x] Package the common JS draft module and synthetic protocol fixtures.
- [x] Test installed-wheel use without HA, ESPHome, YAML or sibling source trees.
- [ ] Add CI/package publication after the repository origin and release policy
  are configured. Until then use pinned local/release wheel artifacts.
- [ ] Extend versioned schema/model/fixtures only as device runtime support and
  consumer compatibility tests are accepted. Do not infer device assets or RAM
  acceptance from host limits or package versions.
- [ ] Keep transport, canonical JSON and edit logic interoperable across
  explicitly supported consumer releases; never add generic service dispatch or
  hardware/network credentials to runtime JSON.

HA registry/editor work belongs to home-panel-ha. Native renderers, physical
capacity, storage recovery and OTA acceptance belong to the firmware repository.
