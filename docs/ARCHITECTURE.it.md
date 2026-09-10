# Architettura e responsabilità

[English](ARCHITECTURE.md) | [MoonTransfer](../README.it.md)

## Indice

- [Confini tra piattaforme](#confini-tra-piattaforme)
- [Dove intervenire](#dove-intervenire)
- [Note architetturali](#note-architetturali)
- [Target Android sperimentale](#target-android-sperimentale)

## Confini tra piattaforme

- **Condiviso, senza Qt:** `src/moontransfer/codes.py` estrae e normalizza i codici; `protocol.py`, `payload.py`, `files.py`, `croc.py`, `progress.py`, `messages.py`, `build_info.py` e `cancellation.py` definiscono i contratti riutilizzati.
- **Desktop:** `app.py`, `widgets.py`, `transfer.py`, `runner.py`, `tasks.py` e `desktop.py` contengono GUI Qt, controller, processi e integrazione desktop; non sono il runtime Android.
- **Android:** in `android/app/moontransfer_android/`, `application.py` coordina la GUI; `moontransfer.kv`, `widgets.py` e `theme.py` definiscono l'aspetto; `sender.py`, `receiver.py` e il servizio gestiscono le sessioni con `subprocess.Popen`. `sharing.py`, `documents.py` e `storage.py` gestiscono intent, URI e salvataggio. `app_state.py` e `ui_state.py` separano stato e presentazione.
- **Integrazione nativa:** i sorgenti Java sotto `android/` e i moduli `android_runtime.py`, `service_client.py`, `service_protocol.py`, `service.py`, `transfer_service.py` collegano activity, foreground service e notifica.
- **Distribuzione:** `tools/android_signing.py` isola firma e verifica; `android/release.toml` coordina il versionCode; `tools/release_assets.py` valida l'insieme dei pacchetti della release. La [guida alle release](RELEASING.it.md) descrive i due workflow.

Questa è una mappa delle responsabilità, non un inventario esaustivo dei file.


## Dove intervenire

Usa i confini già presenti tra i moduli quando scegli dove applicare una
modifica:

- `src/moontransfer/app.py`: entry point dell'applicazione, finestra principale,
  tab di invio, tab di ricezione, validazione degli input, dialoghi utente e
  collegamento degli eventi dei controller alla GUI.
- `src/moontransfer/assets/`: risorse visive versionate condivise dalla
  documentazione del progetto e dall'applicazione. `branding/` contiene il logo
  principale; `icons/` contiene il PNG sorgente incluso nel pacchetto come
  icona dell'applicazione.
- `src/moontransfer/resources.py`: percorsi stabili verso le risorse visive
  pacchettizzate, validi sia dai sorgenti sia nei bundle PyInstaller.
- `src/moontransfer/build_info.py`: identità runtime della build validata e
  diagnostica sicura e copiabile condivisa da desktop e Android.
- `src/moontransfer/transfer.py`: stati espliciti del trasferimento, controller
  di invio e ricezione, ciclo di vita della sessione, coordinamento di processi
  e timeout, flusso dei metadati, operazioni sui payload in background, limiti
  di ricezione, verifica finale e cleanup.
- `src/moontransfer/tasks.py`: worker `QThread` annullabile usato per
  inventario, confronto della destinazione, verifica finale e copie tra
  filesystem senza bloccare l'event loop della GUI.
- `src/moontransfer/cancellation.py`: eccezione di annullamento indipendente da
  Qt e condivisa tra worker in background e operazioni sui file.
- `src/moontransfer/widgets.py`: widget Qt riutilizzabili come etichetta di
  stato, pannello dettagli tecnici, vista output in stile terminale e widget di
  progresso del trasferimento.
- `src/moontransfer/croc.py`: ricerca dell'eseguibile `croc`, argomenti dei
  comandi, variabili d'ambiente per i codici di trasferimento, configurazione
  `croc` isolata e anteprime sicure dei comandi nei log.
- `src/moontransfer/protocol.py`: formato dei metadati di controllo di
  MoonTransfer, versioni del protocollo, codici generati, manifest del payload
  con limiti espliciti, validazione portabile dei percorsi, validazione SHA-256
  e regole di lettura/scrittura del JSON dei metadati.
- `src/moontransfer/payload.py`: inventario dell'albero sorgente, rilevamento
  delle modifiche, confronto con la destinazione, verifica esatta dell'albero
  ricevuto e pubblicazione sicura di payload con uno o più elementi principali.
- `src/moontransfer/files.py`: directory temporanee di sessione, primitive per
  la destinazione, fingerprint stabili, hashing SHA-256 annullabile, nomi
  univoci per file e cartelle e spostamento tra filesystem.
- `src/moontransfer/progress.py`: parsing dell'output di progresso di `croc`,
  aggregazione dei campioni per file e formattazione di dimensioni, velocità,
  tempo trascorso e tempo rimanente.
- `src/moontransfer/messages.py`: messaggi di stato rivolti all'utente derivati
  dall'output e dal risultato dei processi.
- `src/moontransfer/runner.py`: ciclo di vita di `QProcess`, separazione di
  stdout/stderr, terminazione dei processi e risposte su stdin ai prompt di
  `croc`.
- `src/moontransfer/desktop.py`: apertura cartelle tramite il file manager della
  piattaforma e pulizia dell'ambiente usato per i comandi desktop esterni.
- `tools/build.py`: orchestrazione comune della build PyInstaller.
- `tools/build_metadata.py`: risoluzione di versione e commit della build e
  generazione deterministica dei metadati incorporati nelle applicazioni
  pacchettizzate.
- `tools/fetch_croc.py`: selezione della release `croc` fissata, download,
  verifica checksum, estrazione archivio e installazione del binario incluso nel
  bundle.
- `tools/check_latest_croc.py`: controlli di compatibilità con l'ultima release
  upstream di `croc`.
- `tools/package_release.py`: controllo host/target, verifica della versione di
  `croc` inclusa e creazione degli archivi di release versionati con licenza e
  documentazione.
- `tools/prepare_android.py`: generazione deterministica dei sorgenti Android e
  identità di build incorporata.
- `tools/android.py`: diagnostica dell'host Android, preparazione dei sorgenti,
  orchestrazione di Buildozer, validazione dell'APK e preparazione
  dell'artefatto versionato.
- `scripts/build.sh` e `scripts/build.ps1`: wrapper di build rivolti all'utente
  e controlli dei prerequisiti.
- `scripts/android.sh`: wrapper con dipendenze bloccate, indipendente dalla
  directory corrente, per l'ambiente Android isolato.
- `MoonTransfer.spec`: configurazione di packaging `onedir` PyInstaller,
  compreso il bundle applicazione nativo per macOS.
- `.github/workflows/android-build.yml`: test Android, diagnostica del
  toolchain, build validate di APK ARM64 di debug e caricamento degli artefatti
  CI.
- `.github/workflows/release-builds.yml`: automazione di test, build, artefatti,
  checksum e bozze di pre-release su runner nativi.
- `.github/dependabot.yml`: pull request mensili per aggiornare le GitHub Action
  fissate.

Quando modifichi un modulo runtime, aggiorna o aggiungi quando possibile il test
corrispondente in `tests/`. I nomi dei test rispecchiano già la maggior parte
dei moduli runtime e di manutenzione.

## Note architetturali

- MoonTransfer desktop avvia `croc` con `QProcess`, senza passare da shell come bash,
  fish o PowerShell.
- `src/moontransfer/app.py` mantiene l'entry point dell'applicazione, la
  finestra principale e i tab di invio/ricezione. Gestisce il layout dei
  widget, la validazione locale degli input, i dialoghi utente e la
  presentazione degli eventi dei controller. `transfer.py` gestisce le macchine
  a stati esplicite e l'orchestrazione dei processi per metadati e payload
  principale, i timeout, le risorse di sessione, la verifica e il cleanup. Il
  restante comportamento riutilizzabile è separato in `croc.py` per costruire
  i comandi `croc`, `protocol.py` per i manifest di controllo con limiti
  espliciti, `payload.py` per inventario e verifica esatta degli alberi,
  `files.py` per le primitive filesystem di basso livello, `progress.py` per
  parsing e aggregazione dell'output di trasferimento, `messages.py` per i
  messaggi di stato, `desktop.py` per l'integrazione con il file manager,
  `runner.py` per la gestione di `QProcess`, `tasks.py` per le operazioni
  annullabili in background, `cancellation.py` per il contratto di annullamento
  condiviso e `widgets.py` per i widget Qt condivisi.
- La versione di `croc` inclusa nel bundle è fissata in `pyproject.toml`; gli
  archivi supportati della release sono verificati con hash SHA-256 versionati
  prima dell'estrazione.
- In invio MoonTransfer genera direttamente i codici per metadati e payload
  principale. Il protocollo v2 descrive uno o più elementi principali tramite
  un manifest piatto con limiti espliciti di file e cartelle. Ogni voce file
  contiene dimensione esatta e hash SHA-256. Un ricevente v2 può anche
  normalizzare una proposta legacy v1 con un singolo file. Il codice visibile è
  solo quello dei metadati. I codici di
  trasferimento vengono passati tramite `CROC_SECRET`, perché `croc` moderno in
  modalità non-classic non accetta codici di invio personalizzati tramite
  `--code` sui sistemi Unix:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --disable-clipboard send --no-local <percorso> [<percorso> ...]
```

`--no-local` evita il relay locale di `croc`, che nei test con due istanze sulla
stessa macchina può rendere instabile la negoziazione.
`--classic=false` mantiene MoonTransfer sulla modalità moderna di `croc` anche
se la configurazione globale dell'utente ha memorizzato la modalità classic.

Prima di mostrare il codice dei metadati, il mittente verifica che gli elementi
inventariati non siano cambiati e avvia un unico processo `croc send`
principale con tutti gli elementi selezionati. MoonTransfer attende che la
versione fissata di `croc` comunichi il proprio codice: ciò avviene dopo che
`croc` ha raccolto e calcolato gli hash degli elementi da inviare e viene quindi
usato come confine della preparazione. Avvia poi il mittente dei metadati in una
seconda directory di configurazione `croc` isolata e mostra il relativo codice
solo quando anche questo processo raggiunge lo stesso punto. I due processi si
sovrappongono soltanto durante il trasferimento del piccolo manifest; in
seguito rimane in attesa il mittente principale già preparato.

Il destinatario avvia il processo `croc` principale senza `--yes`, poi
MoonTransfer scrive `y` o `n` su quel processo in base alla scelta fatta nella
GUI. In questo modo viene usato il prompt accetta/rifiuta di `croc` invece di un
trasferimento di decisione separato di MoonTransfer. Se il destinatario rifiuta
il payload, il trasferimento principale viene rifiutato e nessun contenuto del
payload viene scaricato. Se il mittente principale termina prima del
completamento dello scambio dei metadati, MoonTransfer segnala un errore invece
di mostrare il codice di una sessione inutilizzabile.

- In ricezione dei metadati, i file di controllo vengono prima ricevuti in
  directory temporanee di sessione. I codici di trasferimento vengono passati
  tramite `CROC_SECRET`, non come argomenti posizionali della riga di comando:

```text
CROC_SECRET=<hidden> croc --classic=false --ignore-stdin --yes --overwrite
```

Il processo di ricezione del payload principale mantiene invece stdin aperto e
non usa `--yes`, così MoonTransfer può rispondere al prompt di `croc`:

```text
CROC_SECRET=<hidden> croc --classic=false --overwrite
```

Ogni sessione di trasferimento fornisce inoltre a `croc` una directory di
configurazione temporanea isolata, quindi MoonTransfer non dipende dalle
impostazioni globali di `croc` dell'utente e non le modifica.

Il comando mostrato nei dettagli tecnici maschera i codici di trasferimento
interni. Il payload principale viene ricevuto in una nuova directory di
staging. MoonTransfer rifiuta percorsi non elencati, elementi mancanti, cambi di
tipo, link, file speciali, dimensioni errate e hash SHA-256 non corrispondenti
prima di pubblicare il risultato verificato. Più elementi principali
selezionati vengono pubblicati in un'unica cartella contenitore, così il gruppo
non viene unito intenzionalmente a contenuto già presente nella destinazione.

- Sul desktop, le operazioni locali potenzialmente lunghe vengono eseguite in un `QThread`
  annullabile: inventario e fingerprint del mittente, confronto con contenuto
  già presente, verifica finale dell'albero ricevuto e copie tra filesystem. Il
  mittente registra l'identità di ogni file sorgente assieme al suo hash,
  analizza nuovamente gli elementi selezionati e controlla i fingerprint prima
  di avviare il processo `croc` principale. La verifica finale del destinatario
  resta autorevole perché `croc` apre i percorsi sorgente dopo l'ultimo controllo
  locale di MoonTransfer.
- La riproducibilità della build dipende da `uv.lock`, dalla versione di `croc`
  fissata e dagli hash SHA-256 versionati in `pyproject.toml`.

## Target Android sperimentale

Il lavoro di fattibilità per Android è isolato sotto `android/` e non
sostituisce l'applicazione desktop PySide6. Usa un ambiente Python 3.13
separato, Kivy, Buildozer e un proprio `uv.lock`. L'albero sorgente Android
viene generato da una lista esplicita di moduli MoonTransfer indipendenti da Qt,
così il protocollo viene condiviso senza aggiungere Kivy alle dipendenze runtime
desktop.

Il prototipo attuale include un eseguibile `croc` ARM64 verificato e può inviare
o ricevere file, cartelle e selezioni miste tra Android e l'applicazione desktop
usando il manifest condiviso del protocollo v2 e lo Storage Access Framework di
Android. Un foreground service `dataSync` possiede i trasferimenti attivi,
quindi passare a un'altra applicazione non interrompe `croc`; una notifica
privata legata allo stato mostra fase e metriche di avanzamento disponibili e
fornisce un'azione di arresto legata alla sessione, quindi lascia un risultato
dismissibile. Il servizio gestisce i timeout `dataSync` di Android 15 e i
riavvii sticky non validi, ma le sessioni interrotte non possono ancora essere
riprese. Gli APK firmati sono ora inclusi nelle bozze di release avviate dai tag,
dopo la configurazione dell'environment di firma. Il
workflow CI Android dedicato crea comunque un APK ARM64 di
debug validato strutturalmente per i test; viene mantenuto intenzionalmente
separato dalle GitHub Release pubblicate.

Un avvio manuale dedicato su `main` può anche compilare un APK release e firmarlo
in un job protetto separato con la stessa chiave usata in locale. Le build da tag
confluiscono nella stessa bozza dei pacchetti desktop. Richiede la
configurazione della chiave e un versionCode coordinato; vedi
[Firma Android](../android/SIGNING.it.md).

Configurazione, diagnostica, comandi di build, dettagli
progettuali e test manuali di compatibilità sono documentati in
[android/README.it.md](../android/README.it.md).
