"""Guarded flash candidate removal and backup staging."""

import asyncio

from .candidate import _after_candidate_change, _model, _ready, _same_import
from .json_codec import encode_document
from .protocol import (
    UINT32_MAX, CandidateConflict, FileInfo, IdentityMismatch, OutcomeUnknown,
    PanelError, PanelHTTPError, ProtocolError, RuntimeSnapshot, Source, TransportError, json_object,
)


def _check(snapshot: RuntimeSnapshot, source: Source) -> None:
    _ready(snapshot)
    state = snapshot.status
    if int(state.storage_generation) >= 2**64 - 2:
        raise CandidateConflict("Flash generation cannot accommodate maintenance")
    candidate = state.file(Source.CANDIDATE)
    if source is Source.CANDIDATE:
        if not candidate.valid:
            raise CandidateConflict("A valid reviewed candidate is required")
        return
    if "recover-candidate.v1" not in state.features:
        raise ProtocolError("Backup staging is unavailable")
    if candidate.present or not state.file(Source.BACKUP).valid:
        raise CandidateConflict("Recovery requires a valid backup and an empty candidate slot")
    if state.flash_write.high_water_revision >= UINT32_MAX:
        raise CandidateConflict("Document revision counter is exhausted")


def candidate_maintenance_available(snapshot: RuntimeSnapshot, source: Source) -> bool:
    if source not in (Source.CANDIDATE, Source.BACKUP):
        return False
    try:
        _check(snapshot, Source(source))
    except PanelError:
        return False
    return True


async def change_candidate(client, expected: RuntimeSnapshot, source: Source) -> RuntimeSnapshot:
    if not isinstance(expected, RuntimeSnapshot):
        raise ValueError("A reviewed panel snapshot is required")
    if client._expected_device_id is None or client._expected_device_id != expected.capabilities.device_id:
        raise IdentityMismatch("Candidate maintenance requires the explicitly paired panel identity")
    _check(expected, source)
    recovering = source is Source.BACKUP
    operation = "recover" if recovering else "discard"
    attempted = False
    try:
        async with asyncio.timeout(client._timeout), client._lock:
            before = await client._snapshot()
            _same_import(expected, before)
            state = before.status
            high_water = state.flash_write.high_water_revision
            info = FileInfo(False, False, 0, 0, 0, 0, "")
            body = {"revision": state.revision}
            data = None
            if recovering:
                backup = await client._export(Source.BACKUP, state)
                document = json_object(backup.data, state.max_bytes)
                document["revision"] = high_water + 1
                data = encode_document(document)
                revision, sha256 = _model(data, before)
                info = FileInfo(True, True, 1, 0, len(data), revision, sha256)
                high_water = revision
                body["sha256"] = backup.sha256
                _same_import(before, await client._snapshot())
            attempted = True
            try:
                _, receipt = await client._job(operation, state, body, candidate=True)
            except PanelHTTPError:
                attempted = False
                raise
            if receipt["status"] != 200:
                if receipt["revision"] == state.revision and receipt["status"] in {400, 404, 409, 413}:
                    attempted = False
                    raise PanelHTTPError(receipt["status"])
                raise OutcomeUnknown("Candidate maintenance result is unverified")
            after = await client._snapshot()
            _after_candidate_change(before, after, info, high_water)
            if recovering:
                prepared = receipt.get("candidate")
                if (not isinstance(prepared, dict) or type(prepared.get("revision")) is not int or
                        prepared["revision"] != info.revision or prepared.get("sha256") != info.sha256 or
                        prepared.get("storage_generation") != after.status.storage_generation):
                    raise ProtocolError("Recovery receipt does not match the expected candidate")
                exported = await client._export(Source.CANDIDATE, after.status)
                if exported.data != data:
                    raise ProtocolError("Recovered candidate differs from the reviewed backup")
                _same_import(after, await client._snapshot())
            return after
    except TimeoutError:
        if attempted:
            raise OutcomeUnknown("Candidate maintenance timed out; refresh status before proceeding") from None
        raise TransportError("Candidate maintenance preflight timed out") from None
    except PanelError:
        if attempted:
            raise OutcomeUnknown("Candidate maintenance was not verified; refresh status before proceeding") from None
        raise
