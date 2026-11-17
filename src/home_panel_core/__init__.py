"""Shared logical model and bounded configuration client, independent of HA/firmware."""

from pathlib import Path

__version__ = "0.1.2"


def asset_path(name: str) -> Path:
    """Resolve only a known bundled asset, never an arbitrary caller path."""
    if name != "runtime-draft.mjs":
        raise ValueError("Unknown Home Panel core asset")
    return Path(__file__).parent / "assets" / name

from .client import PanelConfigClient
from .protocol import (
    ActivationResult, ActivationState, CandidateApplyReceipt, FlashBootState,
    CandidateConflict, CandidateSendResult, DecoderInventory, ExportedDocument, FileInfo, FlashWriteState, HTTPResponse, IdentityMismatch, OutcomeUnknown, PanelError,
    PanelHTTPError, ProtocolError, RuntimeCapabilities, RuntimeSnapshot, RuntimeStatus, Source, TransportError,
    ValidationResult,
)

__all__ = [
    "PanelConfigClient", "ExportedDocument", "FileInfo", "HTTPResponse",
    "OutcomeUnknown", "PanelError", "PanelHTTPError", "ProtocolError",
    "RuntimeStatus", "Source", "TransportError", "ValidationResult",
    "DecoderInventory", "IdentityMismatch", "RuntimeCapabilities", "RuntimeSnapshot",
    "CandidateConflict", "CandidateSendResult", "FlashWriteState",
    "ActivationResult", "ActivationState", "CandidateApplyReceipt", "FlashBootState",
]
