"""System actions for user-selected document URIs, never private staging paths."""
from __future__ import annotations

from urllib.parse import urlsplit


def document_action(uri: str, *, share: bool = False, directory: bool = False) -> None:
    parsed = urlsplit(uri)
    if parsed.scheme != "content" or not parsed.netloc:
        raise ValueError("Riferimento al contenuto non valido.")
    if share and directory:
        raise ValueError("Apri la cartella e seleziona i file da condividere.")
    from jnius import autoclass, cast

    activity = cast(
        "io.github.gaumeloth.moontransfer.MoonTransferActivity",
        autoclass("org.kivy.android.PythonActivity").mActivity,
    )
    activity.openSavedDocument(uri, share, directory)
