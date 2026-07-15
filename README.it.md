# MoonTransfer

Versione inglese: [README.md](README.md)

MoonTransfer è una GUI per inviare e ricevere file tramite
[`croc`](https://github.com/schollz/croc).

L'obiettivo è offrire un trasferimento file semplice: chi invia sceglie un
file, MoonTransfer mostra un codice, chi riceve incolla quel codice e salva il
file nella cartella scelta.

MoonTransfer non implementa un protocollo crittografico proprio. La sicurezza,
la connessione e il trasferimento sono gestiti da `croc`; MoonTransfer fornisce
solo l'interfaccia grafica e include il binario `croc` nell'app buildata.

## Stato attuale

MoonTransfer è in fase iniziale. Il flusso principale è già funzionante:

- invio di un singolo file;
- ricezione di un file tramite codice;
- visualizzazione dell'output di `croc` nella GUI;
- estrazione automatica del codice generato da `croc`;
- build locale con PyInstaller;
- download automatico del binario `croc` durante la build;
- versione `croc` fissata e verifica SHA-256 per le piattaforme supportate;
- bundle finale con `croc` incluso.

Al momento il progetto non fornisce ancora installer firmati o pacchetti di
release già pronti. Per usarlo è necessario scaricare il codice sorgente e
creare localmente la build per il proprio sistema operativo.

La build produce una cartella portabile `MoonTransfer`: per spostarla su un
altro computer bisogna copiare l'intera cartella generata, non solo
l'eseguibile.

## Guida rapida

Per usare MoonTransfer oggi, segui questi passaggi nell'ordine:

1. scarica il codice sorgente, con Git oppure come archivio ZIP;
2. apri un terminale nella cartella del progetto;
3. installa `uv`;
4. lascia che `uv` trovi o installi Python 3.13.x/3.14.x;
5. esegui lo script di build per il tuo sistema operativo;
6. apri la cartella `dist/MoonTransfer/`;
7. avvia MoonTransfer.

Non devi installare `croc` a mano: viene scaricato automaticamente durante la
build.

## Scaricare il sorgente

La repository del progetto è:

```text
https://github.com/gaumeloth/MoonTransfer
```

Puoi scaricare MoonTransfer in due modi:

- con Git, consigliato se vuoi aggiornare facilmente la repository o
  contribuire;
- come archivio ZIP, più semplice se vuoi solo provare o buildare il programma
  senza usare Git.

Espandi solo il metodo che vuoi usare.

<details>
<summary>Scaricare con Git</summary>

Se non hai Git, installalo prima dalla
[pagina ufficiale di download](https://git-scm.com/downloads/).

Le istruzioni specifiche per sistema operativo sono inizialmente chiuse:
espandi solo quella del sistema che stai usando.

<details>
<summary>Linux</summary>

Su Linux puoi usare il gestore pacchetti della distribuzione, per esempio:

```sh
sudo pacman -S git          # Arch Linux
sudo apt install git        # Debian, Ubuntu e derivate
sudo dnf install git        # Fedora
```

</details>

<details>
<summary>macOS</summary>

Su macOS puoi installare gli strumenti da riga di comando di Apple eseguendo:

```sh
git --version
```

Se Git non è presente, macOS proporrà l'installazione dei Command Line Tools.
In alternativa puoi usare Homebrew:

```sh
brew install git
```

</details>

<details>
<summary>Windows</summary>

Su Windows scarica Git dalla
[pagina ufficiale per Windows](https://git-scm.com/download/win), avvia
l'installer e usa queste scelte:

- scarica il normale installer per la tua architettura, di solito **64-bit Git
  for Windows Setup** su PC Intel/AMD;
- mantieni i componenti predefiniti;
- alla scelta del `PATH`, seleziona **Git from the command line and also from
  3rd-party software**, così `git` funziona anche da PowerShell;
- per editor, terminazioni di riga, terminale, HTTPS e opzioni extra puoi
  lasciare le scelte predefinite;
- Git Credential Manager può restare abilitato, è utile se in futuro lavori con
  repository private.

</details>

Dopo l'installazione chiudi e riapri il terminale, poi verifica:

```sh
git --version
```

Scarica la repository:

```sh
git clone https://github.com/gaumeloth/MoonTransfer.git
cd MoonTransfer
```

Da questo momento tutti i comandi successivi vanno eseguiti da dentro la
cartella `MoonTransfer`.

</details>

<details>
<summary>Scaricare come archivio ZIP</summary>

Questo metodo non richiede Git.

1. Apri la [pagina GitHub del progetto](https://github.com/gaumeloth/MoonTransfer).
2. Premi **Code**.
3. Scegli **Download ZIP**.
4. Estrai l'archivio in una cartella.
5. Apri la cartella estratta.

La cartella estratta potrebbe chiamarsi `MoonTransfer-main` invece di
`MoonTransfer`. Va bene: usa quella cartella per i comandi successivi.

Ora apri un terminale dentro la cartella estratta.

<details>
<summary>Linux/macOS</summary>

Puoi usare il file manager e scegliere **Apri nel terminale** oppure aprire un
terminale e spostarti manualmente nella cartella estratta con `cd`.

</details>

<details>
<summary>Windows</summary>

Apri la cartella estratta in Esplora file. Poi usa uno di questi metodi:

- fai click destro in uno spazio vuoto della cartella e scegli **Apri nel
  terminale**;
- oppure clicca nella barra del percorso, scrivi `powershell` e premi Invio.

</details>

GitHub documenta anche il download degli archivi sorgente nella propria
[documentazione ufficiale](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives).

</details>

## Preparare il sistema

Per creare la build servono:

- [`uv`](https://docs.astral.sh/uv/);
- Python 3.13.x o 3.14.x, installato manualmente o gestito da `uv`;
- accesso a Internet durante la build;
- una piattaforma supportata da `tools/fetch_croc.py`: Linux x86_64/ARM64,
  macOS Intel/Apple Silicon o Windows x64/ARM64.

Il modo più semplice è installare `uv` e lasciare che sia `uv` a gestire Python
per il progetto.

### Installare uv

La documentazione ufficiale di `uv` è disponibile su
[docs.astral.sh/uv](https://docs.astral.sh/uv/). Le istruzioni aggiornate per
l'installazione sono nella pagina
[Installing uv](https://docs.astral.sh/uv/getting-started/installation/).

Espandi solo il sistema operativo che stai usando.

<details>
<summary>Arch Linux</summary>

```sh
sudo pacman -S uv
```

</details>

<details>
<summary>Linux/macOS</summary>

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Se il comando `uv` non viene trovato dopo l'installazione, chiudi e riapri il
terminale.

</details>

<details>
<summary>Windows PowerShell</summary>

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Dopo l'installazione chiudi e riapri PowerShell.

</details>

Verifica l'installazione:

```sh
uv --version
```

### Preparare Python

MoonTransfer richiede Python 3.13.x o 3.14.x. `uv` può usare una versione già
installata nel sistema oppure installarne una compatibile.

Dalla cartella del progetto, verifica quale Python viene trovato:

```sh
uv python find --show-version
```

Se il comando mostra una versione `3.13.x` o `3.14.x`, puoi proseguire.

Se invece il comando fallisce, oppure non trova una versione compatibile, esegui:

```sh
uv python install '>=3.13,<3.15'
```

Poi riprova:

```sh
uv python find --show-version
```

Se preferisci installare Python manualmente, scegli una versione stabile di
Python 3.13 o 3.14 dalla
[pagina ufficiale di download](https://www.python.org/downloads/).

<details>
<summary>Windows: installare Python manualmente</summary>

Su Windows hai due possibilità pratiche.

La prima è il **Python install manager**, consigliato dalla documentazione
ufficiale recente. Scaricalo dalla pagina di Python, installalo, apri
PowerShell e poi installa una runtime compatibile:

```powershell
py install 3.14
```

In alternativa puoi installare Python 3.13:

```powershell
py install 3.13
```

Se durante la configurazione viene proposto di aggiungere Python al `PATH`,
accetta: rende più semplice l'uso da PowerShell.

La seconda possibilità è il classico installer di una singola release Python:

- nella pagina delle release Windows scegli **Windows installer (64-bit)** su PC
  Intel/AMD moderni, oppure **Windows installer (ARM64)** su Windows ARM;
- non scegliere l'**embeddable package**, perché è pensato per incorporare
  Python in altre applicazioni e non per lavorare da terminale;
- nella prima schermata abilita **Add python.exe to PATH**;
- usa **Install Now** per un'installazione standard, oppure **Customize
  installation** solo se vuoi controllare le opzioni;
- se usi la schermata personalizzata, lascia abilitati `pip`, `py launcher` e
  l'installazione dei file standard;
- se alla fine compare **Disable path length limit**, puoi abilitarlo: non è
  obbligatorio per MoonTransfer, ma riduce possibili limiti sui percorsi lunghi
  in altri progetti Python.

Dopo l'installazione chiudi e riapri PowerShell, poi verifica:

```powershell
python --version
py --version
```

Una delle versioni disponibili deve essere Python 3.13.x o 3.14.x. Se Windows
apre il Microsoft Store invece di Python, controlla le impostazioni
**Manage app execution aliases** e disabilita eventuali alias Python dello Store
che interferiscono con l'installazione reale.

</details>

## Creare la build

La build installa le dipendenze Python, scarica il binario `croc` adatto alla
piattaforma corrente e crea il pacchetto PyInstaller in `dist/`.

La versione di `croc` e gli hash SHA-256 attesi sono dichiarati in
`[tool.moontransfer.croc]` in `pyproject.toml`. Una build normale usa quella
versione fissata; non passa automaticamente all'ultima release upstream di
`croc`.

Usa lo script adatto al tuo sistema operativo. Gli script controllano i
prerequisiti principali, eseguono `uv sync --frozen --dev` usando `uv.lock`
committato e poi chiamano `tools/build.py`.

<details>
<summary>Linux/macOS</summary>

Dalla cartella del progetto:

```sh
./scripts/build.sh
```

Il comando può essere lanciato da fish, bash o zsh come `./scripts/build.sh`.
Non eseguirlo come `fish scripts/build.sh`.

Se la build termina correttamente, troverai il programma in:

```text
dist/MoonTransfer/
```

</details>

<details>
<summary>Windows</summary>

Apri PowerShell nella cartella del progetto ed esegui:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Se la build termina correttamente, troverai il programma in:

```text
dist\MoonTransfer\
```

</details>

<details>
<summary>Metodo avanzato</summary>

Il comando comune, valido su tutti i sistemi dopo aver preparato l'ambiente con
`uv sync --frozen --dev`, è:

```sh
uv run --frozen --dev python tools/build.py
```

`tools/build.py` è l'orchestratore della build: esegue `tools/fetch_croc.py` e
poi PyInstaller usando `MoonTransfer.spec`.

Per controllare l'ultima release upstream di `croc` senza cambiare il pin di
build:

```sh
uv run --frozen python tools/fetch_croc.py --latest
```

</details>

## Avviare MoonTransfer

Dopo la build, apri la cartella generata:

```text
dist/MoonTransfer/
```

Non spostare solo l'eseguibile: deve restare accanto ai file e alle cartelle
generati da PyInstaller.

<details>
<summary>Linux</summary>

Dal file manager, apri la cartella `dist/MoonTransfer/` e avvia il file
`MoonTransfer`.

Se il file manager non lo avvia con doppio click, puoi usare il terminale:

```sh
./dist/MoonTransfer/MoonTransfer
```

</details>

<details>
<summary>macOS</summary>

Apri la cartella generata dalla build e avvia l'eseguibile `MoonTransfer`.

Se macOS blocca l'apertura perché l'app non è firmata, aprila dalle impostazioni
di sicurezza del sistema oppure avviala da terminale dalla cartella del progetto:

```sh
./dist/MoonTransfer/MoonTransfer
```

</details>

<details>
<summary>Windows</summary>

Apri:

```text
dist\MoonTransfer\
```

e fai doppio click su:

```text
MoonTransfer.exe
```

</details>

## Risoluzione problemi

### Warning Qt sulle icone SVG in Linux

Quando MoonTransfer viene avviato da terminale, Qt può stampare warning come:

```text
qt.svg: Cannot read file '/usr/share/icons/BeautyLine/places/16/folder-new.svg',
because: Start tag expected. (line 1)
```

Significa che Qt ha provato a caricare un'icona SVG dal tema icone di sistema,
ma quel file non è SVG valido. Di solito indica un file icona corrotto, vuoto,
troncato o comunque non valido nel tema grafico. Non riguarda il trasferimento
dei file, `croc`, la cifratura o il contenuto ricevuto. Al massimo può mancare
o apparire male un'icona del file dialog o di una cartella.

Per controllare il file icona sul sistema interessato:

```sh
file /usr/share/icons/BeautyLine/places/16/folder-new.svg
head -n 5 /usr/share/icons/BeautyLine/places/16/folder-new.svg
```

Su sistemi basati su Arch, come Garuda, puoi anche controllare quale pacchetto
possiede il file:

```sh
pacman -Qo /usr/share/icons/BeautyLine/places/16/folder-new.svg
```

La correzione corretta è reinstallare o aggiornare il pacchetto del tema icone,
scegliere un altro tema icone o correggere il file SVG non valido.

## Usare MoonTransfer

Per completare un trasferimento servono due persone o due computer:

- il mittente apre la scheda **Invia** e genera un codice;
- il destinatario apre la scheda **Ricevi** e inserisce quel codice.

Entrambi i computer devono essere connessi a Internet. Il codice va comunicato
fuori da MoonTransfer, per esempio via chat, telefono o email.

### Inviare un file

Sul computer che possiede il file da inviare:

1. apri MoonTransfer;
2. vai nella scheda **Invia**;
3. premi **Sfoglia...**;
4. scegli il file da inviare;
5. premi **Invia**;
6. attendi che compaia il codice;
7. comunica il codice alla persona che deve ricevere il file.

Durante il trasferimento, MoonTransfer mostra avanzamento, dimensione inviata,
velocità attuale, tempo trascorso e tempo stimato rimanente quando `croc`
fornisce informazioni di progresso sufficienti.

Il codice è monouso: serve per quel trasferimento e non va riutilizzato.

### Ricevere un file

Sul computer che deve ricevere il file:

1. apri MoonTransfer;
2. vai nella scheda **Ricevi**;
3. incolla il codice ricevuto;
4. scegli la cartella di destinazione;
5. conferma che file con lo stesso nome nella destinazione possono essere
   sovrascritti;
6. premi **Ricevi**;
7. attendi il completamento del trasferimento.

Durante il trasferimento, MoonTransfer mostra avanzamento, dimensione scaricata,
velocità attuale, tempo trascorso e tempo stimato rimanente quando `croc`
fornisce informazioni di progresso sufficienti.

Se il trasferimento non parte, verifica che entrambi i computer siano connessi a
Internet e che eventuali firewall o reti aziendali non blocchino le connessioni
usate da `croc`.

## Per chi contribuisce

### Roadmap

Possibili miglioramenti futuri, in ordine indicativo:

- pubblicare release scaricabili già buildate per Linux, Windows e macOS;
- aggiungere drag and drop del file da inviare;
- supportare l'invio di cartelle dalla GUI;
- ricordare l'ultima cartella di destinazione usata;
- aggiungere impostazioni avanzate per relay custom di `croc`;
- separare ulteriormente logica di trasferimento, parsing del progresso e
  interfaccia grafica;
- aggiungere altri test automatici per parsing output, argomenti di `croc` e
  gestione errori;
- aggiungere una pipeline CI per controllare build e test sulle piattaforme
  principali;
- eseguire automaticamente sui sistemi principali il controllo di compatibilità
  con l'ultima release di `croc`.

L'idea guida è restare vicini alla filosofia Unix: MoonTransfer deve fare una
cosa sola, delegare bene a `croc`, mantenere il comportamento leggibile e non
nascondere inutilmente gli errori.

### Avvio in sviluppo

Dalla root del progetto:

```sh
uv sync --frozen
uv run python tools/fetch_croc.py
uv run moontransfer
```

`tools/fetch_croc.py` scarica la release di `croc` fissata in `pyproject.toml`,
verifica il checksum dell'archivio e copia il binario in `third_party/croc/`.

Riferimenti utili:

- [`croc`](https://github.com/schollz/croc), motore di trasferimento;
- [`uv`](https://docs.astral.sh/uv/), gestione ambiente Python e dipendenze;
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/), toolkit GUI;
- [PyInstaller](https://pyinstaller.org/en/stable/), creazione del bundle.

### Controllare l'ultima release di croc

Le build normali restano intenzionalmente riproducibili: usano la versione di
`croc` e gli hash SHA-256 fissati in `pyproject.toml`. Chi contribuisce può
controllare separatamente se esiste una release upstream più recente di `croc`
e se MoonTransfer riesce ancora a usarla correttamente.

Dalla root del progetto:

```sh
uv run --frozen python tools/check_latest_croc.py
```

Il comando:

- legge da `pyproject.toml` la versione di `croc` fissata;
- chiede a GitHub qual è l'ultima release upstream di `croc`;
- si ferma subito se la versione fissata è già aggiornata;
- se esiste una versione più recente, scarica il file dei checksum della
  release e l'archivio per la piattaforma corrente;
- verifica lo SHA-256 dell'archivio prima di estrarlo;
- esegue smoke test sui flag di `croc` usati da MoonTransfer.

Per eseguire gli smoke test anche quando l'ultima release è già quella fissata:

```sh
uv run --frozen python tools/check_latest_croc.py --force
```

Esiste anche un controllo end-to-end opzionale del trasferimento:

```sh
uv run --frozen python tools/check_latest_croc.py --force --transfer
```

Il controllo di trasferimento avvia un mittente e un destinatario con il
binario `croc` più recente, trasferisce un piccolo file temporaneo e verifica il
contenuto ricevuto. Richiede accesso a Internet e un relay `croc` raggiungibile,
quindi non fa parte del controllo predefinito.

Se il controllo passa per una nuova release, aggiorna `[tool.moontransfer.croc]`
in `pyproject.toml` con la nuova versione e gli hash ufficiali, poi esegui la
suite di test normale prima del commit.

### Test automatici

I test unitari coprono la logica non-GUI collegata a `croc`, come parsing del
codice, argomenti di invio/ricezione, gestione della variabile `CROC_SECRET`,
selezione degli archivi `croc` fissati e helper per il controllo dell'ultima
release.

Dalla root del progetto:

```sh
uv run --frozen python -m unittest discover -s tests
```

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
- La GUI resta in `src/moontransfer/app.py`; la logica riutilizzabile legata a
  `croc` vive in `src/moontransfer/croc.py`.
- La versione di `croc` inclusa nel bundle è fissata in `pyproject.toml`; gli
  archivi supportati della release sono verificati con hash SHA-256 versionati
  prima dell'estrazione.
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
├─ src/moontransfer/croc.py
├─ tools/check_latest_croc.py
├─ tools/fetch_croc.py
├─ tools/build.py
├─ scripts/build.sh
├─ scripts/build.ps1
├─ tests/test_check_latest_croc.py
├─ tests/test_fetch_croc.py
├─ tests/test_croc.py
├─ README.md
├─ README.it.md
├─ LICENSE
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

MoonTransfer è distribuito sotto la GNU General Public License versione 3.
Vedi il testo completo della licenza in [LICENSE](LICENSE).

I componenti di terze parti mantengono le rispettive licenze. Vedi
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) per i componenti di terze
parti, in particolare `croc` e PySide6/Qt for Python.
