# Esperimento Android di MoonTransfer

Versione inglese: [README.md](README.md)

Questa directory contiene un ambiente Kivy e Buildozer isolato per il prototipo
di fattibilità Android. Non sostituisce l'applicazione desktop PySide6 e non fa
parte degli artefatti delle release desktop.

## Ambito attuale

Il prototipo attualmente fornisce:

- un ambiente di sviluppo Python 3.13 e Kivy 2.3.1;
- un'interfaccia Kivy per selezionare e inviare un file;
- sorgenti di build Android generati contenenti solamente moduli MoonTransfer
  esplicitamente approvati e indipendenti da Qt;
- una configurazione Buildozer e python-for-android con versioni fissate;
- un target APK di debug `arm64-v8a`;
- una recipe privata che verifica e compila per Android il sorgente `croc`
  fissato;
- un probe runtime Android che individua l'eseguibile incluso e ne controlla la
  versione senza esporre un segreto di trasferimento;
- selezione dei file tramite lo Storage Access Framework (SAF) di Android;
- un flusso di invio da Android a desktop compatibile con il protocollo v2 di
  MoonTransfer;
- avanzamento del trasferimento, segnalazione del rifiuto del destinatario,
  annullamento, timeout di inattività e pulizia dei file temporanei privati.

Rimane un mittente sperimentale. Non può ricevere file, selezionare più file o
cartelle, continuare in background o produrre artefatti release per architetture
diverse da `arm64-v8a`. Viene dichiarato solamente il permesso `INTERNET`; SAF
fornisce accesso solo al documento scelto esplicitamente dall'utente, senza
permessi di archiviazione estesi.

## Prerequisiti del sistema host

Le build Android richiedono Linux o macOS. La configurazione attuale prevede
Java 17, Go 1.25 o successivo, i normali strumenti di compilazione nativa e
Rust. Buildozer scarica Android SDK e NDK configurati quando necessario.

Su Ubuntu, installa i prerequisiti di sistema prima di compilare:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool \
  pkg-config cmake libffi-dev libssl-dev automake autopoint gettext \
  make gcc g++
```

Su Arch Linux e derivate come Garuda Linux:

```bash
sudo pacman -S --needed git zip unzip jdk17-openjdk autoconf libtool \
  pkgconf cmake libffi openssl automake gettext make gcc go
```

Installa Rust con il metodo documentato su <https://rustup.rs/> e assicurati
che `cargo` e `rustc` siano disponibili nel `PATH`.

Installa Go 1.25 o successivo da <https://go.dev/doc/install> se il pacchetto
fornito dal sistema operativo host è più vecchio. La recipe Android utilizza
deliberatamente il toolchain installato invece di scaricare implicitamente una
versione differente di Go.

Il toolchain Android viene validato con Java 17. Se un'altra release Java è la
predefinita di sistema, seleziona Java 17 per una singola esecuzione senza
cambiare l'impostazione globale:

```bash
JAVA_HOME=/usr/lib/jvm/java-17-openjdk ./scripts/android.sh doctor
JAVA_HOME=/usr/lib/jvm/java-17-openjdk ./scripts/android.sh build
```

## Comandi

Esegui questi comandi dalla radice della repository:

```bash
./scripts/android.sh doctor
./scripts/android.sh prepare
./scripts/android.sh run
./scripts/android.sh build
```

`doctor` controlla i prerequisiti del sistema host, incluse le versioni di Java
e Go. `prepare` ricrea l'albero dei sorgenti generati sotto
`build/android/source`. `run` avvia lo scaffold Kivy sul desktop per un rapido
smoke test della GUI. `build` produce un APK di debug sotto `dist/android`.

Quando l'APK viene avviato su Android, individua `libcroc.so` nella directory
delle librerie native dell'applicazione ed esegue `croc --version` in un thread
di lavoro. Uno stato verde conferma che l'eseguibile del trasporto può essere
avviato sul dispositivo.

La prima esecuzione può scaricare pacchetti Python, strumenti Android e archivi
sorgente. I sorgenti generati e gli output di build non devono essere modificati
o committati.

## Testare un trasferimento da Android a desktop

Questo è un test manuale di compatibilità del mittente sperimentale, non una
procedura di release per l'utente finale.

1. Compila l'applicazione desktop corrente e l'APK Android di debug dalla stessa
   revisione.
2. Installa l'APK generato
   `dist/android/moontransfer-<version>-arm64-v8a-debug.apk` su un dispositivo
   Android ARM64.
3. Avvia MoonTransfer sul desktop, apri **Ricevi** e scegli una cartella di
   destinazione.
4. Avvia l'app Android e attendi lo stato verde del trasporto `croc`.
5. Premi **Seleziona file** e scegli un documento piccolo e non sensibile dal
   selettore di sistema Android.
6. Controlla nome e dimensione visualizzati, quindi premi **Prepara e invia**.
7. L'app calcola l'hash della copia privata e mostra un codice di 32 caratteri.
   Il codice viene anche copiato negli appunti Android.
8. Inserisci quel codice nella scheda **Ricevi** del desktop e avvia la
   ricezione.
9. Controlla nome, dimensione e informazioni SHA-256 mostrate dall'app desktop,
   quindi accetta o rifiuta il trasferimento.
10. Se accetti, entrambe le applicazioni dovrebbero mostrare avanzamento e
    completamento. Controlla che il file verificato appaia nella destinazione
    desktop scelta. Se rifiuti, Android dovrebbe comunicare la decisione senza
    inviare il payload principale.

La chiusura dell'app Android o il pulsante **Interrompi** richiedono la
terminazione del processo `croc` attivo. Il prototipo attuale non dispone di un
servizio in background, quindi deve rimanere aperto durante l'invio.

## Progettazione del trasferimento Android

Il selettore di sistema restituisce un content URI invece di un normale percorso
del filesystem. MoonTransfer legge il nome portabile e la dimensione opzionale,
apre l'URI tramite `ContentResolver` e lo copia in una nuova directory privata
dell'app con modalità `0600`. La copia privata è la sorgente controllata usata
per l'hash e da `croc`; il suo fingerprint viene verificato nuovamente prima di
avviare il mittente principale. Viene eliminata dopo completamento, rifiuto,
errore o annullamento. Le directory di staging e sessione residue, ma
appartenenti all'app, vengono eliminate all'avvio successivo.

Il mittente riutilizza quindi il protocollo desktop invece di inviare un payload
`croc` grezzo:

1. analizza il file in staging e calcola SHA-256;
2. crea una proposta del protocollo v2 contenente un codice separato per il
   payload principale;
3. invia il manifest JSON con limiti espliciti usando l'unico codice visibile
   all'utente;
4. dopo che il desktop riceve il manifest, avvia il processo `croc send`
   principale;
5. lascia che il ricevitore desktop con prompt comunichi accettazione o rifiuto
   tramite la connessione `croc` principale.

Entrambi i segreti vengono passati in `CROC_SECRET`, mai come argomenti della
riga di comando. Ogni sessione riceve una directory di configurazione `croc`
isolata. L'output dei processi viene consumato in parallelo da stdout e stderr,
limitato per record e oscurato prima di raggiungere le callback. Il completamento
del processo viene determinato dallo stato di uscita; l'output testuale viene
analizzato solamente per avanzamento e stato relativo al rifiuto. Un timeout di
inattività di 15 minuti viene azzerato ogni volta che `croc` produce output,
quindi non impone una durata massima fissa a un trasferimento attivo.

## Isolamento dalle release desktop

Le dipendenze Android si trovano nel `pyproject.toml` e nell'`uv.lock` dedicati
di questa directory. Il progetto principale mantiene PySide6 come unica GUI
runtime. Buildozer riceve un albero sorgente generato, mentre
`MoonTransfer.spec` continua a creare i pacchetti di
`src/moontransfer/app.py` per i sistemi desktop.

Il pacchetto generato esclude intenzionalmente questi moduli specifici di Qt:

- `app.py`;
- `desktop.py`;
- `runner.py`;
- `tasks.py`;
- `transfer.py`;
- `widgets.py`.

I moduli condivisi vengono copiati da `src/moontransfer` durante ogni
preparazione, quindi il prototipo Android non può conservare silenziosamente
una copia obsoleta del protocollo.

## Build nativa di croc

La recipe locale sotto `recipes/croc` fissa la stessa versione di `croc`
dichiarata dal progetto desktop. Verifica l'archivio sorgente upstream tramite
SHA-512 e compila un eseguibile Android ARM64 position-independent con cgo
abilitato. In questo modo Go delega la risoluzione dei nomi dei relay al resolver
DNS nativo di Android, rispettando la rete, la VPN e il Private DNS attivi.
L'eseguibile viene incluso come `lib/arm64-v8a/libcroc.so`, mantenendolo
nell'area delle librerie native firmata dell'APK. Nel pacchetto dell'applicazione
viene inclusa anche la licenza MIT upstream.

## Limitazioni note

- è implementato solamente l'invio di un singolo file da Android a desktop;
- la selezione di cartelle e gruppi di file non è implementata;
- la ricezione su Android e la gestione dei conflitti di destinazione non sono
  implementate;
- nessun servizio foreground mantiene vivo il trasferimento dopo la chiusura
  dell'app;
- viene prodotto solamente un APK di debug `arm64-v8a`;
- lo stato del trasferimento dipende ancora in parte dall'output leggibile di
  `croc`, che non espone un'API strutturata per l'avanzamento.
