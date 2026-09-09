import unittest

from moontransfer.codes import codes_from_shared_text, extract_transfer_code
from moontransfer.protocol import ProtocolError


class CodeExtractionTests(unittest.TestCase):
    def test_raw_spaced_uppercase_and_message(self):
        code = "0123456789abcdef" * 2
        for text in (code, code.upper(), " ".join(code[i:i+8] for i in range(0, 32, 8)),
                     f"Codice MoonTransfer: {code}\nCopia questo messaggio."):
            with self.subTest(text=text):
                self.assertEqual(extract_transfer_code(text), code)

    def test_duplicate_is_unambiguous_but_distinct_codes_are_rejected(self):
        self.assertEqual(extract_transfer_code("a" * 32 + " " + "a" * 32), "a" * 32)
        with self.assertRaises(ProtocolError):
            extract_transfer_code("a" * 32 + " " + "b" * 32)

    def test_limits_boundaries_and_fragments(self):
        for text in ("", "a" * 64, "_" + "a" * 32, "a" * 16 + "\n" + "a" * 16,
                     "x" * 8193, " ".join(f"{i:032x}" for i in range(9))):
            with self.subTest(length=len(text)), self.assertRaises(ProtocolError):
                codes_from_shared_text(text)
