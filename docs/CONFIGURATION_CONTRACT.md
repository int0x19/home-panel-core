# HA Configuration Management Contract

## Status And Scope

First host/client slice, 2026-11-07, for roadmap 3.8.1 and the device-client part
of 3.8.2. The primary editor will run in HA; ESP32 will validate/store JSON,
render the shared LVGL widgets and exchange live states/actions through Native
API. The companion must not replace the standard ESPHome integration.

Implemented here: a bounded asynchronous read/check client, injectable transport,
optional aiohttp adapter and fixtures/tests for the existing device API. The
subsequent `capabilities.v1` extension is prepared in component source and the
client, with Linux acceptance only; it is not installed on the physical panel.
An isolated read-only HA integration (see the firmware/HA repository documentation) now wraps this client,
with config/options/reauth/reconfigure flows and diagnostic entities tested
against real HA 2026.11.0 fixtures. It is not the editor or managed deployment,
and cannot pair with the currently installed legacy firmware.
No ESP32 image build, OTA, device configuration write or household command was
performed for these slices. `export` and `validate` create ephemeral main-loop
jobs but do not publish files or change the running document.

The installed JSON path still controls the separate action preview, with runtime
dispatch disabled. Working rooms/entities remain generated from `panel.yaml`.
An imported file is not proof that its widget families can run on the device.

## Responsibilities And Data Flow

```text
HA editor -> authenticated HA backend -> panel configuration HTTP API
    |                  |                           |
  draft          validated candidate          local JSON / recovery
                                                   |
                                            shared LVGL renderer

HA entity states/actions <-> ESPHome Native API <-> panel controllers
```

HA selects entities/areas on user request, imports capability defaults, resolves
the existing template tokens and generates the same canonical JSON as the
runtime contract (see the firmware/HA repository documentation). It owns bounded drafts/history,
not a parallel renderer or a new widget schema. ESP32 independently validates
the required features, byte/model/layout budgets and references before storing
or activating a document. A larger SD card does not increase RAM budgets.

Credentials, hardware/network/OTA configuration, executable templates and live
sensor samples do not belong in runtime JSON. HA remains authoritative for live
availability, device state and alarm conditions. Removing/stopping the companion
must not erase the cached interface; HA downtime still interrupts live updates
and household commands.

## Independent Versions And Identities

| Item | Meaning | Current implementation |
| --- | --- | --- |
| JSON `format` / `schema_version` | Logical configuration format | `home-panel-runtime` / `1` |
| Status `version` | Configuration HTTP profile, not widget schema | `1` |
| Status `revision` | Boot-scoped operation/concurrency counter | Starts at 1; not the JSON revision |
| JSON/file `revision` | Version carried by a particular document | May differ between active/candidate/backup/loaded |
| `session_id` / `csrf` | Boot-scoped nonce; required to match | Not a stable panel identity or durable revision |
| SHA-256 | Exact exported/file bytes | Content integrity, not a signature or authenticated transport |
| HA draft revision | HA checkpoint optimistic concurrency | Prepared/tested nonce + persisted generation; independent of device counters; see checkpoints (see the firmware/HA repository documentation) |
| Stable panel ID | Pairing/ownership identity independent of IP | Installed: absent; prepared `capabilities.v1`: factory MAC-48 ID |
| Room/widget IDs | Persistent logical placement identities | Preserve on rename/reorder/rebind |

`loaded_revision` describes the selected boot model, whereas the active SD file
may have changed since boot. Neither alone proves renderer readiness or a
successful trial. File exports describe a guarded snapshot, not an atomic
snapshot of the whole panel's files, loaded UI and HA states.

## Capability And Compatibility Matrix

| Capability | Current device boundary | Client policy |
| --- | --- | --- |
| Status and file metadata | Available | Parse bounded typed fields |
| `export.v1` / `validate.v1` | Advertised when implemented | Require the individual feature before POST |
| Input ceiling | Current deployment: 16384 bytes | Read `max_bytes`; never assume the host's 64 KiB budget applies |
| Stable panel identity | Installed: absent; prepared: factory eFuse MAC-48 | `None` for legacy; explicitly pin the negotiated ID for pairing |
| Runtime widget/layout/subscription budgets | Prepared: decoder inventory/configured ceilings | Not measured board capacity; loaded assets/inventory still incomplete |
| Managed ownership/credential scope | Not implemented; shared debug key | Legacy: unreported; metadata: unmanaged/not enforced; never write-ready |
| Active model digest and first-frame/trial status | Not fully reported | Do not claim deployment/boot confirmation |
| Runtime household dispatch | Disabled in the installed preview | No action or activation methods in this client |
| No SD / invalid file / old feature set | Supported error states | Status/check may work; never silently export defaults as active |

The checked-in status fixture is synthetic and contains no real credentials or
device identity. It represents the installed profile's shape, not a declaration
of future measured device capabilities. An older v1 uploader without the two
features can still report status; its missing feature is not guessed or worked
around by scraping HTML. Unknown HTTP profile versions are rejected. Unknown
extra status fields/features are ignored unless a reviewed adapter supports
their semantics; an unexpected field must not enable writes.

Before managed deployment, extend metadata using an explicit negotiated
capability/protocol change: stable identity, actual runtime families/assets,
measured board limits, authority and active-model/readiness reporting. Keep the
configuration schema unchanged unless its logical semantics actually change.
Record tested releases and compare canonical fixtures with the existing shared
validator. Official ESPHome onboarding inputs are not a persistent layout store.

## Prepared Capabilities Extension

`capabilities.v1` is an additive feature of HTTP profile v1, with its own
`metadata_version: 1`, not a new runtime configuration schema. Initially
host-tested on 2026-11-07, the legacy identity/action profile is deployed by the
2026-11-16 checkpoint. The subsequent explicit readings profile is prepared in
source only. Old firmware remains usable
for explicit unpaired diagnostic status/export/check; it cannot be paired by
this new client by guessing an identity or borrowing the Native API address.

The extension adds `device_id` (or null if unavailable) to status and job
acceptance/completion receipts. Clients trust this field only when the status
advertises `capabilities.v1`. The authenticated GET route
`/panel/runtime/api/capabilities` returns an immutable boot-scoped document:

| Section/Field | Legacy Action Profile v1 Meaning |
| --- | --- |
| `format`, `metadata_version`, `protocol_version` | `home-panel-capabilities`, `1`, `1` |
| `device_id`, `identity_source` | `esp32-efuse-<12 lowercase hex digits>`, `esp32-efuse-mac48` |
| `session_id` | Must match the preceding status and subsequent job receipts |
| `target`, `config_format`, `schema_versions` | `esp32-action-preview`, `home-panel-runtime`, `[1]` |
| `features`, `widget_types`, `room_kinds` | Decoder features; only action widgets, ordinary/Actions rooms |
| `display` | Fixed decoder/preview target: width 320, height 480 |
| `limits` | Configured input/scratch/model/presentation ceilings; rooms/pages/placements/bindings/text/depth/nodes; zero runtime subscriptions/views/attention |
| `limits_measured_on_device` | False; bounds are not proof every maximum fits simultaneously |
| `validation` | Accepted action icons/interactions/font sizes and required layout/theme key inventories |
| `runtime` | Preview compiled or model-only; production rooms and runtime dispatch remain false |
| `assets` | Firmware-supplied, no upload; complete loaded asset inventory is not yet implemented |
| `authority` | `unmanaged`, `enforced: false`; no owner or handover protocol yet |
| `deployment_ready`, `management_ready` | Both false; metadata must not arm controls or writes |

Development core 0.1.2 additionally recognizes `esp32-readings-preview` from
the flash owner's general decoder. Its inventory adds `widget.sensor`,
`widget.status`, `sensor-groups.v1` and sensor/status widget types. The configured
combined unique-source ceiling is reported as both `entity_bindings` and
`subscriptions`; it is not the device's aggregate callback count. All authority,
production/dispatch, readiness and incomplete-asset caveats above remain.
Legacy SD remains action-only. See [readings compatibility](READINGS_COMPATIBILITY.md).
HA/core 0.1.1 reject the new target, so update/accept the companion before
deploying such firmware; the current source changes do not publish either.

Identity uses the SDK's documented
[`esp_efuse_mac_get_default`](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/system/misc_system_api.html#mac-address),
not a configured interface MAC, random boot token, hostname, IP or an SD/NVS
record. The initial hardware profile is the ESP32-S3 factory MAC-48. Other chip
families need their own SDK/hardware acceptance before claiming that profile.
Reading fails closed on SDK error, all-zero or multicast MAC values: status
reports null and the metadata route returns 503, with no invented fallback ID.
MAC identity prevents accidental pairing drift; it is not cryptographic
authentication or protection from an active HTTP attacker.

The C++ decoder and endpoint share feature/icon/interaction/font inventories
and parser/text/count constants, including the generated layout/theme field
macros. Input/scratch/model/presentation ceilings come from the actual boot
options. The native tests compare them with the existing Python contract;
no separate HA widget/layout implementation is introduced. `validation` describes
accepted syntax, not complete loaded font/image coverage. Generated room widgets
are not claimed as runtime-deployable capabilities.

The main loop builds one cached metadata body per component boot. HTTP only
borrows its immutable bytes, without SD/LVGL I/O or a large HTTP-task JSON build.
With the existing PSRAM configuration the retained serialized body uses the
shared PSRAM-backed HTTP JSON allocator. It is not one body per browser/job.
Target allocation peaks, heap/stack deltas and physical identity stability still
require separately authorized build/deployment and hardware measurement.

`client.capabilities()` checks the profile, device/session identity and input
ceiling against status. A future explicit pairing flow stores the returned ID
and constructs a client with `expected_device_id=<chosen ID>`; it must not
automatically adopt any ID at reconnect. A missing feature/identity or a different
ID raises `IdentityMismatch` before an export/check POST. On negotiated firmware,
job acceptance/completion IDs are checked too. Downloads retain the existing
session/digest/filename guards with no new header, preserving IDF's eight-header
budget. Capability parsing never enables managed deployment.

## Authority And Preference Rules

These are **target rules**, not ownership enforcement in current firmware:

1. Local mode permits authenticated manual JSON import and the existing
   generation/default workflow. HA may read/import/check but must not silently
   adopt ownership or send a saved draft on reconnect.
2. HA-managed mode requires explicit authenticated pairing/handover with a
   stable device ID and persistent opaque owner identity. The device must
   enforce the owner/revision checks; a client-only flag is insufficient.
3. A second HA instance, concurrent browser or emergency local recovery cannot
   silently win. Reject stale writes; present current versus proposed revision
   and digest, then require an explicit user decision and ownership transition.
4. Cache the validated applied document and a compatible previous/default copy
   locally. Losing HA or an owner connection must not erase configuration.
5. Until a tested preference migration exists, keep socket aliases, Plant
   overrides, light presets and backlight preferences in their existing stores.
   JSON supplies defaults and does not silently clear those overrides. Import
   into HA should show conflicts rather than flatten overrides or change targets.
6. Resolve each override by its existing stable identity/precedence, not page
   array position or display name. Later reset/import/migration must explicitly
   specify which override is retained/reset, preserve compatible backup data and
   never execute an action as a migration side effect.

Managed writes must remain disabled until authority enforcement, scoped access,
capabilities and activation verification are implemented and tested. The local
maintenance page remains an authenticated recovery route, not a second rich
editor or a bypass of ownership/security checks.

## Read/Check Client Contract

`home_panel_core` has no HA imports or runtime renderer
dependencies. Its public operations are `status()`, `snapshot()`,
`capabilities()`, `export(Source)` and `validate(bytes)`.
`snapshot()` reads status and metadata under one operation lock, returning an
immutable pair only after identity/session/input-ceiling guards agree. The HA
coordinator owns one pinned client per entry and polls only this GET snapshot.
Its administrator-only backend (see the firmware/HA repository documentation) shares that client for
explicit import/check jobs, bounds one transaction per entry and requires a
fresh explicit idle status after uncertain outcomes. No persistent writes or
actuator methods are exposed.
There are deliberately no upload/Apply/restore/discard/scan/actuator methods.
The transport allowlist enforces these routes independently of the client.

- One client serializes complete operations; the integration owns one
  client per paired panel, not one per browser. Other clients can still replace
  the device's one retained export; fail visibly rather than silently retrying.
- Require an HTTP(S) origin without userinfo/path/query/fragment. Use injected
  aiohttp sessions, disable redirects and decompression, bound per-request and
  whole-operation time, and read streamed responses up to a hard byte ceiling.
  Do not close a session owned by HA or create a second HA state connection.
- Parse duplicate-free bounded JSON with typed integers/booleans; bound nesting
  and reject non-finite/invalid Unicode values. Metadata is capped at 16 KiB;
  document input/output additionally follows the device's `max_bytes`, with a
  conservative 64 KiB client hard ceiling. These are rejection limits, not
  measured ESP32 capacities or an alternate widget validator.
- Require current feature, idle/not-restarting status and the correct session
  and operation revision. Poll the exact accepted job ID/session/revision;
  bound poll count and total time, reject evicted/expired/stale receipts and
  never automatically resubmit a POST after timeout or an unknown result.
- Exports whitelist active/candidate/backup, require valid file metadata and
  compare the initial file digest/size to the receipt. Accept only the exact
  relative `/panel/runtime/api/downloads/<job-id>` path, never a server-supplied
  arbitrary URL/path. Verify nonce, fixed attachment filename, length and SHA
  header, then calculate SHA-256 over the received bytes and compare the JSON
  envelope/revision to the file metadata. Reject duplicate critical headers.
- Preserve exact exported bytes; do not reconstruct/reorder JSON or substitute
  the builtin template for an absent/invalid active file. Framing/envelope
  checks are not complete domain/layout validation: the shared host validator
  is reused by the future editor, and ESP32 validates independently.
- Validate-only accepts bounded bytes, including malformed JSON so that the
  common device validator can return its normal report. Invalid input is a
  typed unsuccessful result, not an SD write or configuration change. OOM/
  unavailable service remains an HTTP failure, not proof that the model is bad.
- A timeout/lost submission has an unknown ephemeral-job outcome. Cancellation
  stops the client wait, not a job already queued on ESP32. Do not infer failure
  or success, retry automatically or release another client's snapshot. Read
  status before any new explicit request. Exception text and repr omit access
  keys, raw server errors, JSON payloads and session nonces.

The existing wire API and storage limitations (see the firmware/HA repository documentation)
remain authoritative. HTTP on a trusted LAN/VPN is not encrypted; the SHA does
not protect against an active attacker, and Native API encryption does not
cover this HTTP channel. Never expose it publicly. The future frontend talks
only to administrator-authorized HA backend commands; no device key goes to a
browser, iframe, URL, local storage, log or portable JSON backup.

## Later Deployment State Machine

```text
HA draft -> host validation -> device validate-only -> explicit Send candidate
         -> saved candidate -> explicit Apply/restart -> observed running model
                                                    -> fallback / unknown
```

Saving an HA draft is not saving an SD candidate; saving a candidate is not
applying it. Every mutation needs the current paired identity/owner/session,
base operation revision and required candidate/backup digest. A 202 receipt
only acknowledges queuing. After restart verify the loaded source/revision/
digest and renderer readiness before reporting success. On network/HA restart
or missing receipt, reconcile with device status instead of replaying Apply.

Keep the separate pending first-frame/trial and physical SD/power-loss gates;
ordinary FatFs rename is not a power-loss-atomic transaction. Source fallback
does not migrate an incompatible schema. Deployment does not grant household
action permission or solve Native API sender readiness.

## Verification And Next Slice

Run from this repository with the pinned core installed and Python >=3.13:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install '.[http]'
PANEL_CONFIG_HTTP_TEST=1 .venv/bin/python -m unittest discover -s tests -v
```

Native tests in the separate firmware repository compile only a Linux harness for the actual C++ file/HTTP component,
using temporary files and no actuator transport. The opt-in HTTP tests use only
loopback sockets; restricted environments may need permission for that bind.
They do not connect to `192.168.1.45` or Home Assistant. No ESP32 image is built.

Initial client slice acceptance, 2026-11-07: 56 client/native/JSON/file/HTTP regression tests
pass, plus five opt-in real loopback HTTP tests. Tested with Python 3.13.5 and
aiohttp 3.14.5 (installed only under ignored `build/ha-client-deps`). Native
acceptance checks exact active/candidate/backup bytes, shared-validator results,
missing-card behavior, snapshot expiry and unchanged temporary file contents.
HTTP checks cover redirect refusal, known/chunked oversized responses,
compression rejection, bounded timeouts and the injected session lifecycle.
The restricted sandbox's socket bind was retried with loopback permission;
no real panel/HA connection, target memory claim or HA setup acceptance follows.

Metadata extension acceptance, 2026-11-07: the main run has 74 passes and eight
opt-in renderer skips; a rebuilt Linux runtime then passes those eight actual
LVGL tests plus six loopback HTTP cases, for 88 passing targeted tests in total.
This includes C/C++ decoding/geometry/allocation failure checks, unchanged
file publication/export guards and ESPHome C++ generation only (no firmware
compile). The metadata cache is 5012 serialized bytes in the native fixture,
including 153 layout and 17 theme keys; this is not a whole-board RAM delta.
One hundred GETs keep the same cached bytes/counters and create no files.
Factory-ID failure, invalid MAC, restart-stable identity, explicit replacement
rejection, a changed input ceiling and pinned real HTTP requests are covered.
Remaining physical/heap/stack/asset gates are not closed by these host results.

The metadata/identity extension remains host-tested without device deployment.
The companion's setup/status slice now passes 29 tests on real HA 2026.11.0
with its matching official pytest package, including actual loopback HTTP.
Another 31 client/native and six client HTTP checks pass after the client move.
It covers
identity-pinned setup/reconfigure/reauth, duplicate prevention, options reload,
unavailable/stale snapshots, credential redaction, diagnostic entities and
coordinator/session cleanup. See installation and remaining gates (see the firmware/HA repository documentation).
Administrator-authorized read-only JSON import/check is now implemented through
HA's normal WebSocket backend, with real WS role/lifecycle tests and native C++
shared-validator/file-preservation tests. The custom frontend/import display
is the next step. Physical identity, measured limits/asset inventory, the editor, managed
authority/writes, device activation and real-action acceptance remain separate.

Backend acceptance, 2026-11-07: 70 HA 2026.11 integration/WS/HTTP tests plus 37
standalone client/backend/native C++ cases and six standalone HTTP tests pass
(113 targeted checks). The native backend validates unchanged source bytes and
mtime, rejects expired downloads without retry and checks models without SD.
Only temporary Linux files/loopback fixtures are used. See the API notes for
the separate raw pre-auth close-probe limitation; it is not counted as passing
integration acceptance and HA sources/cleanup guards are not patched.

Primary extension references: HA [API libraries](https://contributors.home-assistant.io/core/integrations/api-library/),
[config flows](https://contributors.home-assistant.io/core/integrations/config-flow/)
and [aiohttp client sessions](https://docs.aiohttp.org/en/stable/client_reference.html).
