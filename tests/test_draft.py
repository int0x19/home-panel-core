"""Shared logical sensor edits; no browser, HA, firmware source or device I/O."""

from copy import deepcopy
import json
from pathlib import Path
import random
import shutil
import subprocess
import unittest

from home_panel_core import asset_path
from home_panel_core.runtime_model.panel_runtime import validate_document
from home_panel_core.testing import DOCUMENT, FakeTransport, capability_document


@unittest.skipUnless(shutil.which("node"), "Node required for shared draft asset")
class SensorDraftTests(unittest.TestCase):
    def setUp(self):
        self.doc = deepcopy(DOCUMENT)
        self.caps = capability_document(FakeTransport(with_capabilities=True).state)
        self.caps["features"].extend(["widget.sensor", "sensor-groups.v1"])
        self.caps["widget_types"].append("sensor")

    def run_edits(self, *operations, document=None, caps=None):
        source = self.doc if document is None else document
        result = subprocess.run(["node", str(Path(__file__).with_name("draft_driver.mjs")), str(asset_path("runtime-draft.mjs"))],
            input=json.dumps({"document":source, "capabilities":self.caps if caps is None else caps, "operations":operations}),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["unchanged"])
        return report

    def sensor(self, id="temperature", entity="sensor.bedroom_temperature", **settings):
        return {"type":"put_sensor", "room":"room", "target":"room", "id":id,
                "settings":{"entity":entity, "name":"Temperature", **settings}}

    def test_named_and_unnamed_groups_stable_ids_and_cross_room_move(self):
        temperature = self.sensor(group="comfort", unit="\u00b0C", device_class="temperature")
        humidity = self.sensor("humidity", "sensor.bedroom_humidity", group="comfort", unit="%", device_class="humidity")
        temperature["group_name"] = "\u041a\u043e\u043c\u043d\u0430\u0442\u0430"
        report = self.run_edits(temperature, humidity)
        self.assertEqual(report["errors"], [])
        doc = report["document"]
        self.assertEqual(doc["rooms"][0]["groups"], {"comfort":{"name":"\u041a\u043e\u043c\u043d\u0430\u0442\u0430"}})
        self.assertEqual(report["plans"][0]["height"], doc["style"]["layout"]["sensor_group_height"])
        edit = self.sensor(id="ignored", group="comfort", unit="K")
        edit.update(previous="temperature", group_name="")
        report = self.run_edits(edit, document=doc)
        self.assertEqual(report["document"]["rooms"][0]["groups"], {"comfort":{}})
        self.assertEqual(report["document"]["rooms"][0]["widgets"][0]["id"], "temperature")
        edit.update(target="empty", group_name="Air")
        report = self.run_edits(edit, document=report["document"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["document"]["rooms"][2]["groups"], {"comfort":{"name":"Air"}})
        report = self.run_edits({"type":"delete_sensor", "room":"room", "id":"humidity"}, document=report["document"])
        self.assertEqual(report["document"]["rooms"][0]["groups"], {})
        self.assertIn("sensor-groups.v1", report["document"]["requires"])
        validate_document(report["document"])

    def test_last_sensor_removal_prunes_owned_features(self):
        report = self.run_edits(self.sensor(group="air"), {"type":"delete_sensor", "room":"room", "id":"temperature"})
        self.assertEqual(report["errors"], [])
        self.assertNotIn("widget.sensor", report["document"]["requires"])
        self.assertNotIn("sensor-groups.v1", report["document"]["requires"])
        self.assertEqual(report["document"], self.doc)

    def test_features_widget_inventory_and_action_pages_are_enforced(self):
        for change in (lambda c:c["features"].remove("widget.sensor"), lambda c:c["widget_types"].remove("sensor"),
                       lambda c:c["features"].remove("sensor-groups.v1")):
            caps = deepcopy(self.caps); change(caps)
            self.assertEqual(self.run_edits(self.sensor(group="air"), caps=caps)["errors"], ["capability"])
        operation = self.sensor(); operation["target"] = "actions"
        self.assertEqual(self.run_edits(operation)["errors"], ["sensor_page"])
        report = self.run_edits(self.sensor(), {"type":"room_settings", "room":"room", "name":"Actions", "kind":"actions"})
        self.assertEqual(report["errors"], ["sensor_page"])
        self.assertNotIn("kind", report["document"]["rooms"][0])

    def test_bad_settings_and_duplicate_placements_are_atomic(self):
        for fields, code in (({"entity":"light.no"}, "entity"), ({"name":""}, "text"),
                             ({"name":"\ud800"}, "text"), ({"unit":42}, "text"),
                             ({"unit":"bad\nunit"}, "text"), ({"device_class":""}, "text"),
                             ({"group":"not an id"}, "group"), ({"simulator":{"value":25}}, "sensor_fields")):
            report = self.run_edits(self.sensor(**fields))
            self.assertEqual(report["errors"], [code], fields)
            self.assertEqual(report["document"], self.doc)
        operation = self.sensor(group="air"); operation["group_name"] = "\u042f" * 129
        self.assertEqual(self.run_edits(operation)["errors"], ["text"])
        report = self.run_edits(self.sensor(), self.sensor("other"), self.sensor(entity="sensor.other"))
        self.assertEqual(report["errors"], ["duplicate", "duplicate"])

    def test_repeated_sources_share_binding_budget_but_ids_remain_room_local(self):
        self.caps["limits"]["entity_bindings"] = 4  # Three existing actions plus one sensor.
        repeated = self.sensor(); repeated["target"] = "empty"
        report = self.run_edits(self.sensor(), repeated, self.sensor("humidity", "sensor.humidity"))
        self.assertEqual(report["errors"], ["binding_limit"])
        self.assertEqual(validate_document(report["document"])["bindings"], 4)

    def test_opaque_fields_are_preserved_and_not_silently_overwritten(self):
        doc = self.run_edits(self.sensor(group="air"))["document"]
        doc["rooms"][0]["groups"]["air"]["future"] = {"keep":True}
        report = self.run_edits(self.sensor("humidity", "sensor.humidity", group="air"),
            {"type":"delete_room", "room":"room"},
            {"type":"room_settings", "room":"room", "name":"Kitchen", "kind":"room"}, document=doc)
        self.assertEqual(report["errors"], ["opaque_room", "opaque_room"])
        self.assertEqual(report["document"]["rooms"][0]["groups"], doc["rooms"][0]["groups"])
        self.assertEqual(report["document"]["rooms"][0]["widgets"], doc["rooms"][0]["widgets"])

    def test_groups_named_like_object_properties_are_safe(self):
        for group in ("__proto__", "constructor", "to_string"):
            operation = self.sensor(group=group); operation["group_name"] = "Air"
            report = self.run_edits(operation)
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["document"]["rooms"][0]["groups"], {group:{"name":"Air"}})
            validate_document(report["document"])

    def test_mixed_actions_use_available_space_and_group_title_changes_fit_atomically(self):
        doc = deepcopy(self.doc)
        doc["rooms"][0]["widgets"] = doc["rooms"][1]["widgets"]
        doc["rooms"][1]["widgets"] = []
        report = self.run_edits(self.sensor(group="air"), document=doc)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["plans"][0]["height"], 212)
        doc = self.run_edits(*(self.sensor(f"s{i}", f"sensor.s{i}", group="air") for i in range(9)))["document"]
        doc["style"]["layout"]["sensor_group_height"] = 80
        report = self.run_edits({**self.sensor("ignored", "sensor.s0", group="air"), "previous":"s0", "group_name":"Air"}, document=doc)
        self.assertEqual(report["errors"], ["room_full"])
        self.assertEqual(report["document"], doc)

    def test_planner_matches_python_for_named_groups_nonadjacent_members_and_moves(self):
        rng = random.Random(56)
        for columns in range(1, 7):
            for named in (False, True):
                doc = deepcopy(self.doc)
                doc["style"]["layout"]["sensor_group_columns"] = columns
                operations = [self.sensor(f"s{i}", f"sensor.s{i}", group="air") for i in range(4)]
                operations[0]["group_name"] = "Air" if named else ""
                doc = self.run_edits(*operations, document=doc)["document"]
                doc["rooms"][0]["widgets"].extend(doc["rooms"][1]["widgets"][:2])
                doc["rooms"][1]["widgets"] = []
                rng.shuffle(doc["rooms"][0]["widgets"])
                report = self.run_edits({"type":"move_sensor", "room":"room", "id":"s1", "offset":1}, document=doc)
                model = validate_document(report["document"])
                self.assertEqual(report["plans"][0]["height"], model["room_content_height"]["room"])
                self.assertEqual(report["plans"][0]["available"], model["room_available_height"])

    def test_dense_group_width_guard_matches_native_contract(self):
        doc = deepcopy(self.doc)
        doc["style"]["layout"].update(sensor_group_columns=6, sensor_icon_size=24)
        report = self.run_edits(*(self.sensor(f"s{i}", f"sensor.s{i}", group="air") for i in range(6)), document=doc)
        self.assertEqual(report["errors"], ["geometry"])
        self.assertEqual(len(report["document"]["rooms"][0]["widgets"]), 5)


if __name__ == "__main__":
    unittest.main()
