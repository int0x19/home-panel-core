"""Explicit guarded Apply and bounded inspection of existing flash trial metadata."""

import asyncio
from dataclasses import replace

from .candidate import _model, _ready, _same_import
from .protocol import (
    ActivationResult, ActivationState, CandidateApplyReceipt, CandidateConflict,
    FileInfo, IdentityMismatch, OutcomeUnknown, PanelError, PanelHTTPError,
    ProtocolError, RuntimeSnapshot, Source, TransportError,
)

# Existing PanelNvsBoot phases; unknown future phases are readable, never success.
STABLE, WAIT_FRAME, SETTLING, CONFIRMED = 1, 2, 3, 4
MISSING = FileInfo(False, False, 0, 0, 0, 0, "")


def _target(client, expected):
    if not isinstance(expected, RuntimeSnapshot):
        raise ValueError("A verified pre-Apply snapshot is required")
    if client._expected_device_id is None or client._expected_device_id != expected.capabilities.device_id:
        raise IdentityMismatch("Apply requires an explicitly paired panel identity")
    _ready(expected)
    boot = expected.status.flash_boot
    if boot is None:
        raise ProtocolError("Flash trial metadata is unavailable")
    if not boot.apply_enabled or boot.phase not in {STABLE, CONFIRMED}:
        raise CandidateConflict("Flash trials are disabled or the boot is not stable")
    if int(expected.status.storage_generation) > 2**64 - 5:
        raise CandidateConflict("Flash generation cannot complete a healthy confirmed trial")
    target = expected.status.file(Source.CANDIDATE)
    if not target.valid:
        raise CandidateConflict("A validated saved candidate is required")
    return target


def _after_apply(before, after):
    state = after.status
    if (before.capabilities != after.capabilities or state.write_base_sha256 is None or
            state.write_base_sha256 == before.status.write_base_sha256):
        raise ProtocolError("Apply receipt base or capabilities changed unexpectedly")
    predicted = replace(before.status, revision=before.status.revision + 1,
        storage_generation=str(int(before.status.storage_generation) + 1),
        write_base_sha256=state.write_base_sha256, restarting=True,
        flash_write=replace(before.status.flash_write, writable=False, pending_trial=True))
    if state != predicted:
        raise ProtocolError("Apply changed more than the expected pending trial")


async def apply_candidate(client, expected):
    target = _target(client, expected)
    attempted = False
    try:
        async with asyncio.timeout(client._timeout), client._lock:
            before = await client._snapshot()
            _same_import(expected, before)
            # Readback is a read job; keep its revision rule and original base.
            exported = await client._export(Source.CANDIDATE, before.status)
            _model(exported.data, before)
            _same_import(before, await client._snapshot())
            attempted = True
            try:
                _, receipt = await client._job("apply", before.status,
                    {"revision": before.status.revision, "sha256": target.sha256}, candidate=True)
            except PanelHTTPError:
                attempted = False
                raise
            if receipt["status"] != 200:
                if receipt["revision"] == before.status.revision and receipt["status"] in {400, 409, 413}:
                    attempted = False
                    raise PanelHTTPError(receipt["status"])
                raise OutcomeUnknown("Apply result is unverified; inspect activation, do not retry")
            after = await client._snapshot()
            _after_apply(before, after)
            return CandidateApplyReceipt(target.revision, target.sha256, after)
    except TimeoutError:
        if attempted:
            raise OutcomeUnknown("Apply timed out; inspect activation, do not retry") from None
        raise TransportError("Apply preflight timed out") from None
    except PanelError:
        if attempted:
            raise OutcomeUnknown("Apply was not acknowledged; inspect activation, do not retry") from None
        raise


def _classify(before, after, target):
    state, original = after.status, before.status
    if replace(after.capabilities, session_id=before.capabilities.session_id) != before.capabilities:
        raise ProtocolError("Panel capabilities changed across activation")
    if state.session_id == original.session_id:
        if after == before:
            return ActivationState.UNCHANGED
        try:
            _after_apply(before, after)
        except ProtocolError:
            return ActivationState.UNVERIFIED
        return ActivationState.RESTARTING
    write, boot = state.flash_write, state.flash_boot
    if (state.storage != "flash-nvs" or not state.storage_ready or state.busy or state.restarting or
            write is None or boot is None or boot.apply_enabled != original.flash_boot.apply_enabled or
            state.features != original.features or write.uncertain or write.storage_status or write.storage_warnings or
            write.high_water_revision != original.flash_write.high_water_revision or
            state.write_base_sha256 is None or state.write_base_sha256 == original.write_base_sha256 or
            state.dispatch_enabled != original.dispatch_enabled or state.files[3] != original.files[3]):
        return ActivationState.UNVERIFIED
    generation = int(state.storage_generation) - int(original.storage_generation)
    if state.loaded_source == "flash-trial" and state.loaded_revision == target.revision:
        if (boot.phase in {WAIT_FRAME, SETTLING} and generation == 2 and write.pending_trial and
                not write.writable and state.files == original.files):
            return ActivationState.CONFIRMING
        if (boot.phase == CONFIRMED and generation == 3 and write.ready and
                state.files[:3] == (target, MISSING, original.file(Source.ACTIVE))):
            return ActivationState.CONFIRMED
    fallback = original.file(Source.ACTIVE)
    source = "flash-confirmed" if fallback.valid else "builtin"
    revision = fallback.revision if fallback.valid else original.loaded_revision
    if (boot.phase == STABLE and generation == 3 and write.ready and
            state.files[:3] == (fallback, MISSING, original.file(Source.BACKUP)) and
            state.loaded_source == source and state.loaded_revision == revision):
        return ActivationState.ROLLED_BACK
    return ActivationState.UNVERIFIED


async def inspect_activation(client, expected):
    target = _target(client, expected)
    try:
        async with asyncio.timeout(client._timeout), client._lock:
            after = await client._snapshot()
            state = _classify(expected, after, target)
            if state == ActivationState.CONFIRMED:
                # Success additionally requires exact active export/header/SHA verification.
                await client._export(Source.ACTIVE, after.status)
                _same_import(after, await client._snapshot())
            return ActivationResult(state, after)
    except TimeoutError:
        raise TransportError("Activation inspection timed out") from None
