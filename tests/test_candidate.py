"""Explicit candidate Send, with immutable caller baseline and no Apply/replay."""

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import unittest

from home_panel_core import (CandidateConflict, IdentityMismatch, OutcomeUnknown, PanelConfigClient,
    PanelHTTPError, ProtocolError, Source, TransportError)
from home_panel_core.json_codec import encode_document
from home_panel_core.protocol import API, RuntimeStatus
from home_panel_core.testing import (DEVICE_ID, DOCUMENT, STATUS, TOKEN, FakeTransport, metadata, response)


class UploadTransport(FakeTransport):
    def __init__(self):
        super().__init__(with_capabilities=True)
        self.state.update(storage="flash-nvs", storage_ready=True, sd_ready=False, storage_generation="8",
            write_base_sha256="a" * 64, writable=True, pending_trial=False, uncertain=False,
            high_water_revision=31, storage_status=0, storage_warnings=0)
        self.state["features"].extend(["flash-maintenance.v1", "write-base.v1"])
        self.state["candidate"] = json.loads(STATUS.read_bytes())["candidate"]
        self.documents.pop(Source.CANDIDATE)
        self.upload_id = None
        self.progress = False

    async def request(self, method, path, *, headers, body, max_bytes):
        suffix = path.removeprefix(API)
        if method == "POST" and suffix == "upload":
            await asyncio.sleep(0)
            self.calls.append((method, path, dict(headers), body, max_bytes))
            assert headers["Authorization"] == "Bearer " + TOKEN
            if (headers["X-Panel-Settings"] != self.state["session_id"] or
                headers["X-Panel-Storage-Generation"] != self.state["storage_generation"] or
                headers["X-Panel-Write-Base"] != self.state["write_base_sha256"] or
                headers["X-Panel-Revision"] != str(self.state["revision"])):
                return response({"error": "Stale baseline"}, status=409)
            self.next_id += 1; self.upload_id = self.next_id
            accepted = {"id": self.upload_id, "done": False, "status": 202, "revision": self.state["revision"],
                        "session_id": self.state["session_id"], "device_id": self.state["device_id"], "error": ""}
            self.documents[Source.CANDIDATE] = body; self.state["candidate"] = metadata(body)
            self.state.update(revision=self.state["revision"] + 1,
                storage_generation=str(int(self.state["storage_generation"]) + 1),
                high_water_revision=json.loads(body)["revision"], write_base_sha256="b" * 64)
            self.jobs[self.upload_id] = dict(accepted, revision=self.state["revision"], done=True, status=200)
            return self.change(method, suffix, response(accepted, status=202))
        if suffix == f"jobs/{self.upload_id}" and self.progress:
            self.progress = False
            self.calls.append((method, path, dict(headers), body, max_bytes))
            return self.change(method, suffix, response(dict(self.jobs[self.upload_id], done=False, status=202)))
        return await super().request(method, path, headers=headers, body=body, max_bytes=max_bytes)


class CandidateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = UploadTransport()
        self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID, poll_interval=0.001)
        self.baseline = await self.client.snapshot()
        document = deepcopy(DOCUMENT); document["revision"] = 40
        self.data = encode_document(document)
        self.fake.calls.clear()

    def uploads(self):
        return [call for call in self.fake.calls if call[0:2] == ("POST", API + "upload")]

    async def test_exact_send_and_same_candidate_noop_never_apply_or_change_loaded_ui(self):
        result = await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertTrue(result.changed)
        self.assertEqual(result.revision, 40); self.assertEqual(result.bytes, len(self.data))
        self.assertEqual(self.fake.documents[Source.CANDIDATE], self.data)
        self.assertEqual((result.snapshot.status.loaded_source, result.snapshot.status.loaded_revision),
                         (self.baseline.status.loaded_source, self.baseline.status.loaded_revision))
        for source in (Source.ACTIVE, Source.BACKUP):
            self.assertEqual(result.snapshot.status.file(source), self.baseline.status.file(source))
        upload = self.uploads()[0]
        self.assertEqual(upload[2]["X-Panel-Write-Base"], self.baseline.status.write_base_sha256)
        self.assertEqual(upload[2]["X-Panel-Storage-Generation"], "8")
        self.assertEqual(upload[2]["X-Panel-Revision"], str(self.baseline.status.revision))
        self.assertEqual(upload[3], self.data)
        again = await self.client.send_candidate(self.data, expected=result.snapshot)
        self.assertFalse(again.changed); self.assertEqual(again.snapshot, result.snapshot)
        self.assertEqual(len(self.uploads()), 1)
        self.assertTrue(all(path in {API + "upload", API + "export"} for method, path, *_ in self.fake.calls if method == "POST"))
        self.assertFalse(result.snapshot.capabilities.management_ready)
        self.assertNotIn(TOKEN, repr(result))

    async def test_stale_snapshot_is_not_rebound_to_fresh_generation_or_base(self):
        for field, value in (("write_base_sha256", "c" * 64), ("storage_generation", "9"),
                             ("revision", 2), ("loaded_revision", 18), ("session_id", "2" * 32)):
            old = self.fake.state[field]; self.fake.state[field] = value
            if field == "session_id": self.fake.state["csrf"] = value
            with self.subTest(field=field), self.assertRaises(CandidateConflict):
                await self.client.send_candidate(self.data, expected=self.baseline)
            self.fake.state[field] = old
            if field == "session_id": self.fake.state["csrf"] = old
        self.assertFalse(self.uploads())
        self.fake.state["device_id"] = "esp32-efuse-020000000046"
        with self.assertRaises(IdentityMismatch): await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertFalse(self.uploads())

    async def test_pairing_complete_flash_metadata_and_health_are_required(self):
        unpaired = PanelConfigClient(self.fake, TOKEN)
        with self.assertRaises(IdentityMismatch): await unpaired.send_candidate(self.data, expected=self.baseline)
        self.assertFalse(self.fake.calls)
        for field, value in (("writable", False), ("pending_trial", True), ("uncertain", True),
                             ("storage_status", 14), ("storage_warnings", 1)):
            raw = deepcopy(self.fake.state); raw[field] = value
            expected = replace(self.baseline, status=RuntimeStatus.parse(raw))
            with self.subTest(field=field), self.assertRaises(CandidateConflict):
                await self.client.send_candidate(self.data, expected=expected)
        for missing in ("writable", "high_water_revision", "uncertain"):
            raw = deepcopy(self.fake.state); del raw[missing]
            expected = replace(self.baseline, status=RuntimeStatus.parse(raw))
            with self.subTest(missing=missing), self.assertRaises(ProtocolError):
                await self.client.send_candidate(self.data, expected=expected)
        for change in ({"write_base_sha256": None}, {"storage_generation": str(2**64 - 1)}):
            raw = {**self.fake.state, **change}; expected = replace(self.baseline, status=RuntimeStatus.parse(raw))
            with self.assertRaises((ProtocolError, CandidateConflict)): await self.client.send_candidate(self.data, expected=expected)
        self.assertFalse(self.fake.calls)

    async def test_candidate_and_high_water_require_explicit_review_not_overwrite(self):
        for revision in (30, 31):
            document = json.loads(self.data); document["revision"] = revision
            with self.assertRaises(CandidateConflict):
                await self.client.send_candidate(encode_document(document), expected=self.baseline)
        old = encode_document({**json.loads(self.data), "revision": 35})
        self.fake.documents[Source.CANDIDATE] = old; self.fake.state["candidate"] = metadata(old)
        self.fake.state["high_water_revision"] = 35
        expected = await self.client.snapshot()
        with self.assertRaises(CandidateConflict): await self.client.send_candidate(self.data, expected=expected)
        self.assertFalse(self.uploads())

    async def test_canonical_model_limits_and_features_fail_before_http(self):
        invalid = [b"", b"broken", b"x" * 65537, b"\xff", self.data + b" ", self.data.decode(),
                   self.data.replace(b'"revision":40', b'"revision":40,"revision":40')]
        model = json.loads(self.data); model["requires"].append("widget.light"); invalid.append(encode_document(model))
        model = json.loads(self.data); model["rooms"][0]["name"] = "x" * 300; invalid.append(encode_document(model))
        for data in invalid:
            with self.subTest(data=str(data)[:40]), self.assertRaises(ValueError) as error:
                await self.client.send_candidate(data, expected=self.baseline)
            self.assertNotIn(TOKEN, str(error.exception))
        self.assertFalse(self.fake.calls)

    async def test_progress_can_publish_new_revision_before_done(self):
        self.fake.progress = True
        self.assertTrue((await self.client.send_candidate(self.data, expected=self.baseline)).changed)
        self.assertEqual(len(self.uploads()), 1)

    async def test_prequeue_conflict_is_definitive_and_not_retried(self):
        def race(method, path, result):
            if path == "capabilities": self.fake.state["write_base_sha256"] = "c" * 64
            return result
        self.fake.change = race
        with self.assertRaises(PanelHTTPError) as error: await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.uploads()), 1); self.assertNotIn(Source.CANDIDATE, self.fake.documents)

    async def test_lost_or_malformed_acceptance_and_receipts_are_unknown_without_replay(self):
        for stage, field, value in (("upload", "id", True), ("upload", "session_id", "0" * 32),
                ("jobs/1", "revision", 1), ("jobs/1", "revision", 99), ("jobs/1", "session_id", "0" * 32),
                ("jobs/1", "status", 503)):
            self.fake = UploadTransport(); self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID)
            self.baseline = await self.client.snapshot()
            def corrupt(method, path, result):
                if path == stage:
                    body = json.loads(result.body); body[field] = value
                    return response(body, status=result.status)
                return result
            self.fake.change = corrupt
            with self.subTest(stage=stage, field=field), self.assertRaises(OutcomeUnknown):
                await self.client.send_candidate(self.data, expected=self.baseline)
            self.assertEqual(len(self.uploads()), 1)
        def lost(method, path, result):
            if path == "upload": raise TransportError("Lost reply")
            return result
        self.fake = UploadTransport(); self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID)
        self.baseline = await self.client.snapshot(); self.fake.change = lost
        with self.assertRaises(OutcomeUnknown): await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertEqual(len(self.uploads()), 1)

    async def test_receipt_eviction_and_verification_errors_never_become_another_upload(self):
        for stage in ("jobs/1", "downloads/2", "after_status"):
            self.fake = UploadTransport(); self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID)
            self.baseline = await self.client.snapshot()
            def fail(method, path, result):
                if path == stage: return response({"error": TOKEN}, status=404)
                if stage == "after_status" and path == "status" and self.fake.upload_id:
                    body = json.loads(result.body); body["loaded_revision"] += 1; return response(body)
                return result
            self.fake.change = fail
            with self.subTest(stage=stage), self.assertRaises(OutcomeUnknown):
                await self.client.send_candidate(self.data, expected=self.baseline)
            self.assertEqual(len(self.uploads()), 1)

    async def test_complete_flash_write_fields_are_strictly_typed(self):
        for key, value in (("writable", 1), ("uncertain", None), ("pending_trial", "false"),
                           ("high_water_revision", True), ("storage_status", -1), ("storage_warnings", 2**32)):
            with self.subTest(key=key), self.assertRaises(ProtocolError):
                RuntimeStatus.parse({**self.fake.state, key: value})

    async def test_poll_timeout_and_post_cancellation_do_not_repeat_mutations(self):
        self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID,
                                        poll_interval=0.001, max_polls=2)
        self.fake.change = lambda m, p, r: response(dict(json.loads(r.body), done=False, status=202)) if p == "jobs/1" else r
        with self.assertRaises(OutcomeUnknown): await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertEqual(len(self.uploads()), 1)
        self.fake = UploadTransport()
        committed = asyncio.Event()
        original = self.fake.request
        async def block(method, path, **fields):
            result = await original(method, path, **fields)
            if path == API + "upload":
                committed.set(); await asyncio.Event().wait()
            return result
        self.fake.request = block
        self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID)
        self.baseline = await self.client.snapshot()
        task = asyncio.create_task(self.client.send_candidate(self.data, expected=self.baseline))
        await committed.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(len(self.uploads()), 1)
        self.assertEqual(self.fake.documents[Source.CANDIDATE], self.data)

    async def test_failed_final_readback_is_not_acknowledged_as_sent(self):
        def corrupt(method, suffix, result):
            if suffix == "downloads/2":
                return type(result)(result.status, result.headers, result.body[:-1] + b" ")
            return result
        self.fake.change = corrupt
        with self.assertRaises(OutcomeUnknown): await self.client.send_candidate(self.data, expected=self.baseline)
        self.assertEqual(len(self.uploads()), 1)
