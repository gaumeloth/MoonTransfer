# MoonTransfer

MoonTransfer è una GUI per inviare e ricevere file tramite
[`croc`](https://github.com/schollz/croc).

L'obiettivo è offrire un trasferimento file semplice: chi invia sceglie un
file, MoonTransfer mostra un codice, chi riceve incolla quel codice e salva il
file nella cartella scelta.

MoonTransfer non implementa un protocollo crittografico proprio. La sicurezza,
la connessione e il trasferimento sono gestiti da `croc`; MoonTransfer fornisce
solo l'interfaccia grafica e include il binario `croc` nell'app buildata.

## Stato di sviluppo

MoonTransfer è in fase iniziale. Il flusso principale è già funzionante:

- invio di un singolo file;
- ricezione di un file tramite codice;
- visualizzazione dell'output di `croc` nella GUI;
- estrazione automatica del codice generato da `croc`;
- build locale con PyInstaller;
- download automatico del binario `croc` durante la build;
- bundle finale con `croc` incluso.

Al momento il progetto non fornisce ancora installer firmati o pacchetti di
release già pronti. Per usarlo è necessario scaricare il codice sorgente e
creare localmente la build per il proprio sistema operativo.

La build produce una cartella portabile `MoonTransfer`: per spostarla su un
altro computer bisogna copiare l'intera cartella generata, non solo
l'eseguibile.

## Roadmap

Possibili miglioramenti futuri, in ordine indicativo:

- pubblicare release scaricabili già buildate per Linux, Windows e macOS;
- mostrare messaggi di stato ed errore più chiari sopra all'output tecnico;
- aggiungere drag and drop del file da inviare;
- supportare l'invio di cartelle dalla GUI;
- ricordare l'ultima cartella di destinazione usata;
- aggiungere un pulsante per aprire la cartella del file ricevuto;
- aggiungere impostazioni avanzate per relay custom di `croc`;
- mantenere il codice di trasferimento fuori dagli argomenti del processo;
- separare ulteriormente logica di trasferimento e interfaccia grafica;
- aggiungere test automatici per parsing output, argomenti di `croc` e gestione
  errori;
- aggiungere una pipeline CI per controllare build e test sulle piattaforme
  principali;
- rendere più riproducibile la build fissando opzionalmente la versione di
  `croc`.

L'idea guida è restare vicini alla filosofia Unix: MoonTransfer deve fare una
cosa sola, delegare bene a `croc`, mantenere il comportamento leggibile e non
nascondere inutilmente gli errori.

## Scaricare il sorgente

La repository del progetto è:

```text
https://github.com/gaumeloth/MoonTransfer
```

Puoi scaricare MoonTransfer in due modi.

### Con Git

Questo metodo è consigliato se vuoi aggiornare facilmente la repository o
contribuire al progetto. Se non hai Git, puoi installarlo dalla
[pagina ufficiale di download](https://git-scm.com/downloads/).

```sh
git clone https://github.com/gaumeloth/MoonTransfer.git
cd MoonTransfer
```

### Come archivio ZIP

Questo metodo non richiede Git.

1. Apri la [pagina GitHub del progetto](https://github.com/gaumeloth/MoonTransfer).
2. Premi **Code**.
3. Scegli **Download ZIP**.
4. Estrai l'archivio in una cartella.
5. Apri un terminale dentro la cartella estratta.

GitHub documenta anche il download degli archivi sorgente nella propria
[documentazione ufficiale](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives).

## Requisiti

Per creare la build servono:

- [`uv`](https://docs.astral.sh/uv/);
- accesso a Internet durante la prima build;
- una piattaforma supportata da `tools/fetch_croc.py`: Linux x86_64/ARM64,
  macOS Intel/Apple Silicon o Windows 64 bit.

`uv` gestisce l'ambiente Python del progetto e installa le dipendenze indicate
in `pyproject.toml`. Il progetto richiede Python 3.13. Se nel sistema manca una
versione compatibile, installa Python 3.13 dalla
[pagina ufficiale di Python](https://www.python.org/downloads/).

## Installare uv

La documentazione ufficiale di `uv` è disponibile su
[docs.astral.sh/uv](https://docs.astral.sh/uv/). Le istruzioni aggiornate per
l'installazione sono nella pagina
[Installing uv](https://docs.astral.sh/uv/getting-started/installation/).

### Arch Linux

```sh
sudo pacman -S uv
```

### Linux/macOS

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Se il comando `uv` non viene trovato dopo l'installazione, chiudi e riapri il
terminale.

### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verifica l'installazione:

```sh
uv --version
```

## Build

Durante la build vengono installate le dipendenze Python, viene scaricato il
binario `croc` adatto alla piattaforma corrente e viene creato il pacchetto
PyInstaller in `dist/`.

Il comando comune, valido su tutti i sistemi dopo aver preparato l'ambiente con
`uv sync`, è:

```sh
uv run --frozen --dev python tools/build.py
```

`tools/build.py` è l'orchestratore della build: esegue `tools/fetch_croc.py` e
poi PyInstaller usando `MoonTransfer.spec`.

Gli script in `scripts/` sono wrapper specifici per sistema operativo. Prima
controllano i prerequisiti principali (`uv` e un Python compatibile risolto da
`uv`), mostrano istruzioni di recupero se qualcosa manca, eseguono `uv sync` e
poi chiamano `tools/build.py`.

### Linux/macOS

Dalla cartella del progetto:

```sh
./scripts/build.sh
```

Il comando può essere lanciato da fish, bash o zsh come `./scripts/build.sh`.
Non eseguirlo come `fish scripts/build.sh`.

Lo script verifica che `uv` sia disponibile e che `uv` riesca a trovare Python
3.13. Se il controllo Python fallisce, installa Python 3.13 oppure lascia che
`uv` installi la versione usata dal progetto:

```sh
uv python install 3.13
```

Output:

```text
dist/MoonTransfer/
```

### Windows

Apri PowerShell nella cartella del progetto ed esegui:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Lo script verifica che `uv` sia disponibile e che `uv` riesca a trovare Python
3.13. Se il controllo Python fallisce, installa Python 3.13 oppure esegui:

```powershell
uv python install 3.13
```

Output:

```text
dist\MoonTransfer\
```

## Avviare MoonTransfer

Dopo la build, apri la cartella generata:

```text
dist/MoonTransfer/
```

### Linux

Dal file manager, apri la cartella `dist/MoonTransfer/` e avvia il file
`MoonTransfer`.

Se il file manager non lo avvia con doppio click, puoi usare il terminale:

```sh
./dist/MoonTransfer/MoonTransfer
```

### macOS

Apri la cartella generata dalla build e avvia l'eseguibile `MoonTransfer`.

Se macOS blocca l'apertura perché l'app non è firmata, aprila dalle impostazioni
di sicurezza del sistema oppure avviala da terminale dalla cartella del progetto:

```sh
./dist/MoonTransfer/MoonTransfer
```

### Windows

Apri:

```text
dist\MoonTransfer\
```

e fai doppio click su:

```text
MoonTransfer.exe
```

Non spostare solo `MoonTransfer.exe`: deve restare accanto ai file e alle
cartelle generati da PyInstaller.

## Usare il programma

### Inviare un file

1. Apri MoonTransfer.
2. Vai nella scheda **Invia**.
3. Premi **Sfoglia...**.
4. Scegli il file da inviare.
5. Premi **Invia**.
6. Attendi che compaia il codice.
7. Comunica il codice alla persona che deve ricevere il file.

Il codice è monouso: serve per quel trasferimento e non va riutilizzato.

### Ricevere un file

1. Apri MoonTransfer.
2. Vai nella scheda **Ricevi**.
3. Incolla il codice ricevuto.
4. Scegli la cartella di destinazione.
5. Premi **Ricevi**.
6. Attendi il completamento del trasferimento.

Se il trasferimento non parte, verifica che entrambi i computer siano connessi a
Internet e che eventuali firewall o reti aziendali non blocchino le connessioni
usate da `croc`.

## Per chi contribuisce

### Avvio in sviluppo

Dalla root del progetto:

```sh
uv sync
uv run python tools/fetch_croc.py
uv run moontransfer
```

`tools/fetch_croc.py` scarica la latest release di `croc`, verifica il checksum
dell'archivio e copia il binario in `third_party/croc/`.

Riferimenti utili:

- [`croc`](https://github.com/schollz/croc), motore di trasferimento;
- [`uv`](https://docs.astral.sh/uv/), gestione ambiente Python e dipendenze;
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/), toolkit GUI;
- [PyInstaller](https://pyinstaller.org/en/stable/), creazione del bundle.

### Test manuale di trasferimento

Per verificare il flusso completo durante lo sviluppo puoi usare due istanze
dell'app sulla stessa macchina:

1. apri due istanze di MoonTransfer;
2. nella prima istanza invia un piccolo file;
3. copia il codice mostrato;
4. nella seconda istanza ricevi in una cartella diversa;
5. controlla che il file sia stato creato nella cartella di destinazione.

Questo test è utile per lo sviluppo, ma non rappresenta il caso d'uso principale
del programma, che resta il trasferimento tra due computer diversi.

### Scelte tecniche

- MoonTransfer avvia `croc` con `QProcess`, senza passare da shell come bash,
  fish o PowerShell.
- In invio usa:

```text
croc --ignore-stdin --disable-clipboard send --no-local <file>
```

`--no-local` evita il relay locale di `croc`, che nei test con due istanze sulla
stessa macchina può rendere instabile la negoziazione.

- In ricezione usa:

```text
CROC_SECRET=<codice> croc --ignore-stdin --yes --overwrite
```

Il codice viene passato al processo `croc` tramite variabile d'ambiente, non
come argomento della riga di comando.

### Struttura

```text
MoonTransfer/
├─ src/moontransfer/app.py
├─ tools/fetch_croc.py
├─ tools/build.py
├─ scripts/build.sh
├─ scripts/build.ps1
├─ MoonTransfer.spec
├─ pyproject.toml
├─ uv.lock
└─ THIRD_PARTY_NOTICES.md
```

### File generati

Questi percorsi sono generati localmente e non vanno committati:

```text
.venv/
.cache/
build/
dist/
third_party/croc/
__pycache__/
```

## Licenze

Vedi `THIRD_PARTY_NOTICES.md` per i componenti di terze parti, in particolare
`croc` e PySide6/Qt for Python.
