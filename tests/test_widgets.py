from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from moontransfer.widgets import (
    DropPathListWidget,
    StatusLabel,
    TerminalView,
    local_paths_from_mime_data,
    plain_message_box,
)


class PathDropListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_extracts_local_paths_in_url_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.txt"
            second = Path(tmp) / "folder"
            mime_data = QMimeData()
            mime_data.setUrls(
                [
                    QUrl.fromLocalFile(str(first)),
                    QUrl.fromLocalFile(str(second)),
                ]
            )

            self.assertEqual(
                local_paths_from_mime_data(mime_data),
                (first, second),
            )

    def test_rejects_a_drop_containing_a_nonlocal_url(self) -> None:
        mime_data = QMimeData()
        mime_data.setUrls(
            [
                QUrl.fromLocalFile("/tmp/local.txt"),
                QUrl("https://example.com/remote.txt"),
            ]
        )

        self.assertEqual(local_paths_from_mime_data(mime_data), ())

    def test_valid_drop_is_highlighted_and_emitted_as_copy(self) -> None:
        widget = DropPathListWidget()
        mime_data = QMimeData()
        path = Path("/tmp/example.txt")
        mime_data.setUrls([QUrl.fromLocalFile(str(path))])
        active_states: list[bool] = []
        dropped: list[tuple[Path, ...]] = []
        widget.drop_active_changed.connect(active_states.append)
        widget.paths_dropped.connect(dropped.append)

        enter_event = QDragEnterEvent(
            QPoint(1, 1),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget.viewport(), enter_event)

        self.assertTrue(enter_event.isAccepted())
        self.assertTrue(widget.property("dropActive"))

        drop_event = QDropEvent(
            QPointF(1, 1),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget.viewport(), drop_event)

        self.assertTrue(drop_event.isAccepted())
        self.assertEqual(drop_event.dropAction(), Qt.DropAction.CopyAction)
        self.assertEqual(active_states, [True, False])
        self.assertEqual(dropped, [(path,)])

    def test_drop_is_rejected_when_disabled(self) -> None:
        widget = DropPathListWidget()
        widget.set_drop_enabled(False)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile("/tmp/example.txt")])
        dropped: list[tuple[Path, ...]] = []
        widget.paths_dropped.connect(dropped.append)

        drop_event = QDropEvent(
            QPointF(1, 1),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget.viewport(), drop_event)

        self.assertFalse(drop_event.isAccepted())
        self.assertFalse(widget.drop_enabled)
        self.assertEqual(dropped, [])


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
