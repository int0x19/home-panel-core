"""Synthetic wire fixtures only; no device network or household commands."""

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import HTTPResponse, Source
from .json_codec import encode_document
from .protocol import API
from .runtime_model.panel_actions import ACTION_ICONS
from .runtime_model.panel_model import layout_keys, theme_keys

TOKEN = "client-test-key-not-a-real-credential"
DEVICE_ID = "esp32-efuse-020000000045"
STATUS = Path(__file__).parent / "testing_data/runtime_management_status_v1.json"
DOCUMENT = json.loads((Path(__file__).parent / "testing_data/actions_v1.json").read_bytes())
PILOT_FEATURES = frozenset({"rooms.v1", "style.v1", "widget.action", "action-pages.v1", "script-controls.v1"})

def capability_document(state):
    return {"format": "home-panel-capabilities", "metadata_version": 1, "protocol_version": 1,
        "session_id": state["session_id"], "device_id": state["device_id"],
        "identity_source": "esp32-efuse-mac48", "target": "esp32-action-preview",
        "config_format": "home-panel-runtime", "schema_versions": [1], "features": sorted(PILOT_FEATURES),
        "widget_types": ["action"], "room_kinds": ["room", "actions"], "display": {"width": 320, "height": 480},
        "limits": {"document_bytes": state["max_bytes"], "scratch_bytes": 65536, "model_bytes": 16384,
            "presentation_bytes": 16384, "rooms": 12, "room_pages": 24, "widgets": 12, "entity_bindings": 12,
            "subscriptions": 0, "views": 0, "attention_sources": 0, "string_bytes": 256, "id_bytes": 64,
            "depth": 16, "nodes": 16384}, "limits_measured_on_device": False,
        "validation": {"action_icons": list(ACTION_ICONS), "interactions": ["tap", "hold", "confirm"],
            "font_sizes": [14, 18, 24, 36], "layout_keys": list(layout_keys()), "theme_keys": list(theme_keys())},
        "runtime": {"preview_compiled": False, "production_rooms": False, "dispatch_enabled": False},
        "assets": {"source": "firmware", "upload": False, "inventory_complete": False},
        "authority": {"mode": "unmanaged", "enforced": False}, "deployment_ready": False, "management_ready": False}


def response(value, *, status=200, extra=()):
    data = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
    return HTTPResponse(status, (("Content-Type", "application/json"),
        ("Content-Length", str(len(data))), *extra), data)


def metadata(data):
    return {"present": True, "valid": True, "status": 1, "model_status": 0,
            "bytes": len(data), "revision": json.loads(data)["revision"],
            "sha256": hashlib.sha256(data).hexdigest()}


class FakeTransport:
    def __init__(self, *, with_capabilities=False):
        self.state = json.loads(STATUS.read_bytes())
        self.documents = {}
        for source, revision in zip(Source, (31, 32, 30)):
            doc = deepcopy(DOCUMENT); doc["revision"] = revision
            self.documents[source] = encode_document(doc)
            self.state[source] = metadata(self.documents[source])
        self.calls = []
        self.jobs = {}
        self.next_id = 0
        self.change = lambda _method, _path, result: result
        if with_capabilities:
            self.state["features"].append("capabilities.v1")
            self.state["device_id"] = DEVICE_ID

    async def request(self, method, path, *, headers, body, max_bytes):
        await asyncio.sleep(0)
        self.calls.append((method, path, dict(headers), body, max_bytes))
        assert headers["Authorization"] == "Bearer " + TOKEN
        suffix = path.removeprefix(API)
        if suffix == "status":
            result = response(self.state)
        elif suffix == "capabilities":
            result = response(capability_document(self.state))
        elif method == "POST":
            assert suffix in {"export", "validate"}
            assert headers["X-Panel-Settings"] == self.state["session_id"]
            if self.state.get("storage") == "flash-nvs":
                assert headers["X-Panel-Storage-Generation"] == self.state["storage_generation"]
            self.next_id += 1
            result = {"id": self.next_id, "done": False, "status": 202,
                "session_id": self.state["session_id"], "revision": self.state["revision"], "error": ""}
            if "capabilities.v1" in self.state["features"]:
                result["device_id"] = self.state["device_id"]
            job = dict(result, done=True, status=200)
            if suffix == "export":
                envelope = json.loads(body)
                assert envelope["revision"] == self.state["revision"]
                source = Source(envelope["source"])
                assert envelope["sha256"] == self.state[source]["sha256"]
                job.update(download=API + "downloads/" + str(self.next_id), source=source,
                           sha256=self.state[source]["sha256"], bytes=self.state[source]["bytes"])
            else:
                assert headers["X-Panel-Revision"] == str(self.state["revision"])
                good = body != b"broken"
                job["status"] = 200 if good else 400
                document = json.loads(body) if good else None
                job["validation"] = {"status": 0 if good else 1, "model_error": 0,
                                     "revision": document["revision"] if good else 0,
                                     "rooms": len(document["rooms"]) if good else 0}
            self.jobs[self.next_id] = job
            result = response(result, status=202)
        elif suffix.startswith("jobs/"):
            result = response(self.jobs[int(suffix.split("/")[1])])
        elif suffix.startswith("downloads/"):
            job = self.jobs[int(suffix.split("/")[1])]
            result = response(self.documents[job["source"]], extra=(
                ("X-Panel-Session", self.state["session_id"]), ("X-Panel-SHA256", job["sha256"]),
                ("Content-Disposition", f'attachment; filename=panel-{job["source"]}.json')))
        else:
            raise AssertionError(path)
        return self.change(method, suffix, result)
