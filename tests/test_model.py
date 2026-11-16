from copy import deepcopy
import json
import unittest

import home_panel_core
from home_panel_core.json_codec import encode_document
from home_panel_core.runtime_model.panel_runtime import decode_document, validate_document
from home_panel_core.testing import DOCUMENT


class ModelTests(unittest.TestCase):
    def test_fixture_and_canonical_roundtrip(self):
        report = validate_document(DOCUMENT)
        self.assertEqual(report["rooms"], 3)
        self.assertEqual(report["widgets"], 3)
        self.assertFalse(report["deployment_ready"])
        self.assertEqual(decode_document(encode_document(DOCUMENT)), DOCUMENT)

    def test_full_geometry_ids_features_and_profiles(self):
        for change in (lambda d: d["rooms"].append(deepcopy(d["rooms"][0])),
                       lambda d: d["style"]["layout"].update(nav_button_height=1),
                       lambda d: d.update(requires=[]),
                       lambda d: d["rooms"][1]["widgets"][0]["settings"].update(entity="light.bad")):
            doc = deepcopy(DOCUMENT); change(doc)
            with self.assertRaises(ValueError): validate_document(doc)

    def test_codec_and_framing(self):
        self.assertEqual(encode_document({"b": "\u041a\u0443\u0445\u043d\u044f", "a": [1, 2.0]}),
                         '{"a":[1,2.0],"b":"\u041a\u0443\u0445\u043d\u044f"}'.encode())
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":"\\ud800"}'):
            with self.assertRaises(ValueError): decode_document(raw)

    def test_packaged_asset_and_version(self):
        self.assertEqual(home_panel_core.__version__, "0.1.2")
        self.assertIn("export function", home_panel_core.asset_path("runtime-draft.mjs").read_text())
        with self.assertRaises(ValueError): home_panel_core.asset_path("../secrets.yaml")
