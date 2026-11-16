# Home Panel Core

Shared Python package for Home Panel firmware tools and the Home Assistant
companion. This repository is the canonical source for models/profiles,
resolved-style validation, no-scroll row planning, canonical JSON, the bounded
read/check client/protocol and the browser's immutable action-draft logic.

Python >=3.13. No Home Assistant, ESPHome, YAML, templates or hardware dependency
is needed. The optional `http` extra supplies aiohttp for standalone HTTP use;
HA supplies its own shared session. Nothing in this package uploads/applies a
configuration or calls household services.

## Build And Test

```sh
python -m venv .venv
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
.venv/bin/python -m pip install --no-deps dist/home_panel_core-0.1.0-py3-none-any.whl
.venv/bin/python -m unittest discover -s tests -v
# Optional loopback HTTP tests:
.venv/bin/python -m pip install '.[http]'
PANEL_CONFIG_HTTP_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

Consumers install a pinned wheel, not a relative source path or Git submodule.
The HA release builder bundles this exact wheel so installation needs neither
PyPI publication nor sibling checkouts. Generated release copies are not edited.
Use `home_panel_core.asset_path("runtime-draft.mjs")` for the shared JS asset.

`home_panel_core.testing` contains only synthetic wire data and a fake transport
for downstream acceptance. Its fixed IDs/key are test fixtures, not credentials.
The firmware repository retains native C++/LVGL cross-language acceptance.

## Compatibility

Package releases and logical JSON schema versions are independent. Version
0.1.0 preserves schema/protocol v1 and the previous canonical encoding. HA host
validation is not a certificate of current ESP32 assets, memory, authority or
deployment readiness. Keep per-device negotiation and validation gates.

## Provenance

Extracted from `esp32panel` commit `b72b70f` on 2026-11-07. The initial Git
history is the subtree of `custom_components/home_panel/panel_config`; earlier
history before those models moved from scripts remains in the firmware repo.
The shared JS and synthetic acceptance fixtures were transferred in this split.
No upstream remote or public package publication has been configured.

## GitHub Distribution

The prepared GitHub destination is `int0x19/home-panel-core`; repository creation
and public publication are separate owner actions. This library is **not** a
Marketplace integration. Users install `home-panel-ha`, whose release bundles
the pinned core automatically, without PyPI or an extra Marketplace entry.

The package workflow builds/tests a wheel on pushes and pull requests. A tag
matching `project.version` exactly (initially `0.1.0`, without a `v` prefix)
prepares a **draft**, not published, GitHub release with the wheel attached.
Review licensing and release notes before publishing. No PyPI credentials or
publication are required. The HA repository locks the source commit separately
in `core-source.json`; update that lock explicitly when upgrading core.

Split acceptance: 34 installed-wheel tests pass, including loopback HTTP.
Firmware consumers also pass their native C++/LVGL parity checks; HA source and
the self-contained release ZIP are tested in the separate companion repository.
