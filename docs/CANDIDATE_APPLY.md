# Guarded Apply And Activation Inspection

Development 0.1.2 adds two explicit operations, using existing firmware status
and HTTP Apply/export jobs. No new endpoint, boot mechanism, journal, renderer
probe or ESP32 production code is needed. The subsequent HA integration source
now exposes explicit Apply and inspection through its existing administrator/
per-panel gate; see companion `docs/HA_CANDIDATE_APPLY.md`.

## Request

Retain the immutable snapshot verified after Send or candidate import/readback.
Call `apply_candidate(expected=snapshot)` only after explicit user approval.
The client requires a pinned stable device ID, healthy idle writable flash,
valid candidate, existing write-base/export features, `apply_enabled: true`,
stable/confirmed boot phase and counter room for Apply, boot attempt and
confirmation without exhausting the generation counter. Older/incomplete boot
metadata remains readable but cannot authorize Apply.

The transport additionally requires `allow_candidate_apply=True`; Upload's
existing opt-in does not enable Apply, and Apply's opt-in does not enable Upload.
Neither option permits Discard/restore/scan, authority changes or device actions.

Under one existing client lock, reread and compare the full original snapshot,
export the exact candidate, check its SHA/envelope/canonical model against the
negotiated limits, then recheck that same baseline. Submit Apply once with its
original session, operation revision, flash generation, write-base and candidate
SHA. The device's writer still checks them under its own fresh lease.

Verify the final mutation receipt and expected pending-trial/generation/revision
advance while active/backup/loaded fields remain unchanged. Return a
`CandidateApplyReceipt` with candidate revision/SHA and the acknowledged snapshot.
It means **restart scheduled**, not **configuration running**. A response lost
during reboot, evicted receipt, malformed reply or timeout is `OutcomeUnknown`;
definite pre-queue refusals remain HTTP errors. Cancellation propagates normally
and must also be treated as unknown after submission. Never automatically resend.

## Inspect

Call `inspect_activation(expected=the_same_pre_Apply_snapshot)` explicitly as
needed. It performs one bounded inspection, never Apply or any persistent write;
no long-lived polling task, history buffer or mandatory reconnect loop is added.
It also works after a lost Apply response because the caller retains the intent,
not just the acknowledgement. A temporary network failure leaves the result
unknown, not a reason to submit again.

| State | Meaning |
| --- | --- |
| `unchanged` | Original boot/storage snapshot is still visible. A queued request may not have executed; this is not permission to replay. |
| `restarting` | Same boot has the exact expected pending Apply transition. |
| `confirming` | A new boot loaded this exact trial revision, with the expected refs and generation; first frame/healthy settling is not complete. |
| `confirmed` | This boot reached phase `PANEL_FLASH_CONFIRMED`, exact active/candidate/backup transition and generation +3 agree, and active export/readback verifies its SHA. |
| `rolled_back` | The expected unconfirmed trial was discarded on a subsequent boot and original confirmed/builtin refs were retained. This does not certify that fallback UI's current first frame. |
| `unverified` | Inconsistent/newer/unhealthy state or a phase not sufficient to prove this activation. No automatic repair or retry. |

The existing boot owner confirms only the **primary runtime UI of the exact
trial revision** after first presentation and continuous local UI/binding health.
That local contract does not certify online HA, physical touch, complete assets
or household dispatch. A normal later boot may be `STABLE`, even with the same
confirmed active revision; inspection conservatively returns `unverified` then,
because the current status does not prove that later boot's first frame. Mere
TCP reconnect, active file metadata or matching revision is never confirmation.

Recheck identity/capabilities across the boot, exact generation/high-water/file
transitions, healthy uncertainty/warning flags and unchanged dispatch. Unknown
future phases remain readable, not successful. Before returning `confirmed`,
perform active export/header/length/SHA verification and another unchanged
snapshot. Management/deployment flags remain false and are not bypassed here.

## Acceptance Boundary

Core tests cover phase separation, counter/metadata/pairing gates, stale bases,
readback failure, rollback, capability/replacement drift, lost receipts, timeout
and cancellation. Loopback HTTP checks the separate opt-ins and no redirect/
mutation replay. Firmware tests run this installed package against production
C++ HTTP/jobs/NVS/boot lifecycle on Linux; only SDK/ESPHome UI plumbing is fake.
These are not ESP32 compilation, OTA, physical display acceptance or publication.

Consumer checkpoint, 2026-11-17: all 79 installed-wheel/loopback tests and 232
HA component/browser/bundle tests pass from functional source
`ac24832776852116018ad47cdf120685c9d37567`. All 23 wheel package files match
that source. The firmware's scoped flash/NVS/client/legacy-read/decoder suite
runs 116 cases: 114 pass and two optional sanitizer runs skip. Native frame/
health signals are supplied by the host fixture, not a measured physical UI.
The subsequent source-test-only loopback timeout adjustment changes no package
file, wheel, consumer pin or version. At that checkpoint HA enabled only Upload.

The next HA checkpoint passes all 254 HA and 79 installed-core tests, including
explicit Apply confirmation, success/lost reply/rollback, cached-state freshness,
stale tabs, unload/reload, actual WS/HTTP and Chromium. One intent/last observation
is retained, not JSON or a new background controller. Pairing stays read-only;
paired clients opt into Apply separately. No core package change, pin movement,
physical acceptance, OTA or publication is implied by this documentation update.

The configuration contract now covers guarded Discard and backup staging.
Next verify the complete workflow on the panel with the matching HA package.
