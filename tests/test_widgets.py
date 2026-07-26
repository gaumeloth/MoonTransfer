from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from moontransfer.widgets import StatusLabel, TerminalView, plain_message_box


class WidgetSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_status_label_uses_plain_text(self) -> None:
        label = StatusLabel("<b>untrusted</b>")

        self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)

    def test_message_box_uses_plain_text(self) -> None:
        box = plain_message_box(
            None,
            icon=QMessageBox.Icon.Question,
            title="Transfer",
            text="<b>untrusted filename</b>",
            standard_buttons=(
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
        )

        self.assertEqual(box.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(box.text(), "<b>untrusted filename</b>")

    def test_terminal_limits_retained_output(self) -> None:
        terminal = TerminalView()

        self.assertEqual(terminal.maximumBlockCount(), 5000)


if __name__ == "__main__":
    unittest.main()
