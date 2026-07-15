from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from moontransfer.progress import (
    TransferProgressSample,
    format_duration,
    format_file_size,
    format_transfer_rate,
)


class StatusLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setWordWrap(True)
        self.setStyleSheet(
            "QLabel {"
            "padding: 6px;"
            "border: 1px solid #c8c8c8;"
            "border-radius: 4px;"
            "background: #f6f6f6;"
            "}"
        )


class TransferProgressWidget(QWidget):
    def __init__(self, transferred_title: str) -> None:
        super().__init__()
        self.transferred_title = transferred_title
        self.total_bytes: int | None = None
        self.transferred_bytes = 0
        self.percent: int | None = None
        self.speed_bps: float | None = None
        self.started_at: float | None = None
        self.elapsed_seconds = 0.0
        self.running = False
        self.exact_total = False

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.total_value = QLabel("-")
        self.transferred_value = QLabel("0 B")
        self.speed_value = QLabel("-")
        self.elapsed_value = QLabel("-")
        self.eta_value = QLabel("-")

        for label in (
            self.total_value,
            self.transferred_value,
            self.speed_value,
            self.elapsed_value,
            self.eta_value,
        ):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.progress_bar, 0, 0, 1, 6)
        grid.addWidget(QLabel("Totale:"), 1, 0)
        grid.addWidget(self.total_value, 1, 1)
        grid.addWidget(QLabel(f"{self.transferred_title}:"), 1, 2)
        grid.addWidget(self.transferred_value, 1, 3)
        grid.addWidget(QLabel("Velocità:"), 1, 4)
        grid.addWidget(self.speed_value, 1, 5)
        grid.addWidget(QLabel("Tempo:"), 2, 0)
        grid.addWidget(self.elapsed_value, 2, 1)
        grid.addWidget(QLabel("Fine stimata:"), 2, 2)
        grid.addWidget(self.eta_value, 2, 3)
        grid.setColumnStretch(5, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self._refresh()

    def set_total_preview(self, total_bytes: int | None) -> None:
        if self.running:
            return

        self.total_bytes = total_bytes
        self.transferred_bytes = 0
        self.percent = 0 if total_bytes else None
        self.speed_bps = None
        self.exact_total = bool(total_bytes)
        self.elapsed_seconds = 0.0
        self.started_at = None
        self._refresh()

    def start(
        self,
        *,
        total_bytes: int | None = None,
        exact_total: bool = False,
    ) -> None:
        self.total_bytes = total_bytes
        self.transferred_bytes = 0
        self.percent = 0 if total_bytes else None
        self.speed_bps = None
        self.started_at = time.monotonic()
        self.elapsed_seconds = 0.0
        self.running = True
        self.exact_total = exact_total
        self.timer.start()
        self._refresh()

    def set_total(self, total_bytes: int) -> None:
        if self.exact_total and self.total_bytes:
            return

        self.total_bytes = total_bytes
        self._refresh()

    def apply_sample(self, sample: TransferProgressSample) -> None:
        if sample.percent is not None:
            self.percent = sample.percent

        if sample.total_bytes is not None:
            self.set_total(sample.total_bytes)

        if sample.speed_bps is not None:
            self.speed_bps = sample.speed_bps

        if sample.transferred_bytes is not None:
            if self.exact_total and self.total_bytes and sample.percent is not None:
                self.transferred_bytes = round(self.total_bytes * sample.percent / 100)
            else:
                self.transferred_bytes = sample.transferred_bytes
        elif sample.percent is not None and self.total_bytes:
            self.transferred_bytes = round(self.total_bytes * sample.percent / 100)

        if self.total_bytes is not None:
            self.transferred_bytes = min(self.transferred_bytes, self.total_bytes)

        self._refresh()

    def finish(self, *, success: bool) -> None:
        if self.started_at is not None:
            self.elapsed_seconds = time.monotonic() - self.started_at
        self.running = False
        self.timer.stop()

        if success and self.total_bytes is not None:
            self.transferred_bytes = self.total_bytes
            self.percent = 100

        self._refresh(success=success)

    def _current_elapsed(self) -> float | None:
        if self.started_at is None:
            return None
        if self.running:
            return time.monotonic() - self.started_at
        return self.elapsed_seconds

    def _estimated_remaining(self, elapsed: float | None) -> float | None:
        if not self.running or not self.total_bytes or self.transferred_bytes <= 0:
            return None

        remaining = self.total_bytes - self.transferred_bytes
        if remaining <= 0:
            return 0.0

        speed = self.speed_bps
        if not speed and elapsed and elapsed > 0:
            speed = self.transferred_bytes / elapsed

        if not speed or speed <= 0:
            return None

        return remaining / speed

    def _refresh(self, *, success: bool = False) -> None:
        elapsed = self._current_elapsed()

        if self.total_bytes:
            percent = self.percent
            if percent is None:
                percent = round(self.transferred_bytes * 100 / self.total_bytes)
            percent = max(0, min(100, percent))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        elif self.running:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        self.total_value.setText(
            format_file_size(self.total_bytes) if self.total_bytes else "-"
        )
        self.transferred_value.setText(format_file_size(self.transferred_bytes))
        self.speed_value.setText(format_transfer_rate(self.speed_bps))
        self.elapsed_value.setText(format_duration(elapsed))

        eta = self._estimated_remaining(elapsed)
        if success:
            self.eta_value.setText("Completato")
        else:
            self.eta_value.setText(format_duration(eta))


class TerminalView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def append_text(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertPlainText(text)
        self.ensureCursorVisible()

    def append_line(self, text: str = "") -> None:
        self.append_text(text + "\n")


class TechnicalOutput(QWidget):
    expanded_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.toggle = QToolButton()
        self.toggle.setText("Dettagli tecnici")
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.clear_button = QPushButton("Pulisci")
        self.clear_button.setVisible(False)

        self.terminal = TerminalView()
        self.terminal.setMinimumHeight(180)
        self.terminal.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.terminal.setVisible(False)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.addWidget(self.toggle)
        toggle_row.addStretch(1)
        toggle_row.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toggle_row)
        layout.addWidget(self.terminal, 1)

        self.clear_button.clicked.connect(self.terminal.clear)
        self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.clear_button.setVisible(expanded)
        self.terminal.setVisible(expanded)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if expanded else QSizePolicy.Policy.Fixed,
        )
        self.updateGeometry()
        self.expanded_changed.emit(expanded)


def add_expandable_output(layout: QVBoxLayout, output: TechnicalOutput) -> None:
    layout.addWidget(output)
    layout.addStretch(1)
    spacer_index = layout.count() - 1
    compact_height: int | None = None

    def update_stretch(expanded: bool) -> None:
        layout.setStretchFactor(output, 1 if expanded else 0)
        layout.setStretch(spacer_index, 0 if expanded else 1)
        QTimer.singleShot(0, sync_window_size)

    def sync_window_size() -> None:
        nonlocal compact_height
        window = output.window()
        if not window or window.isMaximized() or window.isFullScreen():
            return

        expanded = output.toggle.isChecked()
        target_height = window.sizeHint().height()
        if expanded:
            window.setMinimumHeight(window.minimumSizeHint().height())
            if compact_height is None:
                compact_height = window.height()
            if window.height() < target_height:
                window.resize(window.width(), target_height)
        else:
            target_height = compact_height or target_height
            if window.height() > target_height:
                window.resize(window.width(), target_height)
            QTimer.singleShot(
                0,
                lambda target_height=target_height: shrink_collapsed_window(
                    target_height
                ),
            )
            compact_height = target_height

    def shrink_collapsed_window(target_height: int) -> None:
        window = output.window()
        if (
            window
            and not output.toggle.isChecked()
            and not window.isMaximized()
            and not window.isFullScreen()
        ):
            window.setMinimumHeight(target_height)
            window.resize(window.width(), target_height)

    output.expanded_changed.connect(update_stretch)
    update_stretch(output.toggle.isChecked())
