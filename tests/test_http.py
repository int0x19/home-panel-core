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
        self.assertEqual(len(self.seen), 1)

    async def test_rejects_credential_urls_and_non_read_check_routes(self):
        for origin in ("http://user:secret@127.0.0.1", "file:///tmp/test", "http://127.0.0.1/?key=x",
                       "http://127.0.0.1/#x", "http://127.0.0.1/a", "http://127.0.0.1:0", "http://127.0.0.1\\@other"):
            with self.subTest(origin=origin), self.assertRaises(ValueError): AiohttpTransport(self.session, origin)
        for path in (API + "upload", API + "apply", API + "scan", "https://other.invalid", API + "downloads/../1"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                await self.transport.request("POST", path, headers={}, body=b"", max_bytes=1024)
        self.assertEqual(self.seen, [])


if __name__ == "__main__": unittest.main()
