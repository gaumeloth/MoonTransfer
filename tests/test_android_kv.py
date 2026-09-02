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
    def test_layout_declares_all_ids_required_by_python(self) -> None:
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
        self.assertEqual(set(expected).difference(declared), set())

    def test_layout_is_declarative_and_uses_named_screens(self) -> None:
        source = KV_PATH.read_text(encoding="utf-8")

        self.assertIn("MoonTransferRoot:", source)
        self.assertIn("ScreenManager:", source)
        self.assertIn('name: "send"', source)
        self.assertIn('name: "receive"', source)
        self.assertIn('name: "send_selection"', source)
        self.assertIn('name: "send_transfer"', source)
        self.assertIn('name: "send_result"', source)
        self.assertIn('name: "receive_code"', source)
        self.assertIn('name: "receive_proposal"', source)
        self.assertIn('name: "receive_save"', source)
        self.assertIn('name: "receive_result"', source)

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

    def test_file_and_directory_flows_are_exposed_by_the_ui(self) -> None:
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
        self.assertIn('text: "Aggiungi contenuto"', layout)
        self.assertIn('text: "File"', layout)
        self.assertIn('text: "Cartella"', layout)
        self.assertIn('text: "Proposta ricevuta"', layout)

    def test_send_selection_can_be_extended_and_managed(self) -> None:
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
        staging_source = ast.unparse(methods["_run_staging"])
        layout = KV_PATH.read_text(encoding="utf-8")

        self.assertIn("existing_selection=existing_selection", staging_source)
        self.assertIn("stage_directory_uri", staging_source)
        self.assertIn("_remove_selected_document", methods)
        self.assertIn("_clear_selection", methods)
        self.assertIn('text: "File"', layout)
        self.assertIn('text: "Cartella"', layout)
        self.assertIn('text: "Svuota"', layout)
        self.assertIn("id: selection_list", layout)

    def test_custom_design_system_is_used_consistently(self) -> None:
        source = KV_PATH.read_text(encoding="utf-8")

        for rule in (
            "<MoonButton>",
            "<MoonIconButton>",
            "<MoonNavButton>",
            "<MoonSurface>",
            "<MoonProgressBar>",
            "<MoonResultPanel>",
            "<MoonDialogOverlay>",
        ):
            self.assertIn(rule, source)
        self.assertIn("moontransfer_android.theme", source)
        self.assertIn("RecycleView:", source)
        self.assertIn("transition: NoTransition()", source)
        self.assertNotIn("background_color: app.accent_color", source)


if __name__ == "__main__":
    unittest.main()
