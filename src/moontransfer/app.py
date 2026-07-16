from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from moontransfer import croc
from moontransfer.desktop import open_folder
from moontransfer.files import (
    CONTROL_METADATA_NAME,
    DestinationConflict,
    SessionPaths,
    check_destination,
    cleanup_session_paths,
    create_session_paths,
    move_verified_file,
    received_path,
    sha256_file,
    unique_destination_path,
    verify_received_file,
)
from moontransfer.messages import croc_status_from_line
from moontransfer.progress import (
    format_file_size,
    parse_announced_transfer_total,
    parse_transfer_progress,
)
from moontransfer.protocol import (
    TransferProposal,
    code_id,
    create_proposal,
    generate_croc_code,
    read_proposal,
    write_control_file,
)
from moontransfer.runner import CrocRunner
from moontransfer.widgets import (
    StatusLabel,
    TechnicalOutput,
    TransferProgressWidget,
    add_expandable_output,
)


class SendTab(QWidget):
    CONTROL_TIMEOUT_MS = 15 * 60 * 1000

    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.croc_path = croc_path
        self.last_code: str | None = None
        self.metadata_code: str | None = None
        self.source_path: Path | None = None
        self.paths: SessionPaths | None = None
        self.proposal: TransferProposal | None = None
        self.session_active = False
        self.stopping = False
        self.timeout_stage = ""
        self.main_rejected_by_receiver = False

        self.status_label = StatusLabel("Pronto a inviare un file.")
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Seleziona un file da inviare")
        self.browse_button = QPushButton("Sfoglia...")
        self.file_info_label = QLabel("Nessun file selezionato.")
        self.file_info_label.setWordWrap(True)
        self.file_info_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.start_button = QPushButton("Invia")
        self.start_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.code_edit = QLineEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setPlaceholderText("Il codice apparirà qui")
        self.copy_button = QPushButton("Copia codice")
        self.copy_button.setEnabled(False)

        self.progress = TransferProgressWidget("Inviato")
        self.output = TechnicalOutput()
        self.terminal = self.output.terminal
        self.runners = {
            "metadata_send": self._make_runner("metadata_send"),
            "main_send": self._make_runner("main_send"),
        }
        self.control_timer = QTimer(self)
        self.control_timer.setSingleShot(True)
        self.control_timer.timeout.connect(self._on_control_timeout)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.browse_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)
        control_row.addWidget(QLabel("Codice:"))
        control_row.addWidget(self.code_edit, 1)
        control_row.addWidget(self.copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(file_row)
        layout.addWidget(self.file_info_label)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.browse_button.clicked.connect(self._browse_file)
        self.file_edit.textChanged.connect(self._refresh_file_info)
        self.start_button.clicked.connect(self._start_send)
        self.stop_button.clicked.connect(self._stop_send)
        self.copy_button.clicked.connect(self._copy_code)
        self._refresh_file_info()

    def stop_active_transfers(self) -> None:
        if self._any_running():
            self.stopping = True
            for runner in self.runners.values():
                runner.stop()
            self.stopping = False

        if self.session_active:
            self.session_active = False
            self._stop_control_timeout()
            self._cleanup_session()
            self.progress.finish(success=False)
            self._set_running(False)

    def _make_runner(self, name: str) -> CrocRunner:
        runner = CrocRunner(
            self.croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )
        runner.on_line = lambda line, role=name: self._on_croc_line(role, line)
        runner.on_finished = (
            lambda exit_code, exit_status, role=name: self._on_runner_finished(
                role,
                exit_code,
                exit_status,
            )
        )
        return runner

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona file da inviare",
            str(Path.home()),
        )
        if path:
            self.file_edit.setText(path)
            self._refresh_file_info()

    def _selected_file(self) -> Path | None:
        path_text = self.file_edit.text().strip()
        if not path_text:
            return None
        return Path(path_text)

    def _has_valid_file(self) -> bool:
        path = self._selected_file()
        return bool(path and path.is_file())

    def _any_running(self) -> bool:
        return any(runner.is_running() for runner in self.runners.values())

    def _refresh_file_info(self) -> None:
        path = self._selected_file()
        if not path:
            self.file_info_label.setText("Nessun file selezionato.")
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            return

        if not path.is_file():
            self.file_info_label.setText("Il percorso selezionato non è un file valido.")
            self.start_button.setEnabled(False)
            self.progress.set_total_preview(None)
            return

        try:
            size_bytes = path.stat().st_size
            size = format_file_size(size_bytes)
        except OSError:
            size_bytes = None
            size = "dimensione non disponibile"

        self.file_info_label.setText(f"File: {path.name} - {size}")
        self.progress.set_total_preview(size_bytes)
        if not self._any_running():
            self.start_button.setEnabled(True)
            self.status_label.setText("File selezionato. Premi Invia per generare il codice.")

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(False if running else self._has_valid_file())
        self.stop_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.file_edit.setEnabled(not running)
        self.copy_button.setEnabled(bool(self.last_code))

    def _stop_send(self) -> None:
        self.status_label.setText("Interruzione dell'invio in corso...")
        self.stop_active_transfers()
        self.status_label.setText("Invio interrotto.")

    def _start_send(self) -> None:
        path = self._selected_file()

        if not path or not path.is_file():
            self.status_label.setText("Seleziona un file valido prima di inviare.")
            QMessageBox.warning(self, "File non valido", "Seleziona un file valido.")
            return

        self._cleanup_session()
        self.source_path = path
        self.last_code = None
        self.metadata_code = None
        self.proposal = None
        self.main_rejected_by_receiver = False
        self.code_edit.clear()
        self.copy_button.setEnabled(False)
        self._set_running(True)

        self.status_label.setText("Calcolo hash SHA-256 del file...")
        QApplication.processEvents()

        try:
            size = path.stat().st_size
            digest = sha256_file(path)
            self.proposal = create_proposal(
                filename=path.name,
                size=size,
                sha256=digest,
            )
            self.metadata_code = generate_croc_code()
            self.paths = create_session_paths()
            metadata_path = self.paths.metadata_send / CONTROL_METADATA_NAME
            write_control_file(metadata_path, self.proposal)
        except Exception as exc:
            self._abort_session("Impossibile preparare il trasferimento.", exc)
            return

        self.session_active = True
        self.last_code = self.metadata_code
        self.code_edit.setText(self.metadata_code)
        self.copy_button.setEnabled(True)
        self.progress.set_total_preview(self.proposal.size)
        self.status_label.setText(
            "Codice generato. Comunicalo al destinatario."
        )

        try:
            self._start_metadata_sender(metadata_path)
            self._start_control_timeout(
                "invio metadati",
                self.CONTROL_TIMEOUT_MS,
            )
        except Exception as exc:
            self._abort_session("Impossibile avviare il trasferimento.", exc)

    def _start_metadata_sender(self, metadata_path: Path) -> None:
        if not self.metadata_code or not self.paths:
            raise RuntimeError("Codice metadata mancante.")

        self.terminal.append_line(
            f"[metadata] invio informazioni file (code-id={code_id(self.metadata_code)})"
        )
        args = croc.build_send_args(metadata_path)
        self.runners["metadata_send"].start(
            args,
            env=croc.build_process_environment(
                self.paths.croc_config,
                secret=self.metadata_code,
            ),
            preview=croc.build_secret_preview(self.croc_path, args),
        )

    def _start_main_sender(self) -> None:
        if not self.session_active:
            return

        if not self.source_path or not self.proposal or not self.paths:
            self._abort_session("Sessione di invio incompleta.")
            return

        self.terminal.append_line(
            f"[main] invio file principale (code-id={code_id(self.proposal.main_code)})"
        )
        self.progress.start(total_bytes=self.proposal.size, exact_total=True)
        args = croc.build_send_args(self.source_path)
        try:
            self.runners["main_send"].start(
                args,
                env=croc.build_process_environment(
                    self.paths.croc_config,
                    secret=self.proposal.main_code,
                ),
                preview=croc.build_secret_preview(self.croc_path, args),
            )
            self._start_control_timeout(
                "attesa connessione destinatario",
                self.CONTROL_TIMEOUT_MS,
            )
        except Exception as exc:
            self.progress.finish(success=False)
            self._abort_session("Impossibile avviare l'invio principale.", exc)
            return

    def _copy_code(self) -> None:
        if self.last_code:
            QApplication.clipboard().setText(self.last_code)
            self.status_label.setText("Codice copiato negli appunti.")
            self.terminal.append_line()
            self.terminal.append_line("[clipboard] codice copiato")

    def _on_croc_line(self, runner_name: str, line: str) -> None:
        if runner_name != "main_send":
            return

        lowered = line.lower()
        if any(token in lowered for token in ("declin", "reject", "refus", "cancel")):
            self.main_rejected_by_receiver = True

        if "Sending (->" in line:
            self._stop_control_timeout()

        status = croc_status_from_line(line, role="send")
        if status:
            self.status_label.setText(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress.set_total(total)

        sample = parse_transfer_progress(line)
        if sample:
            self._stop_control_timeout()
            self.progress.apply_sample(sample)

    def _on_runner_finished(
        self,
        runner_name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self.stopping or not self.session_active:
            return

        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if not success:
            if runner_name == "main_send":
                self.progress.finish(success=False)
                self._abort_session(
                    "Invio non completato. Il destinatario potrebbe aver rifiutato "
                    "il file oppure la connessione potrebbe essere fallita."
                )
            else:
                self._abort_session(
                    f"Processo {runner_name} terminato con errore.",
                )
            return

        if runner_name == "metadata_send":
            self._stop_control_timeout()
            self.status_label.setText(
                "Informazioni inviate. Attendo decisione del destinatario..."
            )
            self._start_main_sender()
            return

        if runner_name == "main_send":
            self._stop_control_timeout()
            if self.main_rejected_by_receiver:
                self.progress.finish(success=False)
                self.status_label.setText("Trasferimento rifiutato dal destinatario.")
                self.session_active = False
                self._cleanup_session()
                self._set_running(False)
                return
            self.progress.finish(success=True)
            self.status_label.setText("Invio completato.")
            self.session_active = False
            self._cleanup_session()
            self._set_running(False)

    def _abort_session(self, message: str, exc: Exception | None = None) -> None:
        self.stopping = True
        self._stop_control_timeout()
        for runner in self.runners.values():
            runner.stop()
        self.stopping = False
        self.session_active = False
        self._cleanup_session()
        self._set_running(False)
        self.status_label.setText(message)
        if exc is not None:
            QMessageBox.critical(self, "Errore trasferimento", f"{message}\n\n{exc}")

    def _start_control_timeout(self, stage: str, milliseconds: int) -> None:
        self.timeout_stage = stage
        self.control_timer.start(milliseconds)

    def _stop_control_timeout(self) -> None:
        self.timeout_stage = ""
        self.control_timer.stop()

    def _on_control_timeout(self) -> None:
        stage = self.timeout_stage or "operazione di controllo"
        self._abort_session(f"Timeout durante {stage}.")

    def _cleanup_session(self) -> None:
        cleanup_session_paths(self.paths)
        self.paths = None
        self.proposal = None
        self.metadata_code = None
        self.main_rejected_by_receiver = False


class ReceiveTab(QWidget):
    CONTROL_TIMEOUT_MS = 15 * 60 * 1000
    MAIN_RECEIVE_DELAY_MS = 750

    def __init__(self, croc_path: str) -> None:
        super().__init__()
        self.croc_path = croc_path
        self.paths: SessionPaths | None = None
        self.proposal: TransferProposal | None = None
        self.target_path: Path | None = None
        self.target_overwrite = False
        self.session_active = False
        self.stopping = False
        self.timeout_stage = ""
        self.main_response_accepted: bool | None = None

        self.status_label = StatusLabel("Pronto a ricevere un file.")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Incolla il codice ricevuto")
        self.dest_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.dest_button = QPushButton("Scegli...")
        self.open_dest_button = QPushButton("Apri cartella")
        self.start_button = QPushButton("Ricevi")
        self.start_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.progress = TransferProgressWidget("Scaricato")
        self.output = TechnicalOutput()
        self.terminal = self.output.terminal
        self.runners = {
            "metadata_receive": self._make_runner("metadata_receive"),
            "main_receive": self._make_runner("main_receive"),
        }
        self.control_timer = QTimer(self)
        self.control_timer.setSingleShot(True)
        self.control_timer.timeout.connect(self._on_control_timeout)

        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("Codice:"))
        code_row.addWidget(self.code_edit, 1)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Destinazione:"))
        dest_row.addWidget(self.dest_edit, 1)
        dest_row.addWidget(self.dest_button)
        dest_row.addWidget(self.open_dest_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(code_row)
        layout.addLayout(dest_row)
        layout.addLayout(control_row)
        layout.addWidget(self.progress)
        add_expandable_output(layout, self.output)

        self.code_edit.textChanged.connect(self._refresh_receive_actions)
        self.dest_edit.textChanged.connect(self._refresh_receive_actions)
        self.dest_button.clicked.connect(self._choose_destination)
        self.open_dest_button.clicked.connect(self._open_destination)
        self.start_button.clicked.connect(self._start_receive)
        self.stop_button.clicked.connect(self._stop_receive)
        self._refresh_receive_actions()

    def stop_active_transfers(self) -> None:
        if self._any_running():
            self.stopping = True
            for runner in self.runners.values():
                runner.stop()
            self.stopping = False

        if self.session_active:
            self.session_active = False
            self._stop_control_timeout()
            self._cleanup_session()
            self.progress.finish(success=False)
            self._set_running(False)

    def _make_runner(self, name: str) -> CrocRunner:
        runner = CrocRunner(
            self.croc_path,
            append_text=self.terminal.append_text,
            append_line=self.terminal.append_line,
        )
        runner.on_line = lambda line, role=name: self._on_croc_line(role, line)
        runner.on_finished = (
            lambda exit_code, exit_status, role=name: self._on_runner_finished(
                role,
                exit_code,
                exit_status,
            )
        )
        return runner

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Scegli cartella di destinazione",
            self.dest_edit.text().strip() or str(Path.home()),
        )
        if path:
            self.dest_edit.setText(path)
            self.status_label.setText("Cartella di destinazione selezionata.")
            self._refresh_receive_actions()

    def _destination(self) -> Path:
        return Path(self.dest_edit.text().strip())

    def _can_open_destination(self) -> bool:
        destination_text = self.dest_edit.text().strip()
        return bool(destination_text and Path(destination_text).is_dir())

    def _can_start_receive(self) -> bool:
        return bool(self.code_edit.text().strip() and self.dest_edit.text().strip())

    def _any_running(self) -> bool:
        return any(runner.is_running() for runner in self.runners.values())

    def _refresh_receive_actions(self) -> None:
        running = self._any_running()
        self.start_button.setEnabled(not running and self._can_start_receive())
        self.open_dest_button.setEnabled(
            self._can_open_destination() and not running
        )

    def _open_destination(self) -> None:
        destination = self._destination()
        if not destination.is_dir():
            self.status_label.setText("La cartella di destinazione non esiste ancora.")
            QMessageBox.warning(
                self,
                "Cartella non disponibile",
                "La cartella di destinazione non esiste ancora.",
            )
            self._refresh_receive_actions()
            return

        result = open_folder(destination)
        if result.opened:
            self.status_label.setText("Cartella di destinazione aperta.")
        else:
            self.status_label.setText("Impossibile aprire la cartella di destinazione.")
            details = f"\n\nDettaglio tecnico:\n{result.error}" if result.error else ""
            QMessageBox.warning(
                self,
                "Apertura non riuscita",
                "Non riesco ad aprire la cartella con il file manager del sistema."
                + details,
            )

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(False if running else self._can_start_receive())
        self.stop_button.setEnabled(running)
        self.code_edit.setEnabled(not running)
        self.dest_edit.setEnabled(not running)
        self.dest_button.setEnabled(not running)
        self.open_dest_button.setEnabled(not running and self._can_open_destination())

    def _stop_receive(self) -> None:
        self.status_label.setText("Interruzione della ricezione in corso...")
        self.stop_active_transfers()
        self.status_label.setText("Ricezione interrotta.")

    def _start_receive(self) -> None:
        code = self.code_edit.text().strip()
        destination_text = self.dest_edit.text().strip()

        if not code:
            self.status_label.setText("Inserisci il codice ricevuto prima di avviare la ricezione.")
            QMessageBox.warning(self, "Codice mancante", "Incolla il codice ricevuto.")
            return

        if not destination_text:
            self.status_label.setText("Scegli una cartella di destinazione.")
            QMessageBox.warning(
                self,
                "Destinazione mancante",
                "Scegli una cartella di destinazione.",
            )
            return

        destination = Path(destination_text)

        try:
            destination.mkdir(parents=True, exist_ok=True)
            self.paths = create_session_paths()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Errore destinazione",
                f"Impossibile usare la cartella di destinazione:\n{exc}",
            )
            self.status_label.setText("Impossibile usare la cartella di destinazione.")
            self._refresh_receive_actions()
            return

        self.proposal = None
        self.target_path = None
        self.target_overwrite = False
        self.main_response_accepted = None
        self.session_active = True
        self.progress.set_total_preview(None)
        self._set_running(True)
        self.status_label.setText("Ricezione informazioni file...")

        try:
            self._start_metadata_receiver(code)
            self._start_control_timeout(
                "ricezione metadati",
                self.CONTROL_TIMEOUT_MS,
            )
        except Exception as exc:
            self._abort_session("Impossibile avviare la ricezione dei metadati.", exc)

    def _start_metadata_receiver(self, code: str) -> None:
        if not self.paths:
            raise RuntimeError("Sessione di ricezione non inizializzata.")

        args = croc.build_receive_args()
        self.terminal.append_line(
            f"[metadata] ricezione informazioni file (code-id={code_id(code)})"
        )
        self.runners["metadata_receive"].start(
            args,
            workdir=self.paths.metadata_receive,
            env=croc.build_process_environment(
                self.paths.croc_config,
                secret=code,
            ),
            preview=croc.build_secret_preview(self.croc_path, args),
        )

    def _schedule_main_response(self, accepted: bool) -> None:
        self.main_response_accepted = accepted
        if accepted:
            self.status_label.setText("Trasferimento accettato. Attendo il file...")
        else:
            self.status_label.setText("Comunico il rifiuto al mittente...")

        QTimer.singleShot(
            self.MAIN_RECEIVE_DELAY_MS,
            lambda: self._start_main_receiver(accepted),
        )

    def _start_main_receiver(self, accepted: bool) -> None:
        if not self.session_active:
            return

        if not self.paths or not self.proposal:
            self._abort_session("Sessione di ricezione incompleta.")
            return

        args = croc.build_prompted_receive_args()
        self.terminal.append_line(
            f"[main] ricezione file principale (code-id={code_id(self.proposal.main_code)})"
        )
        if accepted:
            self.progress.start(total_bytes=self.proposal.size, exact_total=True)
        try:
            self.runners["main_receive"].start(
                args,
                workdir=self.paths.main_receive,
                env=croc.build_process_environment(
                    self.paths.croc_config,
                    secret=self.proposal.main_code,
                ),
                preview=croc.build_secret_preview(self.croc_path, args),
            )
            answer = "y\n" if accepted else "n\n"
            self.runners["main_receive"].write_stdin(answer, close=True)
            self.terminal.append_line(
                "[prompt] risposta inviata a croc: "
                + ("accetta" if accepted else "rifiuta")
            )
            self._start_control_timeout(
                "trasferimento principale",
                self.CONTROL_TIMEOUT_MS,
            )
        except Exception as exc:
            if accepted:
                self.progress.finish(success=False)
            self._abort_session("Impossibile avviare la ricezione principale.", exc)

    def _on_croc_line(self, runner_name: str, line: str) -> None:
        if runner_name != "main_receive":
            return

        if self.main_response_accepted is False:
            return

        status = croc_status_from_line(line, role="receive")
        if status:
            self.status_label.setText(status)

        total = parse_announced_transfer_total(line)
        if total is not None:
            self.progress.set_total(total)

        sample = parse_transfer_progress(line)
        if sample:
            self.progress.apply_sample(sample)

    def _on_runner_finished(
        self,
        runner_name: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self.stopping or not self.session_active:
            return

        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if runner_name == "main_receive" and self.main_response_accepted is False:
            self._stop_control_timeout()
            self.status_label.setText("Trasferimento rifiutato.")
            self.session_active = False
            self._cleanup_session()
            self._set_running(False)
            return

        if not success:
            if runner_name == "main_receive":
                self.progress.finish(success=False)
            self._abort_session(
                f"Processo {runner_name} terminato con errore.",
            )
            return

        if runner_name == "metadata_receive":
            self._stop_control_timeout()
            self._handle_received_metadata()
            return

        if runner_name == "main_receive":
            self._stop_control_timeout()
            self._handle_main_received()

    def _handle_received_metadata(self) -> None:
        if not self.paths:
            self._abort_session("Metadati ricevuti ma sessione non disponibile.")
            return

        try:
            metadata_path = self.paths.metadata_receive / CONTROL_METADATA_NAME
            if not metadata_path.is_file():
                raise FileNotFoundError(self._missing_metadata_message(metadata_path))

            self.proposal = read_proposal(metadata_path)
            self.progress.set_total_preview(self.proposal.size)
            accepted, target, overwrite = self._choose_transfer_action(self.proposal)
            if not accepted:
                self._schedule_main_response(False)
                return
            self.target_path = target
            self.target_overwrite = overwrite
            self._schedule_main_response(True)
        except Exception as exc:
            self._abort_session("Metadati ricevuti non validi.", exc)

    def _missing_metadata_message(self, metadata_path: Path) -> str:
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

    def _choose_transfer_action(
        self,
        proposal: TransferProposal,
    ) -> tuple[bool, Path | None, bool]:
        destination = self._destination()
        details = (
            f"Nome: {proposal.filename}\n"
            f"Dimensione: {format_file_size(proposal.size)}\n"
            f"SHA-256: {proposal.sha256}"
        )
        check = check_destination(proposal, destination)

        if check.conflict == DestinationConflict.NONE:
            answer = QMessageBox.question(
                self,
                "Accetta trasferimento",
                f"{details}\n\nVuoi ricevere questo file?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                return True, check.path, False
            return False, None, False

        if check.conflict == DestinationConflict.IDENTICAL:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("File già presente")
            box.setText(
                f"{details}\n\nNella destinazione esiste già lo stesso file."
            )
            skip_button = box.addButton(
                "Non scaricare",
                QMessageBox.ButtonRole.RejectRole,
            )
            receive_button = box.addButton(
                "Scarica comunque",
                QMessageBox.ButtonRole.AcceptRole,
            )
            box.setDefaultButton(skip_button)
            box.exec()

            if box.clickedButton() is receive_button:
                return True, check.path, True
            return False, None, False

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("File già esistente")
        box.setText(
            f"{details}\n\n"
            "Nella destinazione esiste già un file con lo stesso nome, "
            "ma il contenuto è diverso."
        )
        overwrite_button = box.addButton(
            "Sovrascrivi",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        rename_button = box.addButton(
            "Salva con altro nome",
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(
            "Rifiuta",
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(rename_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite_button:
            return True, check.path, True

        if clicked is rename_button:
            suggested = unique_destination_path(check.path)
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "Salva file come",
                str(suggested),
            )
            if selected:
                target = Path(selected)
                return True, target, target.exists()

        return False, None, False

    def _handle_main_received(self) -> None:
        if not self.paths or not self.proposal or not self.target_path:
            self._abort_session("File ricevuto ma sessione non disponibile.")
            return

        source = received_path(self.paths.main_receive, self.proposal.filename)
        try:
            verify_received_file(source, self.proposal)
            saved_path = move_verified_file(
                source,
                self.target_path,
                overwrite=self.target_overwrite,
            )
        except Exception as exc:
            self.progress.finish(success=False)
            self._abort_session("Verifica o salvataggio del file non riusciti.", exc)
            return

        self.progress.finish(success=True)
        self.status_label.setText(f"Ricezione completata: {saved_path}")
        self.session_active = False
        self._cleanup_session()
        self._set_running(False)

    def _abort_session(self, message: str, exc: Exception | None = None) -> None:
        self.stopping = True
        self._stop_control_timeout()
        for runner in self.runners.values():
            runner.stop()
        self.stopping = False
        self.session_active = False
        self._cleanup_session()
        self._set_running(False)
        self.status_label.setText(message)
        if exc is not None:
            QMessageBox.critical(self, "Errore trasferimento", f"{message}\n\n{exc}")

    def _start_control_timeout(self, stage: str, milliseconds: int) -> None:
        self.timeout_stage = stage
        self.control_timer.start(milliseconds)

    def _stop_control_timeout(self) -> None:
        self.timeout_stage = ""
        self.control_timer.stop()

    def _on_control_timeout(self) -> None:
        stage = self.timeout_stage or "operazione di controllo"
        self._abort_session(f"Timeout durante {stage}.")

    def _cleanup_session(self) -> None:
        cleanup_session_paths(self.paths)
        self.paths = None
        self.proposal = None
        self.target_path = None
        self.target_overwrite = False
        self.main_response_accepted = None


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoonTransfer")

        croc_path = croc.find_executable()
        if not croc_path:
            QMessageBox.critical(
                self,
                "croc non trovato",
                "Esegui prima: uv run python tools/fetch_croc.py",
            )
            raise SystemExit(1)

        tabs = QTabWidget()
        self.send_tab = SendTab(croc_path)
        self.receive_tab = ReceiveTab(croc_path)
        tabs.addTab(self.send_tab, "Invia")
        tabs.addTab(self.receive_tab, "Ricevi")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.resize(900, self.sizeHint().height())

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self.send_tab.stop_active_transfers()
        self.receive_tab.stop_active_transfers()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MoonTransfer")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
