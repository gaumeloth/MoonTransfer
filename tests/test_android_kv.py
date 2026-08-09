from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_PATH = (
    ROOT / "android" / "app" / "moontransfer_android" / "application.py"
)
KV_PATH = ROOT / "android" / "app" / "moontransfer_android" / "moontransfer.kv"


def _application_tree() -> ast.Module:
    return ast.parse(APPLICATION_PATH.read_text(encoding="utf-8"))


def _view_ids(tree: ast.Module) -> tuple[str, ...]:
    assignment = next(
        statement
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "VIEW_IDS"
    )
    value = ast.literal_eval(assignment.value)
    if not isinstance(value, tuple) or not all(
        isinstance(item, str) for item in value
    ):
        raise AssertionError("VIEW_IDS must be a tuple of strings")
    return value


class AndroidKvLayoutTests(unittest.TestCase):
    def test_layout_declares_exactly_the_ids_required_by_python(self) -> None:
        expected = _view_ids(_application_tree())
        source = KV_PATH.read_text(encoding="utf-8")
        declared = tuple(
            re.findall(
                r"^\s*id:\s*([a-z_][a-z0-9_]*)\s*$",
                source,
                flags=re.MULTILINE,
            )
        )

        self.assertEqual(len(expected), len(set(expected)))
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(set(declared), set(expected))

    def test_layout_is_declarative_and_uses_named_screens(self) -> None:
        source = KV_PATH.read_text(encoding="utf-8")

        self.assertIn("MoonTransferRoot:", source)
        self.assertIn("ScreenManager:", source)
        self.assertIn('name: "send"', source)
        self.assertIn('name: "receive"', source)
        self.assertNotRegex(source, r"(?m)^\s*on_(?:press|release|text):")

    def test_application_loads_kv_and_binds_callbacks_in_python(self) -> None:
        tree = _application_tree()
        application = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "MoonTransferAndroidApp"
        )
        methods = {
            node.name: node
            for node in application.body
            if isinstance(node, ast.FunctionDef)
        }
        build_source = ast.unparse(methods["build"])
        bind_source = ast.unparse(methods["_bind_view"])

        self.assertIn("Builder.load_file(str(KV_PATH))", build_source)
        self.assertIn("set(VIEW_IDS).difference(root.ids)", bind_source)
        self.assertIn(".bind(on_release=", bind_source)
        self.assertNotIn("_build_send_view", methods)
        self.assertNotIn("_build_receive_view", methods)

    def test_multi_file_copy_and_save_flows_are_exposed_by_the_ui(self) -> None:
        tree = _application_tree()
        application = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "MoonTransferAndroidApp"
        )
        methods = {
            node.name: node
            for node in application.body
            if isinstance(node, ast.FunctionDef)
        }
        picker_source = ast.unparse(methods["_open_save_picker"])
        layout = KV_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "select_directory=not proposal.is_single_file",
            picker_source,
        )
        self.assertIn("Invia uno o più file", layout)
        self.assertIn("Ricevi uno o più file", layout)


if __name__ == "__main__":
    unittest.main()
