# Guarded Candidate Send

Development 0.1.2 adds `PanelConfigClient.send_candidate(data, expected=snapshot)`.
It uses the existing flash Upload job, not a new endpoint, owner journal or
HA state connection. The normal `AiohttpTransport` remains read/check-only;
construct it with `allow_candidate_upload=True` only in a deliberately enabled
writer. The client must be paired with an explicit stable `expected_device_id`.
The HA integration has not enabled this transport option or a Send command yet.

## Preconditions And Result

- Retain the exact `RuntimeSnapshot` associated with the imported draft. Never
  fetch a fresh baseline just to make an older draft writable. Under the shared
  client lock, reread identity/session/capabilities and full status; any mismatch
  with that original snapshot is a `CandidateConflict`.
- Require flash-NVS, write-base/export capabilities, complete healthy writable
  metadata, idle storage, no pending trial/uncertain result, and available
  counters. Older flash/SD metadata stays readable, not Send-ready.
- Validate exact canonical JSON against negotiated features and model/layout/
  byte limits. Do not normalize, assign revisions or generate a newer revision
  automatically. New documents must exceed the flash high-water revision.
- Refuse a different existing candidate; replacement needs a future explicit
  Discard. An identical candidate is only exported and checked, with no Upload.
- Submit once using the original session/operation revision/generation/write-base.
  A pending mutation receipt may show the old or next operation revision; a
  successful final receipt must show the next one. Read jobs keep their original
  revision rule.
- Check generation/revision/high-water advancement and exact candidate metadata.
  All other storage/loaded fields, active and backup must remain unchanged.
  Export the candidate, compare exact bytes and SHA, then recheck status.

`CandidateSendResult` returns document revision/SHA/size, whether a write occurred
and the verified new snapshot. It does not retain another document copy. Send
does not Apply, restart, enable dispatch, create owner records or confirm a
runtime renderer. Management/deployment capability flags remain unchanged.

## Failure Handling

Definite pre-queue HTTP refusals remain `PanelHTTPError`; local stale/different
candidate checks are `CandidateConflict`. A lost/malformed response, evicted
receipt, timeout or mismatched readback after submission is `OutcomeUnknown`.
No request is automatically replayed. Cancellation propagates normally; a caller
that cancels after starting Send must also treat the outcome as unknown, inspect
fresh state and never retry automatically. A fresh explicit import/review is
required before another operation; no automatic snapshot rebinding occurs.

## Acceptance Boundary

Source tests cover stale state, pairing, limits, no-op Send, candidate conflicts,
revision progress, races, lost responses, timeout/cancellation and exact readback.
Loopback HTTP tests verify opt-in/redirect boundaries. The firmware repository
tests this installed package against its production C++ HTTP queue and NVS writer
on Linux, using only fake SDK storage. These checks do not constitute physical
ESP32 acceptance, a firmware change or a published 0.1.2 release.

Next expose Send through HA's existing administrator-only backend/editor, keep
local checkpoint Save distinct, and test stale tabs/unknown results without
Apply. Add Apply and running-model verification in a later focused step.
