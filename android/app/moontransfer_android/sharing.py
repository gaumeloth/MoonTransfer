from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from moontransfer.cancellation import OperationCancelled
from moontransfer.codes import MAX_SHARED_TEXT, codes_from_shared_text as parse_codes
from moontransfer.protocol import MAX_PAYLOAD_ROOTS, ProtocolError, validate_croc_code
from moontransfer_android.storage import (
    AndroidStorageError,
    DIRECTORY_MIME_TYPE,
    StagedSelection,
    android_content_resolver,
    android_documents_contract,
    cleanup_staged_selection,
    stage_directory_uri,
    stage_document_uris,
)

ACTION_SEND = "android.intent.action.SEND"
ACTION_SEND_MULTIPLE = "android.intent.action.SEND_MULTIPLE"
EXTRA_STREAM = "android.intent.extra.STREAM"
EXTRA_TEXT = "android.intent.extra.TEXT"


class AndroidShareError(RuntimeError):
    pass


class SharedDirectoryAccessError(AndroidShareError):
    pass


@dataclass(frozen=True)
class SharedContent:
    uris: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()


def shared_code_message(code: str) -> str:
    return (
        f"Codice MoonTransfer: {validate_croc_code(code)}\n"
        "Copia questo messaggio e incollalo in Ricevi su MoonTransfer."
    )


def codes_from_shared_text(text: str) -> tuple[str, ...]:
    try:
        return parse_codes(text)
    except ProtocolError as error:
        raise AndroidShareError(str(error)) from error


def read_shared_intent(intent: Any) -> SharedContent | None:
    action = intent.getAction()
    if action not in (ACTION_SEND, ACTION_SEND_MULTIPLE):
        return None
    uris: list[str] = []

    def add_uri(uri: Any) -> None:
        if uri is None:
            raise AndroidShareError("La condivisione contiene un file non valido.")
        value = str(uri.toString())
        if len(value) > 8192:
            raise AndroidShareError("Il riferimento al contenuto supera il limite consentito.")
        parsed = urlsplit(value)
        if parsed.scheme != "content" or not parsed.netloc:
            raise AndroidShareError(
                "Il file manager non ha fornito un accesso Android al contenuto. "
                "Seleziona il file o la cartella da MoonTransfer."
            )
        if value not in uris:
            uris.append(value)
        if len(uris) > MAX_PAYLOAD_ROOTS:
            raise AndroidShareError(f"Puoi condividere al massimo {MAX_PAYLOAD_ROOTS} elementi.")

    if action == ACTION_SEND:
        stream = intent.getParcelableExtra(EXTRA_STREAM)
        if stream is not None:
            add_uri(stream)
    else:
        streams = intent.getParcelableArrayListExtra(EXTRA_STREAM)
        if streams is not None:
            if int(streams.size()) > MAX_PAYLOAD_ROOTS:
                raise AndroidShareError(f"Puoi condividere al massimo {MAX_PAYLOAD_ROOTS} elementi.")
            for index in range(int(streams.size())):
                add_uri(streams.get(index))

    # Some providers use ClipData instead of (or as well as) EXTRA_STREAM.
    clip = intent.getClipData()
    if clip is not None:
        if int(clip.getItemCount()) > MAX_PAYLOAD_ROOTS:
            raise AndroidShareError(f"Puoi condividere al massimo {MAX_PAYLOAD_ROOTS} elementi.")
        for index in range(int(clip.getItemCount())):
            uri = clip.getItemAt(index).getUri()
            if uri is not None:
                add_uri(uri)
    if uris:
        return SharedContent(uris=tuple(uris))
    texts: list[str] = []
    text_size = 0

    def add_text(text: Any) -> None:
        nonlocal text_size
        if text is None:
            return
        # Java CharSequence may be a SpannableString rather than a Python str.
        value = text if isinstance(text, str) else str(text.toString())
        if value in texts:
            return
        text_size += len(value) + bool(texts)
        if text_size > MAX_SHARED_TEXT:
            raise AndroidShareError("Il testo condiviso supera il limite consentito.")
        texts.append(value)

    multiple_texts = (
        intent.getCharSequenceArrayListExtra(EXTRA_TEXT)
        if action == ACTION_SEND_MULTIPLE else None
    )
    if multiple_texts is not None:
        if int(multiple_texts.size()) > MAX_PAYLOAD_ROOTS:
            raise AndroidShareError("Troppi testi condivisi. Condividi un solo codice.")
        for index in range(int(multiple_texts.size())):
            add_text(multiple_texts.get(index))
    else:
        add_text(intent.getCharSequenceExtra(EXTRA_TEXT))
    if clip is not None:
        for index in range(int(clip.getItemCount())):
            add_text(clip.getItemAt(index).getText())
    if not texts:
        raise AndroidShareError("Nessun file o codice nella condivisione ricevuta.")
    return SharedContent(codes=codes_from_shared_text("\n".join(texts)))


def share_code(code: str) -> None:
    message = shared_code_message(code)
    from jnius import autoclass, cast

    activity = cast(
        "io.github.gaumeloth.moontransfer.MoonTransferActivity",
        autoclass("org.kivy.android.PythonActivity").mActivity,
    )
    activity.shareTransferCode(message)


def stage_shared_uris(
    uris: tuple[str, ...],
    staging_parent: Path,
    *,
    existing_selection: StagedSelection | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
    resolver: Any = None,
    documents_contract: Any = None,
    uri_parser: Callable[[str], Any] | None = None,
) -> StagedSelection:
    if not uris or len(uris) > MAX_PAYLOAD_ROOTS:
        raise AndroidShareError("Numero di elementi condivisi non valido.")
    resolver = resolver or android_content_resolver()
    contract = documents_contract or android_documents_contract()
    if uri_parser is None:
        from jnius import autoclass
        uri_parser = autoclass("android.net.Uri").parse
    imported: StagedSelection | None = None
    combined = existing_selection
    copied = 0
    try:
        for value in uris:
            if cancel_requested and cancel_requested():
                raise OperationCancelled
            uri = uri_parser(value)
            is_tree = bool(contract.isTreeUri(uri))
            try:
                is_directory = resolver.getType(uri) == DIRECTORY_MIME_TYPE
            except Exception as error:
                if is_tree:
                    raise SharedDirectoryAccessError(
                        "Accesso alla cartella non disponibile. Selezionala dal selettore Android."
                    ) from error
                raise
            if is_tree and "/document/" not in urlsplit(value).path:
                is_directory = True

            def progress(current: int, _total: int | None) -> None:
                if on_progress is not None:
                    on_progress(copied + current, None)

            if is_directory:
                try:
                    if not is_tree:
                        raise AndroidStorageError("Accesso alla struttura non disponibile.")
                    root_id = (
                        str(contract.getDocumentId(uri))
                        if "/document/" in urlsplit(value).path else None
                    )
                    document = stage_directory_uri(
                        uri, staging_parent, existing_selection=combined,
                        resolver=resolver, documents_contract=contract,
                        root_document_id=root_id,
                        cancel_requested=cancel_requested, on_progress=progress,
                    )
                    selection = StagedSelection((document,))
                except OperationCancelled:
                    raise
                except Exception as error:
                    raise SharedDirectoryAccessError(
                        "Impossibile importare la cartella condivisa. "
                        "Selezionala dal selettore Android per autorizzare l'accesso "
                        "e verificare il contenuto."
                    ) from error
            else:
                selection = stage_document_uris(
                    (uri,), staging_parent, existing_selection=combined,
                    resolver=resolver, cancel_requested=cancel_requested,
                    on_progress=progress,
                )
            try:
                imported = selection if imported is None else imported.merged_with(selection)
            except Exception:
                cleanup_staged_selection(selection)
                raise
            combined = imported if existing_selection is None else existing_selection.merged_with(imported)
            copied += selection.total_size
        assert imported is not None
        return imported
    except BaseException:
        cleanup_staged_selection(imported)
        raise
