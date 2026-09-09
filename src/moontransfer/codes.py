"""Transfer-code parsing shared by desktop and Android frontends."""
from __future__ import annotations

import re

from moontransfer.protocol import ProtocolError, validate_croc_code

MAX_SHARED_TEXT = 8192
CODE_PATTERN = re.compile(
    r"(?<![\w])(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:[ \t]+[0-9a-fA-F]{8}){3})(?![\w])"
)


def codes_from_shared_text(text: str) -> tuple[str, ...]:
    if len(text) > MAX_SHARED_TEXT:
        raise ProtocolError("Il testo supera il limite di 8192 caratteri.")
    codes = tuple(dict.fromkeys(
        validate_croc_code("".join(match.group().split()).lower())
        for match in CODE_PATTERN.finditer(text)
    ))
    if not codes:
        raise ProtocolError("Nessun codice MoonTransfer riconosciuto nel testo.")
    if len(codes) > 8:
        raise ProtocolError("Troppi codici nel testo. Usa un solo codice.")
    return codes


def extract_transfer_code(text: str) -> str:
    codes = codes_from_shared_text(text)
    if len(codes) != 1:
        raise ProtocolError("Il testo contiene piu codici distinti. Usa un solo codice.")
    return codes[0]
