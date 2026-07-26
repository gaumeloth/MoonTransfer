from __future__ import annotations

import unittest

from moontransfer.cancellation import OperationCancelled
from moontransfer.tasks import CancellableTask


class CancellableTaskTests(unittest.TestCase):
    def test_run_records_successful_result(self) -> None:
        task = CancellableTask(lambda _cancel_requested: 42)

        task.run()

        self.assertEqual(task.result, 42)
        self.assertIsNone(task.error)
        self.assertFalse(task.was_cancelled)

    def test_run_records_operation_failure(self) -> None:
        error = RuntimeError("failure")

        def fail(_cancel_requested):
            raise error

        task = CancellableTask(fail)
        task.run()

        self.assertIs(task.error, error)
        self.assertIsNone(task.result)
        self.assertFalse(task.was_cancelled)

    def test_pre_cancelled_task_does_not_publish_result(self) -> None:
        def cancelled(_cancel_requested):
            raise OperationCancelled

        task = CancellableTask(cancelled)
        task.cancel()
        task.run()

        self.assertTrue(task.was_cancelled)
        self.assertIsNone(task.result)
        self.assertIsNone(task.error)


if __name__ == "__main__":
    unittest.main()
