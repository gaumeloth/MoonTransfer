from __future__ import annotations


def process_result_message(
    *,
    action: str,
    exit_code: int,
    crashed: bool,
) -> str:
    if not crashed and exit_code == 0:
        return f"{action}: completato."

    if crashed:
        return f"{action}: interrotto. Controlla l'output tecnico."

    return f"{action}: terminato con errore. Controlla l'output tecnico."


def croc_status_from_line(line: str, *, role: str) -> str | None:
    normalized = line.strip().lower()
    if not normalized:
        return None

    if "code is:" in normalized and role == "send":
        return "Codice generato. Comunicalo alla persona che deve ricevere il file."

    if "waiting" in normalized and any(
        word in normalized for word in ("receiver", "recipient", "peer")
    ):
        return "In attesa che il destinatario usi il codice."

    if any(word in normalized for word in ("connecting", "connected")):
        return "Connessione stabilita. Trasferimento in preparazione."

    if any(word in normalized for word in ("sending", "receiving", "transferring")):
        return "Trasferimento in corso."

    if any(word in normalized for word in ("error", "failed", "refused", "unable")):
        return "croc segnala un errore. Controlla i dettagli tecnici."

    return None
