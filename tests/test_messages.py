from __future__ import annotations

import unittest

from moontransfer.messages import croc_status_from_line, process_result_message


class MessageTests(unittest.TestCase):
    def test_status_from_code_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("Code is: alpha-beta", role="send"),
            "Codice generato. Comunicalo alla persona che deve ricevere il file.",
        )

    def test_status_from_waiting_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("waiting for receiver", role="send"),
            "In attesa che il destinatario usi il codice.",
        )

    def test_status_from_transfer_line(self) -> None:
        self.assertEqual(
            croc_status_from_line("sending file.txt", role="send"),
            "Trasferimento in corso.",
        )

    def test_status_from_unrelated_line(self) -> None:
        self.assertIsNone(croc_status_from_line("some unrelated output", role="send"))

    def test_success_message(self) -> None:
        self.assertEqual(
            process_result_message(action="Invio", exit_code=0, crashed=False),
            "Invio: completato.",
        )

    def test_error_message(self) -> None:
        self.assertEqual(
            process_result_message(action="Ricezione", exit_code=1, crashed=False),
            "Ricezione: terminato con errore. Controlla l'output tecnico.",
        )

    def test_crash_message(self) -> None:
        self.assertEqual(
            process_result_message(action="Invio", exit_code=1, crashed=True),
            "Invio: interrotto. Controlla l'output tecnico.",
        )


if __name__ == "__main__":
    unittest.main()
