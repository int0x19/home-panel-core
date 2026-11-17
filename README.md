# Home Panel Core

Shared Python package for Home Panel firmware tools and the Home Assistant
companion. This repository is the canonical source for models/profiles,
resolved-style validation, no-scroll row planning, canonical JSON, the bounded
configuration client/protocol and the browser's immutable room/action/sensor draft logic.

Python >=3.13. No Home Assistant, ESPHome, YAML, templates or hardware dependency
is needed. The optional `http` extra supplies aiohttp for standalone HTTP use;
HA supplies its own shared session. The transport is read/check-only by default.
Separate explicit opt-ins support guarded candidate Send and Apply, never
household services. Send does not apply; an Apply receipt is not proof of
activation. See [Send](docs/CANDIDATE_SEND.md) and [Apply](docs/CANDIDATE_APPLY.md).

## Build And Test

Node >=20 is required for the shared JS draft tests; CI checks its presence so
that those cases cannot silently skip. No browser is required by core tests.

```sh
python -m venv .venv
.venv/bin/python -m pip install setuptools wheel
.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
.venv/bin/python -m pip install --no-deps dist/home_panel_core-0.1.2-py3-none-any.whl
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

Core 0.1.2 adds [shared numeric-sensor/group edits](docs/SENSOR_DRAFT.md),
including mixed-row fit guards. It keeps schema/protocol v1, does not advertise
new device capabilities. Its subsequent candidate Send slice adds only guarded
Upload and exact readback. The subsequent HA companion source exposes it through
its administrator backend/editor with a one-use imported baseline and checked
digest; Apply and physical acceptance remain separate.
The same unpublished development version now recognizes the firmware's explicit
[readings preview profile](docs/READINGS_COMPATIBILITY.md), without granting
management, asset or dispatch permissions. Legacy SD/action negotiation stays
supported; firmware/device acceptance is independent of this client support.

Core 0.1.1 adds read/check compatibility with the deployed internal-flash
configuration storage. Flash pairing/export no longer requires an SD card;
legacy SD status is still supported. See [flash compatibility](docs/FLASH_COMPATIBILITY.md).

Package releases and logical JSON schema versions are independent. Version
0.1.0 preserves schema/protocol v1 and the previous canonical encoding. HA host
validation is not a certificate of current ESP32 assets, memory, authority or
deployment readiness. Keep per-device negotiation and validation gates.

## Provenance

Extracted from `esp32panel` commit `b72b70f` on 2026-11-07. The initial Git
history is the subtree of `custom_components/home_panel/panel_config`; earlier
history before those models moved from scripts remains in the firmware repo.
The shared JS and synthetic acceptance fixtures were transferred in this split.
The public GitHub origin is `https://github.com/int0x19/home-panel-core.git`.
Core 0.1.1 is bundled in published HA release 0.1.1; local development toward
0.1.2 is not yet a published release. No PyPI publication is required.

## GitHub Distribution

The GitHub repository is `int0x19/home-panel-core`. This library is **not** a
Marketplace integration. Users install `home-panel-ha`, whose release bundles
the pinned core automatically, without PyPI or an extra Marketplace entry.

The package workflow builds/tests a wheel on pushes and pull requests. A tag
matching `project.version` exactly (initially `0.1.0`, without a `v` prefix)
prepares a **draft**, not published, GitHub release with the wheel attached.
Review licensing and release notes before publishing. No PyPI credentials or
publication are required. The HA repository locks the source commit separately
in `core-source.json`; update that lock explicitly when upgrading core.

## License

Apache-2.0; see [LICENSE](LICENSE). Copyright 2026 Denis and contributors.

Split acceptance: 34 installed-wheel tests pass, including loopback HTTP.
Firmware consumers also pass their native C++/LVGL parity checks; HA source and
the self-contained release ZIP are tested in the separate companion repository.

Flash compatibility acceptance: 39 installed-wheel tests pass, including
loopback HTTP, explicit profile validation and export without SD. A read-only
snapshot also passes against the deployed flash-confirmed ESP32. No OTA or
configuration/device command was performed for that snapshot.

Shared sensor-draft acceptance: 49 source tests pass, including the ten
Node-driven draft cases and loopback HTTP. Device-family acceptance and
downstream HA/native rendering checks are separate consumer gates.
The subsequent consumer checks pass 212 HA tests and actual Linux C++/LVGL
sensor-edit acceptance, including the browser-exported JSON. Core 0.1.2
remains a local development version, not a published Marketplace upgrade.
