"""Apply is explicit; receipts, reboot, first frame and confirmation are distinct."""

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import unittest

from home_panel_core import (ActivationState, CandidateConflict, IdentityMismatch, OutcomeUnknown,
    PanelConfigClient, PanelHTTPError, ProtocolError, RuntimeStatus, Source, TransportError)
from home_panel_core.json_codec import encode_document
from home_panel_core.protocol import API
from home_panel_core.testing import DEVICE_ID, DOCUMENT, TOKEN, metadata, response
from test_candidate import UploadTransport


class ApplyTransport(UploadTransport):
    def __init__(self):
        super().__init__()
        self.state.update(apply_enabled=True, boot_phase=1)
        self.target = encode_document({**deepcopy(DOCUMENT), "revision":40})
        self.documents["candidate"] = self.target
        self.state["candidate"] = metadata(self.target)
        self.state["high_water_revision"] = 40
        self.original = deepcopy(self.state)
        self.original_documents = deepcopy(self.documents)

    async def request(self, method, path, *, headers, body, max_bytes):
        if (method, path) != ("POST", API + "apply"):
            return await super().request(method, path, headers=headers, body=body, max_bytes=max_bytes)
        self.calls.append((method, path, dict(headers), body, max_bytes))
        envelope = json.loads(body)
        if (headers["X-Panel-Write-Base"] != self.state["write_base_sha256"] or
                headers["X-Panel-Storage-Generation"] != self.state["storage_generation"] or
                headers["X-Panel-Settings"] != self.state["session_id"] or
                envelope != {"revision":self.state["revision"], "sha256":self.state["candidate"]["sha256"]}):
            return response({}, status=409)
        self.next_id += 1
        accepted = {"id":self.next_id, "done":False, "status":202, "error":"",
            "revision":self.state["revision"], "session_id":self.state["session_id"], "device_id":DEVICE_ID}
        self.state.update(revision=self.state["revision"] + 1, pending_trial=True,
            writable=False, restarting=True, storage_generation=str(int(self.state["storage_generation"]) + 1),
            write_base_sha256="b" * 64)
        self.jobs[self.next_id] = dict(accepted, revision=self.state["revision"], done=True, status=200)
        return self.change(method, "apply", response(accepted, status=202))

    def reboot(self):
        self.state.update(session_id="2" * 32, csrf="2" * 32, revision=1, boot_phase=2,
            restarting=False, storage_generation=str(int(self.original["storage_generation"]) + 2),
            loaded_source="flash-trial", loaded_revision=40, write_base_sha256="c" * 64)
        self.jobs.clear(); self.next_id = 0

    def confirm(self):
        self.state.update(boot_phase=4, writable=True, pending_trial=False,
            storage_generation=str(int(self.original["storage_generation"]) + 3), write_base_sha256="d" * 64)
        self.state["backup"] = deepcopy(self.original["active"])
        self.documents["backup"] = self.original_documents["active"]
        self.state["active"] = deepcopy(self.state["candidate"])
        self.documents["active"] = self.documents.pop("candidate")
        self.state["candidate"] = deepcopy(self.state["temporary"])

    def rollback(self):
        self.state.update(session_id="3" * 32, csrf="3" * 32, boot_phase=1, writable=True,
            pending_trial=False, loaded_source="flash-confirmed", loaded_revision=self.original["active"]["revision"],
            storage_generation=str(int(self.original["storage_generation"]) + 3), write_base_sha256="e" * 64)
        self.state["candidate"] = deepcopy(self.state["temporary"])
        self.documents.pop("candidate", None)


class ActivationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = ApplyTransport()
        self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID, poll_interval=0.001)
        self.expected = await self.client.snapshot()
        self.fake.calls.clear()

    def applies(self):
        return [call for call in self.fake.calls if call[:2] == ("POST", API + "apply")]

    async def test_apply_receipt_and_read_only_progress_never_claim_early_success(self):
        initial = await self.client.inspect_activation(expected=self.expected)
        self.assertEqual(initial.state, ActivationState.UNCHANGED)
        receipt = await self.client.apply_candidate(expected=self.expected)
        self.assertEqual((receipt.revision, receipt.sha256), (40, self.expected.status.file(Source.CANDIDATE).sha256))
        self.assertTrue(receipt.snapshot.status.restarting and receipt.snapshot.status.flash_write.pending_trial)
        self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.RESTARTING)
        self.fake.reboot()
        for phase in (2, 3):
            self.fake.state["boot_phase"] = phase
            self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.CONFIRMING)
        self.fake.confirm()
        verified = await self.client.inspect_activation(expected=self.expected)
        self.assertEqual(verified.state, ActivationState.CONFIRMED)
        self.assertEqual(len(self.applies()), 1)
        self.assertFalse(verified.snapshot.capabilities.management_ready or verified.snapshot.status.dispatch_enabled)
        self.assertEqual(self.applies()[0][2]["X-Panel-Write-Base"], self.expected.status.write_base_sha256)

    async def test_rollback_is_distinct_from_confirmation_and_does_not_write(self):
        await self.client.apply_candidate(expected=self.expected)
        self.fake.reboot(); self.fake.rollback()
        before = len(self.applies())
        self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.ROLLED_BACK)
        self.assertEqual(len(self.applies()), before)

    async def test_apply_needs_pairing_trials_complete_metadata_and_counter_headroom(self):
        for change in ({"apply_enabled":False}, {"boot_phase":2}, {"boot_phase":99},
                       {"storage_generation":str(2**64 - 3)}, {"storage_generation":str(2**64 - 4)}):
            raw = {**self.fake.state, **change}
            expected = replace(self.expected, status=RuntimeStatus.parse(raw))
            with self.subTest(change=change), self.assertRaises(CandidateConflict):
                await self.client.apply_candidate(expected=expected)
        for key in ("apply_enabled", "boot_phase"):
            raw = deepcopy(self.fake.state); del raw[key]
            expected = replace(self.expected, status=RuntimeStatus.parse(raw))
            self.assertIsNone(expected.status.flash_boot)
            with self.assertRaises(ProtocolError): await self.client.apply_candidate(expected=expected)
        with self.assertRaises(IdentityMismatch):
            await PanelConfigClient(self.fake, TOKEN).apply_candidate(expected=self.expected)
        self.assertFalse(self.fake.calls)

    async def test_stale_baseline_and_bad_candidate_readback_prevent_apply(self):
        self.fake.state["write_base_sha256"] = "f" * 64
        with self.assertRaises(CandidateConflict): await self.client.apply_candidate(expected=self.expected)
        self.fake.state["write_base_sha256"] = self.expected.status.write_base_sha256
        self.fake.documents["candidate"] += b" "
        with self.assertRaises(ProtocolError): await self.client.apply_candidate(expected=self.expected)
        self.assertFalse(self.applies())

    async def test_lost_apply_reply_is_unknown_but_read_only_inspection_can_verify_later(self):
        def lost(method, suffix, result):
            if suffix == "apply": raise TransportError("PRIVATE " + TOKEN)
            return result
        self.fake.change = lost
        with self.assertRaises(OutcomeUnknown) as error: await self.client.apply_candidate(expected=self.expected)
        self.assertNotIn(TOKEN, str(error.exception))
        self.fake.change = lambda m, p, r: r
        self.fake.reboot(); self.fake.confirm()
        self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.CONFIRMED)
        self.assertEqual(len(self.applies()), 1)
        with self.assertRaises(CandidateConflict): await self.client.apply_candidate(expected=self.expected)
        self.assertEqual(len(self.applies()), 1)

    async def test_receipt_errors_and_fast_reboot_never_become_another_apply(self):
        for stage, change in (("apply", {"session_id":"0" * 32}), ("jobs/2", {"revision":999}),
                              ("jobs/2", {"done":True, "status":503})):
            await self.asyncSetUp()
            def corrupt(method, suffix, result):
                if suffix == stage:
                    return response(dict(json.loads(result.body), **change), status=result.status)
                return result
            self.fake.change = corrupt
            with self.subTest(stage=stage), self.assertRaises(OutcomeUnknown):
                await self.client.apply_candidate(expected=self.expected)
            self.assertEqual(len(self.applies()), 1)
        await self.asyncSetUp()
        def reboot(method, suffix, result):
            if suffix == "jobs/2": self.fake.reboot()
            return result
        self.fake.change = reboot
        with self.assertRaises(OutcomeUnknown): await self.client.apply_candidate(expected=self.expected)
        self.assertEqual(len(self.applies()), 1)

    async def test_confirmation_requires_exact_generation_files_phase_and_readback(self):
        await self.client.apply_candidate(expected=self.expected)
        self.fake.reboot(); self.fake.confirm()
        confirmed = deepcopy(self.fake.state)
        for key, value in (("pending_trial", True), ("writable", False), ("uncertain", True),
                           ("storage_generation", "12"), ("boot_phase", 1), ("boot_phase", 5),
                           ("boot_phase", 99), ("high_water_revision", 41), ("loaded_revision", 41),
                           ("dispatch_enabled", True), ("storage_warnings", 1), ("apply_enabled", False)):
            self.fake.state = {**deepcopy(confirmed), key:value}
            with self.subTest(key=key, value=value):
                self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.UNVERIFIED)
        self.fake.state = deepcopy(confirmed)
        self.fake.state["active"]["sha256"] = "a" * 64
        self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.UNVERIFIED)
        self.fake.state = deepcopy(confirmed)
        def bad_export(method, suffix, result):
            if suffix.startswith("downloads/"):
                return type(result)(result.status, result.headers, result.body + b" ")
            return result
        self.fake.change = bad_export
        with self.assertRaises(ProtocolError): await self.client.inspect_activation(expected=self.expected)
        self.assertEqual(len(self.applies()), 1)

    async def test_inspection_rejects_replacement_and_capability_drift_without_writes(self):
        self.fake.reboot()
        self.fake.state["device_id"] = "esp32-efuse-020000000046"
        with self.assertRaises(IdentityMismatch): await self.client.inspect_activation(expected=self.expected)
        self.fake.state["device_id"] = DEVICE_ID
        old = self.fake.change
        def changed(method, suffix, result):
            if suffix == "capabilities":
                body = json.loads(result.body); body["assets"]["inventory_complete"] = True
                return response(body)
            return old(method, suffix, result)
        self.fake.change = changed
        with self.assertRaises(ProtocolError): await self.client.inspect_activation(expected=self.expected)
        self.assertFalse(self.applies())

    async def test_apply_prequeue_conflict_is_definite_and_never_rebound(self):
        def race(method, suffix, result):
            if suffix == "capabilities" and len([c for c in self.fake.calls if c[1] == API + "capabilities"]) == 2:
                self.fake.state["write_base_sha256"] = "f" * 64
            return result
        self.fake.change = race
        with self.assertRaises(PanelHTTPError) as error: await self.client.apply_candidate(expected=self.expected)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.applies()), 1)

    async def test_cancellation_after_apply_submission_never_replays(self):
        committed = asyncio.Event()
        original = self.fake.request
        async def hold(method, path, **fields):
            result = await original(method, path, **fields)
            if path == API + "apply":
                committed.set(); await asyncio.Event().wait()
            return result
        self.fake.request = hold
        task = asyncio.create_task(self.client.apply_candidate(expected=self.expected))
        await committed.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(len(self.applies()), 1)
        self.fake.request = original
        self.assertEqual((await self.client.inspect_activation(expected=self.expected)).state, ActivationState.RESTARTING)

    async def test_pending_receipt_poll_limit_is_unknown_not_another_apply(self):
        self.client = PanelConfigClient(self.fake, TOKEN, expected_device_id=DEVICE_ID,
                                        poll_interval=0.001, max_polls=2)
        def pending(method, suffix, result):
            if suffix == "jobs/2": return response(dict(json.loads(result.body), done=False, status=202))
            return result
        self.fake.change = pending
        with self.assertRaises(OutcomeUnknown): await self.client.apply_candidate(expected=self.expected)
        self.assertEqual(len(self.applies()), 1)

    async def test_boot_metadata_optional_for_reads_but_strict_when_complete(self):
        for key, value in (("apply_enabled", 1), ("boot_phase", True), ("boot_phase", -1)):
            with self.subTest(key=key), self.assertRaises(ProtocolError):
                RuntimeStatus.parse({**self.fake.state, key:value})
        legacy = deepcopy(self.fake.state); del legacy["boot_phase"]
        self.assertIsNone(RuntimeStatus.parse(legacy).flash_boot)


if __name__ == "__main__": unittest.main()
