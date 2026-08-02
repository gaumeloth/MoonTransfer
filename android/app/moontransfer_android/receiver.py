from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from moontransfer import croc
from moontransfer.cancellation import OperationCancelled
from moontransfer.files import (
    CONTROL_METADATA_NAME,
    directory_payload_size,
    ensure_receive_capacity,
)
from moontransfer.payload import verify_received_payload
from moontransfer.progress import (
    AggregateTransferProgress,
    TransferProgressSample,
    parse_transfer_progress,
)
from moontransfer.protocol import (
    MAX_CONTROL_FILE_BYTES,
    TransferProposal,
    read_proposal,
    validate_croc_code,
)
from moontransfer_android.storage import save_file_to_uri
from moontransfer_android.transport import (
    CrocProcessResult,
    CrocProcessRunner,
    CrocProcessTimeout,
    croc_failure_detail,
)


CONTROL_IDLE_TIMEOUT_SECONDS = 15 * 60.0
DECISION_TIMEOUT_SECONDS = 15 * 60.0
MAIN_RECEIVE_DELAY_SECONDS = 0.75


class AndroidReceiveState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RECEIVING_METADATA = "receiving_metadata"
    AWAITING_DECISION = "awaiting_decision"
    RESPONDING_TO_DECISION = "responding_to_decision"
    RECEIVING_FILE = "receiving_file"
    VERIFYING = "verifying"
    AWAITING_SAVE = "awaiting_save"
    SAVING = "saving"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


def _ignore(*_args: object) -> None:
    return None


@dataclass(frozen=True)
class AndroidReceiveCallbacks:
    on_state: Callable[[AndroidReceiveState], None] = _ignore
    on_status: Callable[[str], None] = _ignore
    on_proposal: Callable[[TransferProposal], None] = _ignore
    on_progress: Callable[[TransferProgressSample], None] = _ignore
    on_save_ready: Callable[[TransferProposal], None] = _ignore
    on_save_progress: Callable[[int, int], None] = _ignore
    on_log: Callable[[str], None] = _ignore
    on_finished: Callable[[AndroidReceiveState, str], None] = _ignore


@dataclass
class AndroidReceiveSession:
    metadata_code: str
    root: Path | None = None
    croc_config: Path | None = None
    metadata_dir: Path | None = None
    main_dir: Path | None = None
    proposal: TransferProposal | None = None
    accepted: bool | None = None
    decision_expired: bool = False
    destination_uri: Any = None


class AndroidReceiveController:
    def __init__(
        self,
        *,
        runner: CrocProcessRunner,
        sessions_parent: Path,
        callbacks: AndroidReceiveCallbacks | None = None,
        idle_timeout: float = CONTROL_IDLE_TIMEOUT_SECONDS,
        decision_timeout: float = DECISION_TIMEOUT_SECONDS,
        main_receive_delay: float = MAIN_RECEIVE_DELAY_SECONDS,
        save_file: Callable[..., int] = save_file_to_uri,
    ) -> None:
        if decision_timeout <= 0:
            raise ValueError("Il timeout di decisione deve essere positivo.")
        if main_receive_delay < 0:
            raise ValueError("Il ritardo di ricezione non può essere negativo.")
        self.runner = runner
        self.sessions_parent = sessions_parent
        self.callbacks = callbacks or AndroidReceiveCallbacks()
        self.idle_timeout = idle_timeout
        self.decision_timeout = decision_timeout
        self.main_receive_delay = main_receive_delay
        self.save_file = save_file
        self.state = AndroidReceiveState.IDLE
        self.session: AndroidReceiveSession | None = None
        self._cancel_requested = Event()
        self._decision_ready = Event()
        self._save_ready = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._progress = AggregateTransferProgress()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, metadata_code: str) -> None:
        validated_code = validate_croc_code(metadata_code)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Una ricezione è già in corso.")
            self._cancel_requested.clear()
            self._decision_ready.clear()
            self._save_ready.clear()
            self.session = AndroidReceiveSession(metadata_code=validated_code)
            thread = Thread(target=self._run, daemon=True)
            self._thread = thread

        self._set_state(AndroidReceiveState.PREPARING)
        self.callbacks.on_status("Preparazione della ricezione...")
        thread.start()

    def accept(self) -> None:
        self._set_decision(True)

    def reject(self) -> None:
        self._set_decision(False)

    def save_to_uri(self, uri: Any) -> None:
        with self._lock:
            if self.state != AndroidReceiveState.AWAITING_SAVE:
                raise RuntimeError("Nessun file verificato da salvare.")
            session = self.session
            if session is None:
                raise RuntimeError("Sessione di ricezione non disponibile.")
            session.destination_uri = uri
            self._save_ready.set()
        self._set_state(AndroidReceiveState.SAVING)

    def save_cancelled(self) -> None:
        if self.state == AndroidReceiveState.AWAITING_SAVE:
            self.callbacks.on_status(
                "Salvataggio annullato. Il file verificato resta disponibile "
                "finché l'app rimane aperta."
            )

    def cancel(self) -> None:
        if not self.active:
            return
        self._cancel_requested.set()
        self._decision_ready.set()
        self._save_ready.set()
        self.callbacks.on_status("Interruzione della ricezione in corso...")
        self.runner.request_stop()

    def wait(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        terminal_state = AndroidReceiveState.FAILED
        terminal_message = "Ricezione non completata."
        session = self._require_session()
        try:
            self._prepare_session(session)
            self._receive_metadata(session)
            proposal = self._require_proposal(session)

            if not proposal.is_single_file:
                self.callbacks.on_proposal(proposal)
                self.callbacks.on_status(
                    "Il mittente ha proposto elementi non ancora supportati "
                    "su Android. Comunico il rifiuto."
                )
                self._receive_main_response(session, accepted=False)
                terminal_state = AndroidReceiveState.REJECTED
                terminal_message = (
                    "Trasferimento rifiutato: il prototipo Android può "
                    "ricevere un solo file."
                )
            else:
                self._set_state(AndroidReceiveState.AWAITING_DECISION)
                self.callbacks.on_proposal(proposal)
                self.callbacks.on_status(
                    "Controlla le informazioni e scegli se ricevere il file."
                )
                accepted = self._wait_for_decision(session)
                if not accepted:
                    self._receive_main_response(session, accepted=False)
                    terminal_state = AndroidReceiveState.REJECTED
                    terminal_message = (
                        "Trasferimento rifiutato automaticamente per timeout."
                        if session.decision_expired
                        else "Trasferimento rifiutato."
                    )
                else:
                    try:
                        self._ensure_private_capacity(session)
                    except OSError as error:
                        self.callbacks.on_status(
                            "Spazio privato insufficiente. Comunico il "
                            "rifiuto al mittente."
                        )
                        self._receive_main_response(session, accepted=False)
                        terminal_state = AndroidReceiveState.REJECTED
                        terminal_message = (
                            "Trasferimento rifiutato: spazio insufficiente "
                            f"sul dispositivo ({error})."
                        )
                    else:
                        self._receive_main_response(session, accepted=True)
                        self._verify_received_file(session)
                        self._wait_for_save_destination(session)
                        self._save_received_file(session)
                        terminal_state = AndroidReceiveState.COMPLETED
                        terminal_message = "Ricezione e salvataggio completati."
        except OperationCancelled:
            terminal_state = AndroidReceiveState.CANCELLED
            terminal_message = "Ricezione interrotta."
        except CrocProcessTimeout:
            terminal_message = (
                "Nessuna attività rilevata entro il tempo previsto. "
                "La ricezione è stata interrotta."
            )
        except Exception as error:
            terminal_message = f"Ricezione non completata: {error}"
        finally:
            self._cleanup_session(session)
            self._set_state(terminal_state)
            self.callbacks.on_status(terminal_message)
            self.callbacks.on_finished(terminal_state, terminal_message)
            with self._lock:
                self.session = None

    def _prepare_session(self, session: AndroidReceiveSession) -> None:
        self._raise_if_cancelled()
        self.sessions_parent.mkdir(parents=True, exist_ok=True)
        root = Path(
            tempfile.mkdtemp(prefix="receive-", dir=self.sessions_parent)
        )
        metadata_dir = root / "metadata-receive"
        main_dir = root / "main-receive"
        metadata_dir.mkdir()
        main_dir.mkdir()
        session.root = root
        session.croc_config = root / "croc-config"
        session.metadata_dir = metadata_dir
        session.main_dir = main_dir

    def _receive_metadata(self, session: AndroidReceiveSession) -> None:
        if not session.metadata_dir or not session.croc_config:
            raise RuntimeError("Sessione metadati non inizializzata.")

        self._set_state(AndroidReceiveState.RECEIVING_METADATA)
        self.callbacks.on_status("Ricezione delle informazioni sul file...")
        result = self.runner.run(
            croc.build_receive_args(),
            config_dir=session.croc_config,
            secret=session.metadata_code,
            workdir=session.metadata_dir,
            idle_timeout=self.idle_timeout,
            cancel_requested=self._cancel_requested.is_set,
            on_line=lambda line: self.callbacks.on_log(f"[metadata] {line}"),
            process_guard=lambda: self._guard_directory_size(
                session.metadata_dir,
                MAX_CONTROL_FILE_BYTES,
                "metadati",
            ),
        )
        self._ensure_success(result, "Ricezione delle informazioni")
        self._guard_directory_size(
            session.metadata_dir,
            MAX_CONTROL_FILE_BYTES,
            "metadati",
        )

        metadata_path = session.metadata_dir / CONTROL_METADATA_NAME
        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"File metadati atteso non trovato: {metadata_path.name}"
            )
        session.proposal = read_proposal(metadata_path)
        self._progress.reset(session.proposal.file_sizes)

    def _wait_for_decision(self, session: AndroidReceiveSession) -> bool:
        deadline = time.monotonic() + self.decision_timeout
        while not self._decision_ready.wait(0.1):
            self._raise_if_cancelled()
            if time.monotonic() >= deadline:
                session.accepted = False
                session.decision_expired = True
                self._set_state(AndroidReceiveState.RESPONDING_TO_DECISION)
                return False
        self._raise_if_cancelled()
        return bool(session.accepted)

    def _set_decision(self, accepted: bool) -> None:
        with self._lock:
            if self.state != AndroidReceiveState.AWAITING_DECISION:
                raise RuntimeError("Nessuna proposta in attesa di decisione.")
            session = self.session
            if session is None:
                raise RuntimeError("Sessione di ricezione non disponibile.")
            session.accepted = accepted
            self._decision_ready.set()
        self._set_state(AndroidReceiveState.RESPONDING_TO_DECISION)

    def _receive_main_response(
        self,
        session: AndroidReceiveSession,
        *,
        accepted: bool,
    ) -> None:
        proposal = self._require_proposal(session)
        if not session.main_dir or not session.croc_config:
            raise RuntimeError("Sessione principale non inizializzata.")

        self._set_state(AndroidReceiveState.RESPONDING_TO_DECISION)
        self.callbacks.on_status(
            "Attendo il file dal mittente..."
            if accepted
            else "Comunicazione del rifiuto al mittente..."
        )
        self._wait_before_main_receiver()
        if accepted:
            self._set_state(AndroidReceiveState.RECEIVING_FILE)
            self.callbacks.on_status("Ricezione del file in corso...")

        process_guard: Callable[[], None] | None = None
        if accepted:
            process_guard = lambda: self._guard_directory_size(
                session.main_dir,
                proposal.size,
                "file principale",
            )

        result = self.runner.run(
            croc.build_prompted_receive_args(),
            config_dir=session.croc_config,
            secret=proposal.main_code,
            workdir=session.main_dir,
            idle_timeout=self.idle_timeout,
            cancel_requested=self._cancel_requested.is_set,
            on_line=lambda line: self._handle_main_line(line),
            stdin_data=b"y\n" if accepted else b"n\n",
            process_guard=process_guard,
        )
        if not accepted:
            return
        self._ensure_success(result, "Ricezione del file")
        self._guard_directory_size(
            session.main_dir,
            proposal.size,
            "file principale",
        )

    def _ensure_private_capacity(self, session: AndroidReceiveSession) -> None:
        proposal = self._require_proposal(session)
        if not session.main_dir:
            raise RuntimeError("Directory di ricezione non disponibile.")
        ensure_receive_capacity(session.main_dir, proposal.size)

    def _wait_before_main_receiver(self) -> None:
        deadline = time.monotonic() + self.main_receive_delay
        while time.monotonic() < deadline:
            self._raise_if_cancelled()
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def _handle_main_line(self, line: str) -> None:
        self.callbacks.on_log(f"[main] {line}")
        sample = parse_transfer_progress(line)
        if sample is not None:
            self.callbacks.on_progress(self._progress.apply(sample))

    def _verify_received_file(self, session: AndroidReceiveSession) -> None:
        proposal = self._require_proposal(session)
        if not session.main_dir:
            raise RuntimeError("Directory del file ricevuto non disponibile.")
        self._set_state(AndroidReceiveState.VERIFYING)
        self.callbacks.on_status("Verifica di dimensione e hash SHA-256...")
        verify_received_payload(
            session.main_dir,
            proposal,
            cancel_requested=self._cancel_requested.is_set,
        )

    def _wait_for_save_destination(self, session: AndroidReceiveSession) -> None:
        proposal = self._require_proposal(session)
        self._set_state(AndroidReceiveState.AWAITING_SAVE)
        self.callbacks.on_status(
            "File ricevuto e verificato. Scegli dove salvarlo."
        )
        self.callbacks.on_save_ready(proposal)
        while not self._save_ready.wait(0.1):
            self._raise_if_cancelled()
        self._raise_if_cancelled()
        if session.destination_uri is None:
            raise RuntimeError("Destinazione di salvataggio mancante.")

    def _save_received_file(self, session: AndroidReceiveSession) -> None:
        proposal = self._require_proposal(session)
        if not session.main_dir:
            raise RuntimeError("File verificato non disponibile.")
        self._set_state(AndroidReceiveState.SAVING)
        self.callbacks.on_status("Salvataggio nella destinazione scelta...")
        self.save_file(
            session.main_dir / proposal.filename,
            session.destination_uri,
            cancel_requested=self._cancel_requested.is_set,
            on_progress=self.callbacks.on_save_progress,
        )

    @staticmethod
    def _guard_directory_size(directory: Path, limit: int, stage: str) -> None:
        received = directory_payload_size(directory)
        if received > limit:
            raise ValueError(
                f"Dimensione ricevuta eccessiva durante {stage}: "
                f"{received} byte, limite {limit} byte."
            )

    @staticmethod
    def _ensure_success(result: CrocProcessResult, action: str) -> None:
        if result.returncode == 0:
            return
        raise RuntimeError(
            f"{action} non riuscita (exit code {result.returncode}): "
            f"{croc_failure_detail(result)}"
        )

    def _set_state(self, state: AndroidReceiveState) -> None:
        self.state = state
        self.callbacks.on_state(state)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise OperationCancelled

    def _require_session(self) -> AndroidReceiveSession:
        session = self.session
        if session is None:
            raise RuntimeError("Sessione di ricezione non disponibile.")
        return session

    @staticmethod
    def _require_proposal(
        session: AndroidReceiveSession,
    ) -> TransferProposal:
        if session.proposal is None:
            raise RuntimeError("Proposta di trasferimento non disponibile.")
        return session.proposal

    @staticmethod
    def _cleanup_session(session: AndroidReceiveSession) -> None:
        if session.root is not None:
            shutil.rmtree(session.root, ignore_errors=True)
