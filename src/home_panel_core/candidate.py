"""Explicit single-credential candidate Send over the existing flash Upload API."""

import asyncio
from dataclasses import replace

from .json_codec import encode_document
from .protocol import (
    MAX_DOCUMENT_BYTES, UINT32_MAX, CandidateConflict, CandidateSendResult, FileInfo,
    IdentityMismatch, OutcomeUnknown, PanelError, PanelHTTPError, ProtocolError,
    RuntimeSnapshot, Source, TransportError,
)
from .runtime_model.panel_runtime import DEFAULT_LIMITS, decode_document, validate_document


def _ready(snapshot):
    state = snapshot.status
    required = {"capabilities.v1", "flash-maintenance.v1", "write-base.v1", "export.v1"}
    if (state.storage != "flash-nvs" or not required <= state.features or
            state.write_base_sha256 is None or state.flash_write is None):
        raise ProtocolError("Guarded flash candidate upload is unavailable")
    if (not state.storage_ready or state.busy or state.restarting or not state.flash_write.ready):
        raise CandidateConflict("Flash is not idle and writable; inspect status before sending")
    if state.revision >= UINT32_MAX - 1 or int(state.storage_generation) == 2**64 - 1:
        raise CandidateConflict("Configuration counters are exhausted")
    if state.flash_write.high_water_revision < max(info.revision for info in state.files):
        raise ProtocolError("Flash revision metadata is inconsistent")


def _same_import(expected, actual):
    if expected != actual:
        raise CandidateConflict("Imported panel snapshot changed; reload and review the draft")


def _model(data, snapshot):
    caps = snapshot.capabilities
    limits = replace(DEFAULT_LIMITS, **{name: caps.limit(key) for name, key in (
        ("document_bytes", "document_bytes"), ("rooms", "rooms"), ("room_pages", "room_pages"),
        ("widgets", "widgets"), ("views", "views"), ("attention_sources", "attention_sources"),
        ("bindings", "entity_bindings"), ("string_bytes", "string_bytes"), ("depth", "depth"), ("nodes", "nodes"))})
    try:
        document = decode_document(data, limits)
        report = validate_document(document, limits=limits, supported_features=caps.features)
        if encode_document(document) != data:
            raise ValueError
    except ValueError:
        raise ValueError("Candidate must be canonical supported runtime JSON within panel limits") from None
    return report["revision"], report["sha256"]


def _after_candidate_change(before, after, info, high_water_revision):
    state = after.status
    if (state.write_base_sha256 is None or state.write_base_sha256 == before.status.write_base_sha256 or
            before.capabilities != after.capabilities):
        raise ProtocolError("Candidate write-base or capabilities did not match the receipt")
    files = list(before.status.files)
    files[list(Source).index(Source.CANDIDATE)] = info
    predicted = replace(before.status, revision=before.status.revision + 1,
        storage_generation=str(int(before.status.storage_generation) + 1),
        write_base_sha256=state.write_base_sha256, files=tuple(files),
        flash_write=replace(before.status.flash_write, high_water_revision=high_water_revision))
    if state != predicted:
        raise ProtocolError("Storage changed beyond the acknowledged candidate operation")


async def send_candidate(client, data: bytes, expected: RuntimeSnapshot) -> CandidateSendResult:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_DOCUMENT_BYTES:
        raise ValueError("Candidate must be nonempty bounded bytes")
    if not isinstance(expected, RuntimeSnapshot):
        raise ValueError("An imported panel snapshot is required")
    if client._expected_device_id is None or client._expected_device_id != expected.capabilities.device_id:
        raise IdentityMismatch("Candidate Send requires the explicitly paired panel identity")
    _ready(expected)
    revision, sha256 = _model(data, expected)
    info = FileInfo(True, True, 1, 0, len(data), revision, sha256)
    old = expected.status.file(Source.CANDIDATE)
    already_staged = old == info
    if old.present and not already_staged:
        raise CandidateConflict("Discard the existing candidate explicitly before sending another")
    if not already_staged and revision <= expected.status.flash_write.high_water_revision:
        raise CandidateConflict("Candidate revision must exceed the flash high-water revision")
    attempted = False
    try:
        async with asyncio.timeout(client._timeout), client._lock:
            before = await client._snapshot()
            _same_import(expected, before)
            _ready(before)
            if not already_staged:
                attempted = True
                try:
                    _, receipt = await client._job("upload", expected.status, data, raw=True, candidate=True)
                except PanelHTTPError:
                    attempted = False  # Definitive pre-queue refusal; polling failures are OutcomeUnknown.
                    raise
                if receipt["status"] != 200:
                    if receipt["revision"] == before.status.revision and receipt["status"] in {400, 409, 413}:
                        attempted = False
                        raise PanelHTTPError(receipt["status"])
                    raise OutcomeUnknown("Candidate storage result is unverified; inspect status, do not retry")
            after = await client._snapshot()
            if already_staged:
                _same_import(before, after)
            else:
                _after_candidate_change(before, after, info, revision)
            exported = await client._export(Source.CANDIDATE, after.status)
            if exported.data != data:
                raise ProtocolError("Candidate readback differs from sent bytes")
            final = await client._snapshot()
            _same_import(after, final)
            return CandidateSendResult(revision, sha256, len(data), not already_staged, final)
    except TimeoutError:
        if attempted:
            raise OutcomeUnknown("Candidate Send timed out; inspect status, do not retry") from None
        raise TransportError("Candidate verification timed out") from None
    except PanelError:
        if attempted:
            raise OutcomeUnknown("Candidate Send was not verified; inspect status, do not retry") from None
        raise
