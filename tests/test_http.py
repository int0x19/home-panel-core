"""Optional real aiohttp/loopback tests; never connects to a household device."""

import asyncio
from contextlib import suppress
import os
from pathlib import Path
import sys
import unittest

from home_panel_core import IdentityMismatch, PanelConfigClient, PanelHTTPError, ProtocolError, TransportError
from home_panel_core.protocol import API
from home_panel_core.testing import DEVICE_ID, FakeTransport, TOKEN
from test_candidate import UploadTransport
from test_activation import ApplyTransport

try:
    import aiohttp
    from aiohttp import web
    from home_panel_core.aiohttp_transport import AiohttpTransport
except ImportError:
    aiohttp = None


@unittest.skipUnless(aiohttp and os.environ.get("PANEL_CONFIG_HTTP_TEST") == "1",
                     "Install optional client requirements and set PANEL_CONFIG_HTTP_TEST=1 for loopback")
class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeTransport(with_capabilities=True)
        self.mode = "normal"
        self.seen = []
        async def handle(request):
            self.seen.append((request.method, request.path))
            if self.mode == "redirect":
                return web.Response(status=302, headers={"Location": "http://127.0.0.1:1/stolen"})
            if self.mode == "compressed":
                return web.Response(body=b"no decompression", headers={"Content-Encoding": "gzip"})
            if self.mode == "large":
                return web.Response(body=b"x" * 17000)
            if self.mode == "chunked":
                result = web.StreamResponse(headers={"Content-Type": "application/json"})
                await result.prepare(request)
                with suppress(ConnectionResetError):
                    await result.write(b"x" * 17000)
                    await result.write_eof()
                return result
            if self.mode == "slow":
                await asyncio.sleep(0.05)
            result = await self.fake.request(request.method, request.path, headers=request.headers,
                                            body=await request.read(), max_bytes=65536)
            return web.Response(status=result.status, body=result.body, headers=result.headers)
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.addAsyncCleanup(self.runner.cleanup)
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.origin = str(self.runner.addresses[0][0]) + ":" + str(self.runner.addresses[0][1])
        self.session = aiohttp.ClientSession()
        self.addAsyncCleanup(self.session.close)
        self.transport = AiohttpTransport(self.session, "http://" + self.origin)
        self.client = PanelConfigClient(self.transport, TOKEN)

    async def test_real_http_export_and_validate_with_injected_session(self):
        self.assertEqual((await self.client.capabilities()).device_id, DEVICE_ID)
        result = await self.client.export()
        self.assertEqual(result.data, self.fake.documents["active"])
        self.assertFalse((await self.client.validate(b"broken")).valid)
        self.assertFalse(self.session.closed)

    async def test_real_http_pairing_pin_cannot_adopt_another_device(self):
        client = PanelConfigClient(self.transport, TOKEN, expected_device_id=DEVICE_ID)
        self.assertEqual((await client.capabilities()).device_id, DEVICE_ID)
        self.fake.state["device_id"] = "esp32-efuse-020000000046"
        before = len(self.seen)
        with self.assertRaises(IdentityMismatch): await client.export()
        self.assertEqual(self.seen[before:], [("GET", API + "status")])

    async def test_redirect_does_not_leak_credentials_or_get_retried(self):
        self.mode = "redirect"
        with self.assertRaises(PanelHTTPError) as error: await self.client.status()
        self.assertEqual(error.exception.status, 302)
        self.assertEqual(self.seen, [("GET", API + "status")])
        self.assertNotIn(TOKEN, str(error.exception))

    async def test_compression_and_known_or_chunked_oversize_are_bounded(self):
        for mode in ("compressed", "large", "chunked"):
            self.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ProtocolError): await self.client.status()

    async def test_transport_timeout_is_redacted(self):
        self.mode = "slow"
        client = PanelConfigClient(AiohttpTransport(self.session, "http://" + self.origin, request_timeout=0.005), TOKEN)
        with self.assertRaises(TransportError) as error: await client.status()
        self.assertNotIn(TOKEN, str(error.exception))
        # Under CPU load the deadline can expire before the loopback handler runs.
        self.assertLessEqual(len(self.seen), 1)

    async def test_rejects_credential_urls_and_non_read_check_routes(self):
        for origin in ("http://user:secret@127.0.0.1", "file:///tmp/test", "http://127.0.0.1/?key=x",
                       "http://127.0.0.1/#x", "http://127.0.0.1/a", "http://127.0.0.1:0", "http://127.0.0.1\\@other"):
            with self.subTest(origin=origin), self.assertRaises(ValueError): AiohttpTransport(self.session, origin)
        for path in (API + "upload", API + "apply", API + "scan", "https://other.invalid", API + "downloads/../1"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                await self.transport.request("POST", path, headers={}, body=b"", max_bytes=1024)
        self.assertEqual(self.seen, [])

    async def test_candidate_upload_requires_explicit_transport_opt_in(self):
        self.fake = UploadTransport()
        client = PanelConfigClient(self.transport, TOKEN, expected_device_id=DEVICE_ID)
        baseline = await client.snapshot()
        data = self.fake.documents["active"].replace(b'"revision":31', b'"revision":40')
        with self.assertRaises(ValueError): await client.send_candidate(data, expected=baseline)
        self.assertFalse(any(method == "POST" for method, _ in self.seen))
        transport = AiohttpTransport(self.session, "http://" + self.origin, allow_candidate_upload=True)
        client = PanelConfigClient(transport, TOKEN, expected_device_id=DEVICE_ID)
        result = await client.send_candidate(data, expected=baseline)
        self.assertTrue(result.changed); self.assertEqual(result.revision, 40)
        self.assertEqual(self.fake.documents["candidate"], data)
        self.assertEqual(sum(path == API + "upload" for _, path in self.seen), 1)
        for suffix in ("apply", "restore", "discard", "scan", "authority/claim"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                await transport.request("POST", API + suffix, headers={}, body=b"{}", max_bytes=1024)

    async def test_upload_opt_in_does_not_follow_redirects_or_retry(self):
        self.fake = UploadTransport()
        transport = AiohttpTransport(self.session, "http://" + self.origin, allow_candidate_upload=True)
        client = PanelConfigClient(transport, TOKEN, expected_device_id=DEVICE_ID)
        baseline = await client.snapshot()
        data = self.fake.documents["active"].replace(b'"revision":31', b'"revision":40')
        original = self.fake.change
        def redirect(method, suffix, result):
            if suffix == "upload": return type(result)(302, (("Location", "http://127.0.0.1:1/stolen"),), b"")
            return original(method, suffix, result)
        self.fake.change = redirect
        from home_panel_core import OutcomeUnknown
        with self.assertRaises(OutcomeUnknown): await client.send_candidate(data, expected=baseline)
        self.assertEqual(sum(path == API + "upload" for _, path in self.seen), 1)

    async def test_apply_has_its_own_opt_in_and_inspection_never_retries_it(self):
        from home_panel_core import ActivationState, OutcomeUnknown
        self.fake = ApplyTransport()
        client = PanelConfigClient(self.transport, TOKEN, expected_device_id=DEVICE_ID)
        baseline = await client.snapshot()
        with self.assertRaises(ValueError): await client.apply_candidate(expected=baseline)
        self.assertFalse(any(path == API + "apply" for _, path in self.seen))
        transport = AiohttpTransport(self.session, "http://" + self.origin, allow_candidate_apply=True)
        with self.assertRaises(ValueError):
            await transport.request("POST", API + "upload", headers={}, body=b"{}", max_bytes=1024)
        client = PanelConfigClient(transport, TOKEN, expected_device_id=DEVICE_ID)
        def redirect(method, suffix, result):
            if suffix == "apply": return type(result)(302, (("Location", "http://127.0.0.1:1/stolen"),), b"")
            return result
        self.fake.change = redirect
        with self.assertRaises(OutcomeUnknown): await client.apply_candidate(expected=baseline)
        self.fake.change = lambda method, suffix, result: result
        self.fake.reboot(); self.fake.confirm()
        self.assertEqual((await client.inspect_activation(expected=baseline)).state, ActivationState.CONFIRMED)
        self.assertEqual(sum(path == API + "apply" for _, path in self.seen), 1)
        for suffix in ("restore", "discard", "scan", "authority/claim"):
            with self.assertRaises(ValueError):
                await transport.request("POST", API + suffix, headers={}, body=b"{}", max_bytes=1024)


if __name__ == "__main__": unittest.main()
