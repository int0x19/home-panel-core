"""Protocol/client regression against installed core, no firmware checkout."""

import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

from home_panel_core import (HTTPResponse, IdentityMismatch, OutcomeUnknown, PanelConfigClient, PanelHTTPError, ProtocolError, RuntimeCapabilities, RuntimeStatus, Source, TransportError)
from home_panel_core.protocol import API, json_object
from home_panel_core.json_codec import encode_document
from home_panel_core.testing import DEVICE_ID, TOKEN, STATUS, DOCUMENT, PILOT_FEATURES, FakeTransport, capability_document, response, metadata

class ProtocolTests(unittest.TestCase):
    def test_current_profile_does_not_invent_management_capabilities(self):
        value = json.loads(STATUS.read_bytes())
        parsed = RuntimeStatus.parse(value)
        self.assertIsNone(parsed.device_id)
        self.assertFalse(parsed.management_ready)
        self.assertEqual(parsed.authority, "unreported")
        self.assertEqual(parsed.max_bytes, 16384)
        value["revision"] = 99
        self.assertEqual(parsed.revision, 1)
        with self.assertRaises(FrozenInstanceError): parsed.revision = 2
        self.assertNotIn(parsed.session_id, repr(parsed))

    def test_rejects_bad_status_types_versions_and_limits(self):
        for key, value in (("version", True), ("version", 2), ("revision", True),
                ("revision", -1), ("max_bytes", 65537), ("max_bytes", 0), ("sd_ready", 1),
                ("session_id", "bad"), ("csrf", "0" * 32), ("features", ["export.v1"] * 2),
                ("features", [False]), ("features", "export.v1"), ("export_lifetime_ms", 0),
                ("loaded_source", "unknown"), ("loaded_source", [])):
            with self.subTest(key=key, value=value), self.assertRaises(ProtocolError):
                state = json.loads(STATUS.read_bytes()); state[key] = value
                RuntimeStatus.parse(state)

    def test_invalid_files_can_be_reported_but_valid_metadata_must_be_consistent(self):
        state = json.loads(STATUS.read_bytes())
        state["active"].update(present=True, bytes=2**32, status=4)
        self.assertFalse(RuntimeStatus.parse(state).file(Source.ACTIVE).valid)
        state["active"]["valid"] = True
        with self.assertRaises(ProtocolError): RuntimeStatus.parse(state)

    def test_json_framing_rejects_duplicates_nesting_unicode_nonfinite_and_oversize(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b'{"x":"\\ud800"}',
                     b'[]', b'{"x":' + b'[' * 20 + b'0' + b']' * 20 + b'}', b'x' * 16385):
                with self.subTest(data=data[:20]), self.assertRaises(ProtocolError): json_object(data)

    def test_device_id_is_only_accepted_with_negotiated_feature(self):
        state = json.loads(STATUS.read_bytes()); state["device_id"] = DEVICE_ID
        self.assertIsNone(RuntimeStatus.parse(state).device_id)
        state["features"].append("capabilities.v1")
        self.assertEqual(RuntimeStatus.parse(state).device_id, DEVICE_ID)
        for value in ("", "1.2.3.4", "esp32-efuse-000000000000", "esp32-efuse-ff0000000045", "esp32-efuse-02000000004A"):
            state["device_id"] = value
            with self.subTest(value=value), self.assertRaises(ProtocolError): RuntimeStatus.parse(state)
        state["device_id"] = None
        self.assertIsNone(RuntimeStatus.parse(state).device_id)

    def test_capability_profile_is_bounded_immutable_and_never_arms_writes(self):
        state = FakeTransport(with_capabilities=True).state
        raw = capability_document(state)
        parsed = RuntimeCapabilities.parse(raw)
        self.assertEqual(parsed.device_id, DEVICE_ID)
        self.assertEqual(parsed.features, PILOT_FEATURES)
        self.assertEqual(parsed.limit("widgets"), 12)
        self.assertFalse(parsed.management_ready or parsed.deployment_ready or parsed.limits_measured_on_device)
        self.assertFalse(parsed.assets_inventory_complete)
        self.assertEqual(parsed.authority, "unmanaged")
        raw["validation"]["layout_keys"].clear()
        self.assertTrue(parsed.validation.layout_keys)
        self.assertNotIn(parsed.session_id, repr(parsed))

    def test_capabilities_reject_unknown_profile_or_enabled_management(self):
        source = capability_document(FakeTransport(with_capabilities=True).state)
        for key, value in (("metadata_version", 2), ("protocol_version", True), ("target", "host-contract"),
                           ("identity_source", "ip"), ("schema_versions", [True]), ("schema_versions", [1, 1]),
                           ("management_ready", True), ("deployment_ready", True), ("limits", {})):
            raw = deepcopy(source); raw[key] = value
            with self.subTest(key=key), self.assertRaises(ProtocolError): RuntimeCapabilities.parse(raw)
        for section, key, value in (("authority", "enforced", True), ("runtime", "dispatch_enabled", True),
                                    ("assets", "upload", True), ("validation", "layout_keys", ["x"] * 300)):
            raw = deepcopy(source); raw[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ProtocolError): RuntimeCapabilities.parse(raw)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.client = PanelConfigClient(self.transport, TOKEN, poll_interval=0.001)

    async def test_status_and_all_exact_sources_do_not_write_configuration(self):
        before = deepcopy(self.transport.state)
        self.assertEqual((await self.client.status()).loaded_source, "builtin")
        for source in Source:
            result = await self.client.export(source)
            self.assertEqual(result.data, self.transport.documents[source])
            self.assertEqual(result.sha256, hashlib.sha256(result.data).hexdigest())
            self.assertEqual(result.revision, self.transport.state[source]["revision"])
        self.assertEqual(before, self.transport.state)
        self.assertNotIn(TOKEN, repr(self.client))
        self.assertTrue(all(path in {API + "export", API + "validate"}
            for method, path, *_ in self.transport.calls if method == "POST"))
        for name in ("upload", "apply", "restore", "discard", "scan"):
            self.assertFalse(hasattr(self.client, name))

    async def test_validate_returns_shared_report_and_works_without_sd(self):
        self.transport.state["sd_ready"] = False
        result = await self.client.validate(self.transport.documents[Source.ACTIVE])
        self.assertTrue(result.valid); self.assertEqual(result.document_revision, 31)
        result = await self.client.validate(b"broken")
        self.assertFalse(result.valid); self.assertEqual(result.status, 400)
        with self.assertRaises(ValueError): await self.client.validate(b"x" * 16385)
        self.assertEqual(sum(method == "POST" for method, *_ in self.transport.calls), 2)

    async def test_missing_features_busy_and_missing_source_never_submit(self):
        for key, value, expected in (("features", [], ProtocolError), ("busy", True, PanelHTTPError),
                                     ("restarting", True, PanelHTTPError), ("sd_ready", False, PanelHTTPError)):
            with self.subTest(key=key):
                old = self.transport.state[key]; self.transport.state[key] = value
                with self.assertRaises(expected): await self.client.export()
                self.transport.state[key] = old
        self.transport.state["active"] = json.loads(STATUS.read_bytes())["active"]
        with self.assertRaises(PanelHTTPError) as error: await self.client.export()
        self.assertEqual(error.exception.status, 404)
        self.assertFalse(any(method == "POST" for method, *_ in self.transport.calls))
        with self.assertRaises(ValueError): await self.client.export("temporary")

    async def test_old_v1_status_without_export_features_remains_read_only(self):
        self.transport.state.pop("features")
        self.transport.state.pop("export_lifetime_ms")
        self.transport.state["device_id"] = "unreviewed-extension"
        self.transport.state["management_ready"] = True
        state = await self.client.status()
        self.assertFalse(state.features)
        self.assertIsNone(state.device_id)
        self.assertFalse(state.management_ready)
        with self.assertRaises(ProtocolError): await self.client.export()
        with self.assertRaises(ProtocolError): await self.client.validate(b"broken")
        self.assertFalse(any(method == "POST" for method, *_ in self.transport.calls))

    async def test_acceptance_and_receipt_identity_guards(self):
        for stage, field, value in (("export", "id", True), ("export", "session_id", "0" * 32),
                ("export", "revision", 2), ("jobs/1", "id", 2), ("jobs/1", "revision", 2),
                ("jobs/1", "session_id", "0" * 32), ("jobs/1", "download", "https://other.invalid/token"),
                ("jobs/1", "source", "backup"), ("jobs/1", "sha256", "0" * 64), ("jobs/1", "bytes", True)):
            with self.subTest(stage=stage, field=field):
                fake = FakeTransport()
                def change(_method, suffix, result):
                    if suffix == stage:
                        obj = json.loads(result.body); obj[field] = value
                        return response(obj, status=result.status)
                    return result
                fake.change = change
                with self.assertRaises(ProtocolError): await PanelConfigClient(fake, TOKEN).export()
                self.assertFalse(any("downloads/" in path for _, path, *_ in fake.calls))

    async def test_download_digest_size_source_session_and_duplicate_header_guards(self):
        def replace_header(result, key, value):
            return HTTPResponse(result.status, tuple((k, value if k == key else v) for k, v in result.headers), result.body)
        transforms = [
            lambda r: HTTPResponse(200, r.headers, r.body[:-1] + b" "),
            lambda r: replace_header(r, "Content-Length", "1"),
            lambda r: replace_header(r, "X-Panel-Session", "0" * 32),
            lambda r: replace_header(r, "X-Panel-SHA256", "0" * 64),
            lambda r: replace_header(r, "Content-Disposition", "attachment; filename=panel-backup.json"),
            lambda r: HTTPResponse(200, (*r.headers, ("x-panel-sha256", "0" * 64)), r.body),
            lambda r: HTTPResponse(200, (*r.headers, ("Content-Encoding", "gzip")), r.body),
        ]
        for transform in transforms:
            with self.subTest(transform=transform):
                fake = FakeTransport()
                fake.change = lambda _m, p, r: transform(r) if p.startswith("downloads/") else r
                with self.assertRaises(ProtocolError): await PanelConfigClient(fake, TOKEN).export()

    async def test_http_errors_are_typed_redacted_and_never_retried(self):
        for status in (301, 401, 403, 404, 409, 410, 429, 503):
            with self.subTest(status=status):
                fake = FakeTransport()
                fake.change = lambda *_: response({"error": TOKEN}, status=status)
                with self.assertRaises(PanelHTTPError) as error: await PanelConfigClient(fake, TOKEN).export()
                self.assertEqual(error.exception.status, status)
                self.assertNotIn(TOKEN, str(error.exception))
                self.assertEqual(len(fake.calls), 1)

    async def test_job_eviction_and_expired_download_are_not_retried(self):
        for prefix, status in (("jobs/", 404), ("downloads/", 410)):
            fake = FakeTransport()
            fake.change = lambda m, p, r: response({"error": TOKEN}, status=status) if p.startswith(prefix) else r
            with self.assertRaises(PanelHTTPError) as error: await PanelConfigClient(fake, TOKEN).export()
            self.assertEqual(error.exception.status, status)
            self.assertEqual(sum(method == "POST" for method, *_ in fake.calls), 1)

    async def test_validation_report_consistency_and_memory_failure(self):
        for code, report_status, error_type in ((200, 1, ProtocolError), (400, 0, ProtocolError),
                                               (503, 9, PanelHTTPError)):
            fake = FakeTransport()
            def change(method, suffix, result):
                if suffix.startswith("jobs/"):
                    value = json.loads(result.body)
                    value["status"] = code
                    value["validation"]["status"] = report_status
                    return response(value)
                return result
            fake.change = change
            with self.assertRaises(error_type): await PanelConfigClient(fake, TOKEN).validate(b"broken")

    async def test_actual_payload_envelope_is_checked_even_with_matching_hash(self):
        for key, value in (("format", "other"), ("schema_version", True), ("schema_version", 2)):
            fake = FakeTransport()
            doc = json.loads(fake.documents[Source.ACTIVE]); doc[key] = value
            fake.documents[Source.ACTIVE] = encode_document(doc)
            fake.state["active"] = metadata(fake.documents[Source.ACTIVE])
            with self.assertRaises(ProtocolError): await PanelConfigClient(fake, TOKEN).export()

    async def test_post_transport_loss_and_pending_timeout_do_not_resubmit(self):
        def lost(method, _path, result):
            if method == "POST": raise TransportError("Transport unavailable")
            return result
        self.transport.change = lost
        with self.assertRaises(OutcomeUnknown): await self.client.export()
        self.assertEqual(sum(m == "POST" for m, *_ in self.transport.calls), 1)
        self.transport = FakeTransport()
        self.transport.change = lambda m, p, r: response(dict(json.loads(r.body), done=False, status=202)) if p.startswith("jobs/") else r
        client = PanelConfigClient(self.transport, TOKEN, poll_interval=0.001, max_polls=2)
        with self.assertRaises(OutcomeUnknown): await client.export()
        self.assertEqual(sum(m == "POST" for m, *_ in self.transport.calls), 1)

    async def test_overall_timeout_and_cancellation_never_retry(self):
        class Slow(FakeTransport):
            async def request(self, *args, **kwargs):
                await asyncio.sleep(1)
                return await super().request(*args, **kwargs)
        with self.assertRaises(TransportError):
            await PanelConfigClient(Slow(), TOKEN, operation_timeout=0.005).status()
        task = asyncio.create_task(PanelConfigClient(Slow(), TOKEN).export())
        await asyncio.sleep(0); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_waiting_for_client_lock_is_bounded_and_poll_loss_is_unknown(self):
        client = PanelConfigClient(self.transport, TOKEN, operation_timeout=0.005)
        await client._lock.acquire()
        try:
            with self.assertRaises(TransportError): await client.status()
        finally:
            client._lock.release()
        self.assertEqual(self.transport.calls, [])
        def lost(method, path, result):
            if path.startswith("jobs/"): raise TransportError("Connection lost")
            return result
        self.transport.change = lost
        with self.assertRaises(OutcomeUnknown): await self.client.export()
        self.assertEqual(sum(m == "POST" for m, *_ in self.transport.calls), 1)

    async def test_one_client_serializes_complete_operations(self):
        await asyncio.gather(self.client.export(), self.client.export(Source.BACKUP), self.client.validate(b"broken"))
        paths = [p.removeprefix(API) for _, p, *_ in self.transport.calls]
        self.assertEqual(paths, ["status", "export", "jobs/1", "downloads/1",
            "status", "export", "jobs/2", "downloads/2", "status", "validate", "jobs/3"])

    async def test_negotiated_metadata_and_explicit_identity_pin(self):
        fake = FakeTransport(with_capabilities=True)
        client = PanelConfigClient(fake, TOKEN, expected_device_id=DEVICE_ID)
        caps = await client.capabilities()
        self.assertEqual(caps.device_id, DEVICE_ID)
        self.assertEqual((await client.export()).revision, 31)
        self.assertTrue((await client.validate(fake.documents[Source.ACTIVE])).valid)
        fake.state["session_id"] = fake.state["csrf"] = "2" * 32
        self.assertEqual((await client.capabilities()).device_id, DEVICE_ID)
        fake.state["device_id"] = "esp32-efuse-020000000046"
        before = len(fake.calls)
        for operation in (client.status, client.capabilities, client.export):
            with self.assertRaises(IdentityMismatch): await operation()
        self.assertEqual([method for method, *_ in fake.calls[before:]], ["GET", "GET", "GET"])

    async def test_metadata_session_id_byte_limit_and_receipt_id_guards(self):
        for key, value in (("device_id", "esp32-efuse-020000000046"), ("session_id", "2" * 32),
                           ("limits", {**capability_document(FakeTransport(with_capabilities=True).state)["limits"],
                                       "document_bytes": 8192})):
            fake = FakeTransport(with_capabilities=True)
            def change(_method, suffix, result):
                if suffix == "capabilities":
                    data = json.loads(result.body); data[key] = value
                    return response(data)
                return result
            fake.change = change
            with self.subTest(key=key), self.assertRaises(ProtocolError): await PanelConfigClient(fake, TOKEN).capabilities()
        for stage in ("export", "jobs/1"):
            fake = FakeTransport(with_capabilities=True)
            def change(method, suffix, result):
                if suffix == stage:
                    data = json.loads(result.body); data["device_id"] = "esp32-efuse-020000000046"
                    return response(data, status=result.status)
                return result
            fake.change = change
            with self.subTest(stage=stage), self.assertRaises(ProtocolError): await PanelConfigClient(fake, TOKEN).export()

    async def test_pinning_old_firmware_or_unavailable_identity_fails_without_post(self):
        for fake in (FakeTransport(), FakeTransport(with_capabilities=True)):
            fake.state.pop("device_id", None)
            client = PanelConfigClient(fake, TOKEN, expected_device_id=DEVICE_ID)
            with self.assertRaises(IdentityMismatch): await client.export()
            self.assertFalse(any(m == "POST" for m, *_ in fake.calls))
        with self.assertRaises(ProtocolError): await self.client.capabilities()


if __name__ == "__main__": unittest.main()
