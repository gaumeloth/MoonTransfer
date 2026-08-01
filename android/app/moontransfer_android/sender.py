from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread

from moontransfer import croc
from moontransfer.cancellation import OperationCancelled
from moontransfer.files import CONTROL_METADATA_NAME
from moontransfer.payload import (
    SourcePayload,
    ensure_source_payload_unchanged,
    scan_source_payload,
)
from moontransfer.progress import (
    AggregateTransferProgress,
    TransferProgressSample,
    parse_transfer_progress,
)
from moontransfer.protocol import (
    TransferProposal,
    generate_croc_code,
    write_control_file,
)
from moontransfer_android.storage import StagedDocument, cleanup_staged_document
from moontransfer_android.transport import (
    CrocProcessResult,
    CrocProcessRunner,
    CrocProcessTimeout,
)


CONTROL_IDLE_TIMEOUT_SECONDS = 15 * 60.0
REJECTION_TOKENS = ("declin", "reject", "refus", "cancel")
NON_ERROR_OUTPUT_PREFIXES = (
    "Code is:",
    "On the other computer run:",
    "(For Windows)",
    "(For Linux/macOS)",
    "Or receive in a browser:",
    "https://getcroc.com/?code=",
    "croc ",
    "CROC_SECRET=",
)


class AndroidSendState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    SENDING_METADATA = "sending_metadata"
    AWAITING_DECISION = "awaiting_decision"
    SENDING_FILE = "sending_file"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


def _ignore(*_args: object) -> None:
    return None


@dataclass(frozen=True)
class AndroidSendCallbacks:
    on_state: Callable[[AndroidSendState], None] = _ignore
    on_status: Callable[[str], None] = _ignore
    on_prepared: Callable[[TransferProposal, str], None] = _ignore
    on_progress: Callable[[TransferProgressSample], None] = _ignore
    on_log: Callable[[str], None] = _ignore
    on_finished: Callable[[AndroidSendState, str], None] = _ignore


@dataclass
class AndroidSendSession:
    document: StagedDocument
    root: Path | None = None
    croc_config: Path | None = None
    metadata_path: Path | None = None
    payload: SourcePayload | None = None
    proposal: TransferProposal | None = None
    metadata_code: str | None = None
    rejected_by_receiver: bool = False


class AndroidSendController:
    def __init__(
        self,
        *,
        runner: CrocProcessRunner,
        sessions_parent: Path,
        callbacks: AndroidSendCallbacks | None = None,
        idle_timeout: float = CONTROL_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.runner = runner
        self.sessions_parent = sessions_parent
        self.callbacks = callbacks or AndroidSendCallbacks()
        self.idle_timeout = idle_timeout
        self.state = AndroidSendState.IDLE
        self.session: AndroidSendSession | None = None
        self._cancel_requested = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._progress = AggregateTransferProgress()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, document: StagedDocument) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Un trasferimento è già in corso.")
            self._cancel_requested.clear()
            self.session = AndroidSendSession(document=document)
            thread = Thread(target=self._run, daemon=True)
            self._thread = thread

        self._set_state(AndroidSendState.PREPARING)
        self.callbacks.on_status(
            "Analisi del file e calcolo dell'hash SHA-256..."
        )
        thread.start()

    def cancel(self) -> None:
        if not self.active:
            return
        self._cancel_requested.set()
        self.callbacks.on_status("Interruzione dell'invio in corso...")
        self.runner.request_stop()

    def wait(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        terminal_state = AndroidSendState.FAILED
        terminal_message = "Invio non completato."
        session = self._require_session()
        try:
            self._prepare_session(session)
            self._send_metadata(session)
            self._send_main_file(session)
            if session.rejected_by_receiver:
                terminal_state = AndroidSendState.REJECTED
                terminal_message = "Trasferimento rifiutato dal destinatario."
            else:
                terminal_state = AndroidSendState.COMPLETED
                terminal_message = "Invio completato."
        except OperationCancelled:
            terminal_state = AndroidSendState.CANCELLED
            terminal_message = "Invio interrotto."
        except CrocProcessTimeout:
            terminal_message = (
                "Nessuna attività rilevata entro il tempo previsto. "
                "Il trasferimento è stato interrotto."
            )
        except Exception as error:
            terminal_message = f"Invio non completato: {error}"
        finally:
            self._cleanup_session(session)
            self._set_state(terminal_state)
            self.callbacks.on_status(terminal_message)
            self.callbacks.on_finished(terminal_state, terminal_message)
            with self._lock:
                self.session = None

    def _prepare_session(self, session: AndroidSendSession) -> None:
        self._raise_if_cancelled()
        payload = scan_source_payload(
            (session.document.path,),
            cancel_requested=self._cancel_requested.is_set,
        )
        proposal = payload.create_proposal()
        metadata_code = generate_croc_code()

        self.sessions_parent.mkdir(parents=True, exist_ok=True)
        root = Path(
            tempfile.mkdtemp(prefix="send-", dir=self.sessions_parent)
        )
        metadata_dir = root / "metadata-send"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / CONTROL_METADATA_NAME
        croc_config = root / "croc-config"
        write_control_file(metadata_path, proposal)

        session.root = root
        session.croc_config = croc_config
        session.metadata_path = metadata_path
        session.payload = payload
        session.proposal = proposal
        session.metadata_code = metadata_code
        self._progress.reset(proposal.file_sizes)
        self.callbacks.on_prepared(proposal, metadata_code)

    def _send_metadata(self, session: AndroidSendSession) -> None:
        if not session.metadata_path or not session.croc_config:
            raise RuntimeError("Sessione metadati non inizializzata.")
        if not session.metadata_code:
            raise RuntimeError("Codice metadati mancante.")

        self._set_state(AndroidSendState.SENDING_METADATA)
        self.callbacks.on_status(
            "Codice pronto. In attesa che il destinatario riceva le informazioni..."
        )
        result = self.runner.run(
            croc.build_send_args(session.metadata_path),
            config_dir=session.croc_config,
            secret=session.metadata_code,
            workdir=session.metadata_path.parent,
            idle_timeout=self.idle_timeout,
            cancel_requested=self._cancel_requested.is_set,
            on_line=lambda line: self._handle_process_line("metadata", line),
        )
        self._ensure_success(result, "Invio delle informazioni")

    def _send_main_file(self, session: AndroidSendSession) -> None:
        if not session.payload or not session.proposal or not session.croc_config:
            raise RuntimeError("Sessione di invio incompleta.")

        self._set_state(AndroidSendState.AWAITING_DECISION)
        self.callbacks.on_status(
            "Informazioni ricevute. Attendo la decisione del destinatario..."
        )
        ensure_source_payload_unchanged(
            session.payload,
            cancel_requested=self._cancel_requested.is_set,
        )
        self._raise_if_cancelled()
        result = self.runner.run(
            croc.build_send_args(session.payload.root_paths),
            config_dir=session.croc_config,
            secret=session.proposal.main_code,
            workdir=session.document.staging_dir,
            idle_timeout=self.idle_timeout,
            cancel_requested=self._cancel_requested.is_set,
            on_line=lambda line: self._handle_process_line("main", line),
        )
        if session.rejected_by_receiver:
            return
        self._ensure_success(result, "Invio del file")

    def _handle_process_line(self, role: str, line: str) -> None:
        self.callbacks.on_log(f"[{role}] {line}")
        if role != "main":
            return

        session = self._require_session()
        lowered = line.lower()
        if any(token in lowered for token in REJECTION_TOKENS):
            session.rejected_by_receiver = True

        sample = parse_transfer_progress(line)
        if "Sending (->" in line or sample is not None:
            if self.state == AndroidSendState.AWAITING_DECISION:
                self._set_state(AndroidSendState.SENDING_FILE)
                self.callbacks.on_status("Trasferimento del file in corso...")
        if sample is not None:
            self.callbacks.on_progress(self._progress.apply(sample))

    @staticmethod
    def _ensure_success(result: CrocProcessResult, action: str) -> None:
        if result.returncode == 0:
            return
        detail = AndroidSendController._failure_detail(result)
        raise RuntimeError(
            f"{action} non riuscito (exit code {result.returncode}): {detail}"
        )

    @staticmethod
    def _failure_detail(result: CrocProcessResult) -> str:
        for lines in (
            result.stdout_tail,
            result.stderr_tail,
            result.output_tail,
        ):
            for line in reversed(lines):
                detail = line.strip()
                if detail and not detail.startswith(NON_ERROR_OUTPUT_PREFIXES):
                    return detail
        return "croc non ha restituito dettagli sull'errore"

    def _set_state(self, state: AndroidSendState) -> None:
        self.state = state
        self.callbacks.on_state(state)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise OperationCancelled

    def _require_session(self) -> AndroidSendSession:
        session = self.session
        if session is None:
            raise RuntimeError("Sessione di invio non disponibile.")
        return session

    @staticmethod
    def _cleanup_session(session: AndroidSendSession) -> None:
        if session.root is not None:
            shutil.rmtree(session.root, ignore_errors=True)
        cleanup_staged_document(session.document)
