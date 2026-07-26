from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTimer, Signal

from moontransfer import croc
from moontransfer.files import (
    CONTROL_METADATA_NAME,
    SessionPaths,
    cleanup_session_paths,
    create_session_paths,
    directory_payload_size,
    ensure_receive_capacity,
    move_verified_file,
    received_path,
    sha256_file,
    verify_received_file,
)
from moontransfer.messages import croc_status_from_line
from moontransfer.progress import (
    parse_announced_transfer_total,
    parse_transfer_progress,
)
from moontransfer.protocol import (
    MAX_CONTROL_FILE_BYTES,
    TransferProposal,
    code_id,
    create_proposal,
    generate_croc_code,
    read_proposal,
    validate_filename,
    write_control_file,
)
from moontransfer.runner import CrocRunner


class TransferState(Enum):
    IDLE = auto()
    PREPARING = auto()
    TRANSFERRING_METADATA = auto()
    AWAITING_DECISION = auto()
    RESPONDING_TO_DECISION = auto()
    TRANSFERRING_FILE = auto()
    VERIFYING = auto()
    COMPLETED = auto()
    REJECTED = auto()
    CANCELLED = auto()
    FAILED = auto()


TERMINAL_STATES = frozenset(
    {
        TransferState.COMPLETED,
        TransferState.REJECTED,
        TransferState.CANCELLED,
        TransferState.FAILED,
    }
)
ACTIVE_STATES = frozenset(
    state
    for state in TransferState
    if state not in TERMINAL_STATES and state != TransferState.IDLE
)

SEND_TRANSITIONS: Mapping[TransferState, frozenset[TransferState]] = {
    TransferState.IDLE: frozenset({TransferState.PREPARING}),
    TransferState.PREPARING: frozenset(
        {
            TransferState.TRANSFERRING_METADATA,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.TRANSFERRING_METADATA: frozenset(
        {
            TransferState.AWAITING_DECISION,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.AWAITING_DECISION: frozenset(
        {
            TransferState.TRANSFERRING_FILE,
            TransferState.COMPLETED,
            TransferState.REJECTED,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.TRANSFERRING_FILE: frozenset(
        {
            TransferState.COMPLETED,
            TransferState.REJECTED,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    **{
        state: frozenset({TransferState.PREPARING})
        for state in TERMINAL_STATES
    },
}

RECEIVE_TRANSITIONS: Mapping[TransferState, frozenset[TransferState]] = {
    TransferState.IDLE: frozenset({TransferState.PREPARING}),
    TransferState.PREPARING: frozenset(
        {
            TransferState.TRANSFERRING_METADATA,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.TRANSFERRING_METADATA: frozenset(
        {
            TransferState.AWAITING_DECISION,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.AWAITING_DECISION: frozenset(
        {
            TransferState.RESPONDING_TO_DECISION,
            TransferState.TRANSFERRING_FILE,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.RESPONDING_TO_DECISION: frozenset(
        {
            TransferState.REJECTED,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.TRANSFERRING_FILE: frozenset(
        {
            TransferState.VERIFYING,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    TransferState.VERIFYING: frozenset(
        {
            TransferState.COMPLETED,
            TransferState.CANCELLED,
            TransferState.FAILED,
        }
    ),
    **{
        state: frozenset({TransferState.PREPARING})
        for state in TERMINAL_STATES
    },
}


class InvalidStateTransition(RuntimeError):
    pass


@dataclass
class TransferStateMachine:
    transitions: Mapping[TransferState, frozenset[TransferState]]
    state: TransferState = TransferState.IDLE

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES

    def transition(self, target: TransferState) -> bool:
        if target == self.state:
            return False

        allowed = self.transitions.get(self.state, frozenset())
        if target not in allowed:
            raise InvalidStateTransition(
                f"Transizione non valida: {self.state.name} -> {target.name}"
            )

        self.state = target
        return True


@dataclass(frozen=True)
class ReceiveDecision:
    accepted: bool
    target: Path | None = None
    overwrite: bool = False

    @classmethod
    def reject(cls) -> ReceiveDecision:
        return cls(accepted=False)

    @classmethod
    def accept(cls, target: Path, *, overwrite: bool) -> ReceiveDecision:
        return cls(accepted=True, target=target, overwrite=overwrite)


@dataclass
class SendSession:
    source_path: Path
    paths: SessionPaths | None = None
    proposal: TransferProposal | None = None
    metadata_code: str | None = None
    rejected_by_receiver: bool = False


@dataclass
class ReceiveSession:
    metadata_code: str
    destination: Path
    paths: SessionPaths | None = None
    proposal: TransferProposal | None = None
    target_path: Path | None = None
    target_overwrite: bool = False
    main_response_accepted: bool | None = None
    receive_size_limit: int | None = None
    receive_size_stage: str = ""


class BaseTransferController(QObject):
    CONTROL_TIMEOUT_MS = 15 * 60 * 1000

    state_changed = Signal(object)
    active_changed = Signal(bool)
    status_changed = Signal(str)
    error_raised = Signal(str, str)
    terminal_line = Signal(str)
    progress_preview_changed = Signal(object)
    progress_started = Signal(int, bool)
    progress_total_changed = Signal(int)
    progress_sampled = Signal(object)
    progress_finished = Signal(bool)

    def __init__(
        self,
        *,
        croc_path: str,
        runners: dict[str, CrocRunner],
        transitions: Mapping[TransferState, frozenset[TransferState]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.croc_path = croc_path
        self.runners = runners
        self.machine = TransferStateMachine(transitions)
        self.stopping = False
        self.timeout_stage = ""

        for name, runner in self.runners.items():
            runner.on_line = (
                lambda line, role=name: self._on_runner_line(role, line)
            )
            runner.on_finished = (
                lambda exit_code, exit_status, role=name: self._on_runner_finished(
                    role,
                    exit_code,
                    exit_status,
                )
            )

        self.control_timer = QTimer(self)
        self.control_timer.setSingleShot(True)
        self.control_timer.timeout.connect(self._on_control_timeout)

    @property
    def state(self) -> TransferState:
        return self.machine.state

    @property
    def active(self) -> bool:
        return self.machine.active

    def any_running(self) -> bool:
        return any(runner.is_running() for runner in self.runners.values())

    def _transition(self, target: TransferState) -> None:
        was_active = self.active
        if not self.machine.transition(target):
            return

        self.state_changed.emit(target)
        if was_active != self.active:
            self.active_changed.emit(self.active)

    def _stop_runners(self) -> None:
        self.stopping = True
        for runner in self.runners.values():
            runner.stop()
        self.stopping = False

    def _start_control_timeout(self, stage: str) -> None:
        self.timeout_stage = stage
        self.control_timer.start(self.CONTROL_TIMEOUT_MS)

    def _stop_control_timeout(self) -> None:
        self.timeout_stage = ""
        self.control_timer.stop()

    def _on_control_timeout(self) -> None:
        stage = self.timeout_stage or "operazione di controllo"
        self._abort_session(f"Timeout durante {stage}.")

    def _emit_error(
        self,
        title: str,
        message: str,
        exc: Exception | None = None,
    ) -> None:
        text = f"{message}\n\n{exc}" if exc is not None else message
        self.error_raised.emit(title, text)

    def _on_runner_line(self, runner_name: str, line: str) -> None:
        raise NotImplementedError

    def _on_runner_finished(
        self,
        runner_name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        raise NotImplementedError

    def _abort_session(
        self,
        message: str,
        exc: Exception | None = None,
    ) -> None:
        raise NotImplementedError


class SendTransferController(BaseTransferController):
    code_changed = Signal(object)

    def __init__(
        self,
        *,
        croc_path: str,
        runners: dict[str, CrocRunner],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(
            croc_path=croc_path,
            runners=runners,
            transitions=SEND_TRANSITIONS,
            parent=parent,
        )
        self.session: SendSession | None = None

    def start(self, source_path: Path) -> None:
        if self.active or self.any_running():
            raise RuntimeError("Un trasferimento è già in corso.")

        self._cleanup_session()
        self.session = SendSession(source_path=source_path)
        self._transition(TransferState.PREPARING)
        self.code_changed.emit(None)
        self.status_changed.emit("Calcolo hash SHA-256 del file...")
        QCoreApplication.processEvents()

        try:
            size = source_path.stat().st_size
            validate_filename(source_path.name)
            digest = sha256_file(source_path)
            proposal = create_proposal(
                filename=source_path.name,
                size=size,
                sha256=digest,
            )
            metadata_code = generate_croc_code()
            paths = create_session_paths()

            self.session.proposal = proposal
            self.session.metadata_code = metadata_code
            self.session.paths = paths
            metadata_path = paths.metadata_send / CONTROL_METADATA_NAME
            write_control_file(metadata_path, proposal)
        except Exception as exc:
            self._abort_session("Impossibile preparare il trasferimento.", exc)
            return

        self.code_changed.emit(metadata_code)
        self.progress_preview_changed.emit(proposal.size)
        self.status_changed.emit("Codice generato. Comunicalo al destinatario.")

        try:
            self._transition(TransferState.TRANSFERRING_METADATA)
            self._start_metadata_sender(metadata_path)
            self._start_control_timeout("invio metadati")
        except Exception as exc:
            self._abort_session("Impossibile avviare il trasferimento.", exc)

    def stop(self) -> None:
        if not self.active and not self.any_running():
            return

        self.status_changed.emit("Interruzione dell'invio in corso...")
        self._stop_control_timeout()
        self._stop_runners()
        self.progress_finished.emit(False)
        self._cleanup_session()
        if self.active:
            self._transition(TransferState.CANCELLED)
        self.status_changed.emit("Invio interrotto.")

    def _start_metadata_sender(self, metadata_path: Path) -> None:
        session = self._require_session()
        if not session.metadata_code or not session.paths:
            raise RuntimeError("Codice metadata mancante.")

        self.terminal_line.emit(
            "[metadata] invio informazioni file "
            f"(code-id={code_id(session.metadata_code)})"
        )
        args = croc.build_send_args(metadata_path)
        self.runners["metadata_send"].start(
            args,
            env=croc.build_process_environment(
                session.paths.croc_config,
                secret=session.metadata_code,
            ),
            preview=croc.build_secret_preview(self.croc_path, args),
            sensitive_values=(session.metadata_code,),
        )

    def _start_main_sender(self) -> None:
        session = self._require_session()
        if not session.proposal or not session.paths:
            self._abort_session("Sessione di invio incompleta.")
            return

        self.terminal_line.emit(
            "[main] invio file principale "
            f"(code-id={code_id(session.proposal.main_code)})"
        )
        self.progress_started.emit(session.proposal.size, True)
        args = croc.build_send_args(session.source_path)
        try:
            self.runners["main_send"].start(
                args,
                env=croc.build_process_environment(
                    session.paths.croc_config,
                    secret=session.proposal.main_code,
                ),
                preview=croc.build_secret_preview(self.croc_path, args),
                sensitive_values=(session.proposal.main_code,),
            )
            self._start_control_timeout("attesa connessione destinatario")
        except Exception as exc:
            self.progress_finished.emit(False)
            self._abort_session("Impossibile avviare l'invio principale.", exc)

    def _on_runner_line(self, runner_name: str, line: str) -> None:
        if runner_name != "main_send" or not self.session:
            return

        lowered = line.lower()
        if any(token in lowered for token in ("declin", "reject", "refus", "cancel")):
            self.session.rejected_by_receiver = True

        if "Sending (->" in line:
            self._stop_control_timeout()
            if self.state == TransferState.AWAITING_DECISION:
                self._transition(TransferState.TRANSFERRING_FILE)

        status = croc_status_from_line(line, role="send")
        if status:
            self.status_changed.emit(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress_total_changed.emit(total)

        sample = parse_transfer_progress(line)
        if sample:
            self._stop_control_timeout()
            if self.state == TransferState.AWAITING_DECISION:
                self._transition(TransferState.TRANSFERRING_FILE)
            self.progress_sampled.emit(sample)

    def _on_runner_finished(
        self,
        runner_name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self.stopping or not self.active:
            return

        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if not success:
            if runner_name == "main_send":
                self.progress_finished.emit(False)
                self._abort_session(
                    "Invio non completato. Il destinatario potrebbe aver rifiutato "
                    "il file oppure la connessione potrebbe essere fallita."
                )
            else:
                self._abort_session(
                    f"Processo {runner_name} terminato con errore."
                )
            return

        if runner_name == "metadata_send":
            self._stop_control_timeout()
            self._transition(TransferState.AWAITING_DECISION)
            self.status_changed.emit(
                "Informazioni inviate. Attendo decisione del destinatario..."
            )
            self._start_main_sender()
            return

        if runner_name != "main_send":
            return

        self._stop_control_timeout()
        rejected = bool(self.session and self.session.rejected_by_receiver)
        self.progress_finished.emit(not rejected)
        self._cleanup_session()
        if rejected:
            self._transition(TransferState.REJECTED)
            self.status_changed.emit("Trasferimento rifiutato dal destinatario.")
        else:
            self._transition(TransferState.COMPLETED)
            self.status_changed.emit("Invio completato.")

    def _abort_session(
        self,
        message: str,
        exc: Exception | None = None,
    ) -> None:
        self._stop_control_timeout()
        self._stop_runners()
        self._cleanup_session()
        if self.active:
            self._transition(TransferState.FAILED)
        self.status_changed.emit(message)
        if exc is not None:
            self._emit_error("Errore trasferimento", message, exc)

    def _cleanup_session(self) -> None:
        if self.session:
            cleanup_session_paths(self.session.paths)
        self.session = None

    def _require_session(self) -> SendSession:
        if not self.session:
            raise RuntimeError("Sessione di invio non disponibile.")
        return self.session


class ReceiveTransferController(BaseTransferController):
    MAIN_RECEIVE_DELAY_MS = 750

    def __init__(
        self,
        *,
        croc_path: str,
        runners: dict[str, CrocRunner],
        decision_provider: Callable[[TransferProposal], ReceiveDecision],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(
            croc_path=croc_path,
            runners=runners,
            transitions=RECEIVE_TRANSITIONS,
            parent=parent,
        )
        self.decision_provider = decision_provider
        self.session: ReceiveSession | None = None

        self.receive_size_timer = QTimer(self)
        self.receive_size_timer.setInterval(250)
        self.receive_size_timer.timeout.connect(self._check_receive_size)

    def start(self, metadata_code: str, destination: Path) -> None:
        if self.active or self.any_running():
            raise RuntimeError("Un trasferimento è già in corso.")

        self._cleanup_session()
        self.session = ReceiveSession(
            metadata_code=metadata_code,
            destination=destination,
        )
        self._transition(TransferState.PREPARING)
        self.progress_preview_changed.emit(None)

        try:
            destination.mkdir(parents=True, exist_ok=True)
            self.session.paths = create_session_paths(
                main_receive_parent=destination
            )
        except Exception as exc:
            self._abort_session(
                "Impossibile usare la cartella di destinazione.",
                exc,
                title="Errore destinazione",
            )
            return

        self.status_changed.emit("Ricezione informazioni file...")
        try:
            self._transition(TransferState.TRANSFERRING_METADATA)
            self._start_metadata_receiver()
            self._start_control_timeout("ricezione metadati")
        except Exception as exc:
            self._abort_session(
                "Impossibile avviare la ricezione dei metadati.",
                exc,
            )

    def stop(self) -> None:
        if not self.active and not self.any_running():
            return

        self.status_changed.emit("Interruzione della ricezione in corso...")
        self._stop_control_timeout()
        self._stop_receive_size_monitor()
        self._stop_runners()
        self.progress_finished.emit(False)
        self._cleanup_session()
        if self.active:
            self._transition(TransferState.CANCELLED)
        self.status_changed.emit("Ricezione interrotta.")

    def _start_metadata_receiver(self) -> None:
        session = self._require_session()
        if not session.paths:
            raise RuntimeError("Sessione di ricezione non inizializzata.")

        args = croc.build_receive_args()
        self.terminal_line.emit(
            "[metadata] ricezione informazioni file "
            f"(code-id={code_id(session.metadata_code)})"
        )
        self.runners["metadata_receive"].start(
            args,
            workdir=session.paths.metadata_receive,
            env=croc.build_process_environment(
                session.paths.croc_config,
                secret=session.metadata_code,
            ),
            preview=croc.build_secret_preview(self.croc_path, args),
            sensitive_values=(session.metadata_code,),
        )
        self._start_receive_size_monitor(
            MAX_CONTROL_FILE_BYTES,
            "ricezione metadati",
        )

    def _schedule_main_response(self, accepted: bool) -> None:
        session = self._require_session()
        session.main_response_accepted = accepted
        if accepted:
            self.status_changed.emit(
                "Trasferimento accettato. Attendo il file..."
            )
        else:
            self.status_changed.emit("Comunico il rifiuto al mittente...")

        QTimer.singleShot(
            self.MAIN_RECEIVE_DELAY_MS,
            lambda: self._start_main_receiver(accepted),
        )

    def _start_main_receiver(self, accepted: bool) -> None:
        if not self.active:
            return

        session = self._require_session()
        if not session.paths or not session.proposal:
            self._abort_session("Sessione di ricezione incompleta.")
            return

        self._transition(
            TransferState.TRANSFERRING_FILE
            if accepted
            else TransferState.RESPONDING_TO_DECISION
        )
        args = croc.build_prompted_receive_args()
        self.terminal_line.emit(
            "[main] ricezione file principale "
            f"(code-id={code_id(session.proposal.main_code)})"
        )
        if accepted:
            self.progress_started.emit(session.proposal.size, True)
        try:
            self.runners["main_receive"].start(
                args,
                workdir=session.paths.main_receive,
                env=croc.build_process_environment(
                    session.paths.croc_config,
                    secret=session.proposal.main_code,
                ),
                preview=croc.build_secret_preview(self.croc_path, args),
                sensitive_values=(session.proposal.main_code,),
            )
            if accepted:
                self._start_receive_size_monitor(
                    session.proposal.size,
                    "ricezione file principale",
                )
            answer = "y\n" if accepted else "n\n"
            self.runners["main_receive"].write_stdin(answer, close=True)
            self.terminal_line.emit(
                "[prompt] risposta inviata a croc: "
                + ("accetta" if accepted else "rifiuta")
            )
            self._start_control_timeout("trasferimento principale")
        except Exception as exc:
            self._abort_session(
                "Impossibile avviare la ricezione principale.",
                exc,
            )

    def _on_runner_line(self, runner_name: str, line: str) -> None:
        if runner_name != "main_receive" or not self.session:
            return

        if self.session.main_response_accepted is False:
            return

        status = croc_status_from_line(line, role="receive")
        if status:
            self.status_changed.emit(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress_total_changed.emit(total)

        sample = parse_transfer_progress(line)
        if sample:
            self.progress_sampled.emit(sample)

    def _on_runner_finished(
        self,
        runner_name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self.stopping or not self.active:
            return

        self._stop_receive_size_monitor()
        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if (
            runner_name == "main_receive"
            and self.session
            and self.session.main_response_accepted is False
        ):
            self._stop_control_timeout()
            self._cleanup_session()
            self._transition(TransferState.REJECTED)
            self.status_changed.emit("Trasferimento rifiutato.")
            return

        if not success:
            if runner_name == "main_receive":
                self.progress_finished.emit(False)
            self._abort_session(
                f"Processo {runner_name} terminato con errore."
            )
            return

        if runner_name == "metadata_receive":
            self._stop_control_timeout()
            self._handle_received_metadata()
            return

        if runner_name == "main_receive":
            self._stop_control_timeout()
            self._transition(TransferState.VERIFYING)
            self._handle_main_received()

    def _handle_received_metadata(self) -> None:
        session = self._require_session()
        if not session.paths:
            self._abort_session(
                "Metadati ricevuti ma sessione non disponibile."
            )
            return

        try:
            metadata_path = (
                session.paths.metadata_receive / CONTROL_METADATA_NAME
            )
            if not metadata_path.is_file():
                raise FileNotFoundError(
                    self._missing_metadata_message(metadata_path)
                )

            session.proposal = read_proposal(metadata_path)
            self.progress_preview_changed.emit(session.proposal.size)
            self._transition(TransferState.AWAITING_DECISION)
            decision = self.decision_provider(session.proposal)
            if not decision.accepted:
                self._schedule_main_response(False)
                return
            if decision.target is None:
                raise RuntimeError("Destinazione del trasferimento mancante.")

            try:
                decision.target.parent.mkdir(parents=True, exist_ok=True)
                ensure_receive_capacity(
                    session.paths.main_receive,
                    session.proposal.size,
                )
                if (
                    decision.target.parent.stat().st_dev
                    != session.paths.main_receive.stat().st_dev
                ):
                    ensure_receive_capacity(
                        decision.target.parent,
                        session.proposal.size,
                    )
            except OSError as exc:
                self._emit_error("Spazio insufficiente", str(exc))
                self._schedule_main_response(False)
                return

            session.target_path = decision.target
            session.target_overwrite = decision.overwrite
            self._schedule_main_response(True)
        except Exception as exc:
            self._abort_session("Metadati ricevuti non validi.", exc)

    def _handle_main_received(self) -> None:
        session = self._require_session()
        if not session.paths or not session.proposal or not session.target_path:
            self._abort_session(
                "File ricevuto ma sessione non disponibile."
            )
            return

        source = received_path(
            session.paths.main_receive,
            session.proposal.filename,
        )
        try:
            verify_received_file(source, session.proposal)
            saved_path = move_verified_file(
                source,
                session.target_path,
                overwrite=session.target_overwrite,
            )
        except Exception as exc:
            self._abort_session(
                "Verifica o salvataggio del file non riusciti.",
                exc,
            )
            return

        self.progress_finished.emit(True)
        self._cleanup_session()
        self._transition(TransferState.COMPLETED)
        self.status_changed.emit(f"Ricezione completata: {saved_path}")

    def _abort_session(
        self,
        message: str,
        exc: Exception | None = None,
        *,
        title: str = "Errore trasferimento",
    ) -> None:
        accepted = bool(
            self.session and self.session.main_response_accepted is True
        )
        self._stop_control_timeout()
        self._stop_receive_size_monitor()
        self._stop_runners()
        if accepted:
            self.progress_finished.emit(False)
        self._cleanup_session()
        if self.active:
            self._transition(TransferState.FAILED)
        self.status_changed.emit(message)
        if exc is not None:
            self._emit_error(title, message, exc)

    def _start_receive_size_monitor(self, limit: int, stage: str) -> None:
        session = self._require_session()
        session.receive_size_limit = limit
        session.receive_size_stage = stage
        self.receive_size_timer.start()

    def _stop_receive_size_monitor(self) -> None:
        self.receive_size_timer.stop()
        if self.session:
            self.session.receive_size_limit = None
            self.session.receive_size_stage = ""

    def _check_receive_size(self) -> None:
        session = self.session
        if (
            not self.active
            or not session
            or not session.paths
            or session.receive_size_limit is None
        ):
            self._stop_receive_size_monitor()
            return

        if self.runners["metadata_receive"].is_running():
            directory = session.paths.metadata_receive
        elif self.runners["main_receive"].is_running():
            directory = session.paths.main_receive
        else:
            return

        try:
            received_bytes = directory_payload_size(directory)
        except Exception as exc:
            self._abort_session(
                "Contenuto temporaneo non valido durante "
                f"{session.receive_size_stage}.",
                exc,
            )
            return

        if received_bytes > session.receive_size_limit:
            self._abort_session(
                f"Ricezione interrotta durante {session.receive_size_stage}: "
                "dimensione superiore a quella consentita.",
                ValueError(
                    f"Ricevuti {received_bytes} byte, "
                    f"limite {session.receive_size_limit} byte."
                ),
            )

    def _cleanup_session(self) -> None:
        self._stop_receive_size_monitor()
        if self.session:
            cleanup_session_paths(self.session.paths)
        self.session = None

    def _require_session(self) -> ReceiveSession:
        if not self.session:
            raise RuntimeError("Sessione di ricezione non disponibile.")
        return self.session

    @staticmethod
    def _missing_metadata_message(metadata_path: Path) -> str:
        directory = metadata_path.parent
        try:
            files = sorted(path.name for path in directory.iterdir())
        except OSError:
            files = []

        found = ", ".join(files) if files else "nessun file"
        return (
            f"File metadati atteso non trovato: {metadata_path}\n"
            f"Contenuto della directory temporanea: {found}\n"
            "Possibili cause: codice non valido, trasferimento interrotto o "
            "configurazione croc incompatibile."
        )
