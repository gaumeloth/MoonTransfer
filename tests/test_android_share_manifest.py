from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from tools.android import validate_share_manifest


NS = "{http://schemas.android.com/apk/res/android}"


def manifest():
    root = ET.Element("manifest")
    app = ET.SubElement(root, "application")
    activity = ET.SubElement(app, "activity", {
        NS + "name": "io.github.gaumeloth.moontransfer.MoonTransferActivity",
        NS + "exported": "true",
        NS + "launchMode": "2",
    })
    for action, category in (
        ("MAIN", "LAUNCHER"), ("SEND", "DEFAULT"), ("SEND_MULTIPLE", "DEFAULT"),
    ):
        item = ET.SubElement(activity, "intent-filter")
        ET.SubElement(item, "action", {NS + "name": "android.intent.action." + action})
        ET.SubElement(item, "category", {NS + "name": "android.intent.category." + category})
        if action != "MAIN":
            ET.SubElement(item, "data", {NS + "mimeType": "*/*"})
    return root, app, activity


class AndroidShareManifestTests(unittest.TestCase):
    def test_packaged_numeric_and_symbolic_launch_mode(self):
        for mode in ("2", "singleTask"):
            root, _, activity = manifest()
            activity.set(NS + "launchMode", mode)
            validate_share_manifest(ET.tostring(root, encoding="unicode"))

    def test_wrong_activity_visibility_and_launch_mode_are_rejected(self):
        for attribute, value in (
            ("name", "org.kivy.android.PythonActivity"),
            ("exported", "false"), ("enabled", "false"), ("launchMode", "0"),
        ):
            with self.subTest(attribute=attribute):
                root, _, activity = manifest()
                activity.set(NS + attribute, value)
                with self.assertRaises(RuntimeError):
                    validate_share_manifest(ET.tostring(root, encoding="unicode"))

    def test_missing_or_misplaced_intent_filter_parts_are_rejected(self):
        for index, part in ((0, "category"), (1, "action"), (1, "category"), (1, "data"), (2, "action")):
            with self.subTest(index=index, part=part):
                root, _, activity = manifest()
                filters = activity.findall("intent-filter")
                node = filters[index].find(part)
                filters[index].remove(node)
                ET.SubElement(activity, "intent-filter").append(node)
                with self.assertRaises(RuntimeError):
                    validate_share_manifest(ET.tostring(root, encoding="unicode"))

    def test_disabled_application_is_rejected(self):
        root, app, _ = manifest()
        app.set(NS + "enabled", "false")
        with self.assertRaises(RuntimeError):
            validate_share_manifest(ET.tostring(root, encoding="unicode"))
