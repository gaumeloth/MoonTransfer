from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QThread

from moontransfer.cancellation import OperationCancelled


class CancellableTask(QThread):
    def __init__(
        self,
        operation: Callable[[Callable[[], bool]], object],
    ) -> None:
        super().__init__()
        self.operation = operation
        self.result: object | None = None
        self.error: Exception | None = None
        self.was_cancelled = False
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        try:
            result = self.operation(self.cancel_requested)
        except OperationCancelled:
            self.was_cancelled = True
        except Exception as exc:
            self.error = exc
        else:
            self.result = result
