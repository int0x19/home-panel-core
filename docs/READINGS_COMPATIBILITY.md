# Runtime Readings Capability Profile

Development 0.1.2 accepts the explicit `esp32-readings-preview` target alongside
the unchanged legacy `esp32-action-preview`. Both use `capabilities.v1`, JSON
schema v1 and the same bounded read/check endpoints. Unknown targets still fail
closed. This is not a generic managed/production profile.

The readings target reports action, numeric sensor and binary-status decoding,
plus named/unnamed sensor groups. Its configured unique-source ceiling covers
actions and readings together. Repeated placements share a binding. The
`subscriptions` ceiling equals `entity_bindings`; it counts only runtime-owned
callbacks, not the device's aggregate generated-room/API subscriptions. Limits
are configured, not measured resource acceptance. Inconsistent inventories,
zero/over-budget bindings and nonzero views/attention are rejected.

Only the firmware flash owner uses this general profile. Its validation,
candidate/export and restart loading must all use the same decoder options.
The legacy SD publisher stays action-only; Linux support must not silently
change that contract. Flash remains primary and SD is not required.

Authority stays unmanaged/not enforced. `management_ready`, `deployment_ready`,
production rooms, asset upload and action dispatch remain false. Asset coverage
is still incomplete. Negotiating sensors never grants permission to persist or
activate a draft. The subsequent [candidate Send](CANDIDATE_SEND.md) operation
requires explicit transport opt-in and healthy flash metadata, not managed flags;
HA still exposes no Send/Apply and the core has no Apply method.

Core source acceptance: 50 tests including Node draft cases and loopback HTTP.
Firmware C++/HTTP/NVS and HA consumer acceptance are separate gates. The working
physical panel and published Marketplace 0.1.1 are unchanged by this development
slice. Test/build the pinned 0.1.2 wheel; do not infer support from version alone.

Next: expose guarded candidate Send in HA, then explicit Apply with observed
activation. Base-revision/digest/generation checks remain mandatory; persistent
multi-controller ownership is deferred by the current scope decision.

Consumer checkpoint, 2026-11-17: the wheel from functional source
`5513b8a7737e3ebb08181b2ce02d4266f010e0a0` passes all 50 installed-wheel tests,
213 HA/component-browser tests and 70 scoped firmware C++/HTTP/NVS/LVGL checks
(one optional sanitizer skip). Three ESPHome source-generation checks also
pass without ESP32 compilation. The browser's exact edited JSON traverses fake
NVS/API and renders in Linux without overflow/commands. Next implement the
ownership/base guards; physical acceptance and publication remain pending.
Core/HA 0.1.1 reject the new target: accept the updated companion before any
future readings-profile OTA. Documentation-only commits need not move that pin.
