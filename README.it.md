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
- ricezione dei metadati del file tramite codice prima di accettare il download
  principale;
- invio di una risposta esplicita di accettazione/rifiuto prima del
  trasferimento principale;
- visualizzazione dell'output di `croc` nella GUI;
- generazione di un solo codice visibile all'utente, con codici di controllo
  interni nascosti;
- visualizzazione di nome file, dimensione e SHA-256 prima del download
  principale;
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

Il codice permette prima al destinatario di scaricare un piccolo file di
metadati. Il destinatario può quindi accettare o rifiutare il trasferimento.
MoonTransfer avvia il trasferimento principale solo dopo che il mittente ha
ricevuto la risposta del destinatario.

Durante il trasferimento del file principale, MoonTransfer mostra avanzamento,
dimensione inviata, velocità attuale, tempo trascorso e tempo stimato rimanente
quando `croc` fornisce informazioni di progresso sufficienti.

Il codice è monouso: serve per quel trasferimento e non va riutilizzato.

### Ricevere un file

Sul computer che deve ricevere il file:

1. apri MoonTransfer;
2. vai nella scheda **Ricevi**;
3. incolla il codice ricevuto;
4. scegli la cartella di destinazione;
5. premi **Ricevi**;
6. controlla nome file, dimensione e hash SHA-256 mostrati da MoonTransfer;
7. accetta o rifiuta il trasferimento;
8. se esiste già un file con lo stesso nome, scegli se non scaricarlo,
   sovrascriverlo o salvare il file in arrivo con un altro nome;
9. attendi il completamento del trasferimento.

Il file principale viene scaricato solo dopo che MoonTransfer ha inviato la
risposta di accettazione al mittente. Al termine MoonTransfer verifica
dimensione e hash SHA-256 ricevuti prima di salvare il file nella destinazione
finale.

Durante il trasferimento del file principale, MoonTransfer mostra avanzamento,
dimensione scaricata, velocità attuale, tempo trascorso e tempo stimato
rimanente quando `croc` fornisce informazioni di progresso sufficienti.

Se il trasferimento non parte, verifica che entrambi i computer siano connessi a
Internet e che eventuali firewall o reti aziendali non blocchino le connessioni
usate da `croc`.

## Per chi contribuisce

### Stato del progetto e roadmap

MoonTransfer è in una fase di sviluppo iniziale attiva. Offre già un flusso
grafico di invio/ricezione, include nella build un binario `croc` fissato e
verificato tramite checksum, e contiene test unitari per la logica non-GUI. Le
release già pronte non sono ancora pubblicate, quindi al momento gli utenti
buildano l'applicazione localmente.

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

### Modello di contribuzione

Le contribuzioni esterne devono essere proposte tramite pull request. Non è
previsto l'accesso diretto in push alla repository originale.

Flusso Git consigliato:

1. fai un fork della repository su GitHub;
2. clona localmente il tuo fork;
3. aggiungi la repository originale come `upstream`;
4. crea un branch dedicato alla modifica;
5. committa un insieme di modifiche coerente e circoscritto;
6. fai push del branch sul tuo fork;
7. apri una pull request dal branch del tuo fork verso
   `gaumeloth/MoonTransfer:main`.

Esempio:

```sh
git clone https://github.com/<tuo-utente>/MoonTransfer.git
cd MoonTransfer
git remote add upstream https://github.com/gaumeloth/MoonTransfer.git
git switch -c breve-descrizione-modifica
```

Prima di iniziare un nuovo lavoro, aggiorna il tuo `main` locale dalla
repository originale:

```sh
git fetch upstream
git switch main
git merge --ff-only upstream/main
```

Mantieni le pull request focalizzate. Se una modifica mescola codice,
documentazione, formattazione, dipendenze e build senza un legame diretto,
dividila prima di aprire la pull request. Le modifiche più grandi andrebbero
discusse prima dell'implementazione.

### Flusso di contribuzione

Per una normale sessione di sviluppo:

1. prepara l'ambiente di sviluppo;
2. scarica il binario `croc` fissato;
3. avvia MoonTransfer e applica la modifica;
4. esegui i controlli automatici;
5. esegui un test manuale di trasferimento se la modifica riguarda il
   comportamento di trasferimento o il flusso della GUI;
6. committa solo modifiche intenzionali a sorgenti, documentazione,
   configurazione e lockfile;
7. fai push del branch sul tuo fork e apri una pull request.

Se modifichi documentazione per utenti o contributori, mantieni allineati
`README.md` e `README.it.md`: non devono essere traduzioni letterali, ma devono
avere la stessa struttura e le stesse informazioni.

### Preparazione sviluppo

Prepara l'ambiente Python con le dipendenze bloccate e gli strumenti di sviluppo
necessari anche per il lavoro legato alla build:

```sh
uv sync --frozen --dev
```

Scarica il binario `croc` fissato usato durante l'avvio in sviluppo:

```sh
uv run python tools/fetch_croc.py
```

`tools/fetch_croc.py` scarica la release di `croc` fissata in `pyproject.toml`,
verifica il checksum dell'archivio e copia il binario in `third_party/croc/`.

### Modifiche alle dipendenze

`uv.lock` è committato intenzionalmente. Rende riproducibile la risoluzione
delle dipendenze per sviluppo, test e build locali.

Se cambi le dipendenze Python:

1. modifica `pyproject.toml`;
2. aggiorna `uv.lock` con `uv lock`;
3. esegui `uv sync --frozen --dev`;
4. esegui i controlli automatici;
5. committa sia `pyproject.toml` sia `uv.lock`.

Non modificare `uv.lock` manualmente.

### Avvio in sviluppo

Avvia MoonTransfer dalla root del progetto:

```sh
uv run moontransfer
```

Riferimenti utili:

- [`croc`](https://github.com/schollz/croc), motore di trasferimento;
- [`uv`](https://docs.astral.sh/uv/), gestione ambiente Python e dipendenze;
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/), toolkit GUI;
- [PyInstaller](https://pyinstaller.org/en/stable/), creazione del bundle.

### Test automatici

I test unitari coprono la logica non-GUI separata nei moduli runtime e negli
strumenti di manutenzione: costruzione dei comandi, parsing dell'output di
trasferimento, messaggi di stato, helper di integrazione desktop, separazione
dell'output dei processi, selezione degli archivi `croc` fissati e helper per il
controllo dell'ultima release.

Non esercitano l'interazione reale con la GUI e non eseguono un trasferimento
reale per impostazione predefinita. Usa il test manuale di trasferimento per
questi controlli.

Esegui la suite di test:

```sh
uv run --frozen python -m unittest discover -s tests
```

Controlla che i moduli Python compilino:

```sh
uv run --frozen python -m py_compile src/moontransfer/*.py tools/*.py
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

### Prima del commit

Esegui questi controlli prima di committare:

```sh
uv lock --check
uv run --frozen python -m unittest discover -s tests
uv run --frozen python -m py_compile src/moontransfer/*.py tools/*.py
git diff --check
```

Se tocchi script di build, packaging o `MoonTransfer.spec`, esegui anche lo
script di build per la piattaforma modificata.

### Attività di manutenzione

#### Controllare l'ultima release di croc

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

### Note architetturali

- MoonTransfer avvia `croc` con `QProcess`, senza passare da shell come bash,
  fish o PowerShell.
- `src/moontransfer/app.py` mantiene l'entry point dell'applicazione, la
  finestra principale e i tab di invio/ricezione. Il comportamento riutilizzabile
  è separato in moduli più piccoli: `croc.py` per costruire i comandi `croc`,
  `protocol.py` per i messaggi JSON di controllo di MoonTransfer, `files.py`
  per hashing, directory temporanee, controllo conflitti e posizionamento finale
  del file, `progress.py` per il parsing dell'output di trasferimento,
  `messages.py` per i messaggi di stato, `desktop.py` per l'integrazione con il
  file manager, `runner.py` per la gestione di `QProcess` e `widgets.py` per i
  widget Qt condivisi.
- La versione di `croc` inclusa nel bundle è fissata in `pyproject.toml`; gli
  archivi supportati della release sono verificati con hash SHA-256 versionati
  prima dell'estrazione.
- In invio MoonTransfer genera direttamente i codici per metadati, decisione e
  file principale. Il codice visibile è solo quello dei metadati. Ogni
  trasferimento usa comunque `croc send --code`, per esempio:

```text
croc --ignore-stdin --disable-clipboard send --no-local --code <codice> <file>
```

`--no-local` evita il relay locale di `croc`, che nei test con due istanze sulla
stessa macchina può rendere instabile la negoziazione.

Dopo il trasferimento dei metadati, il mittente attende un piccolo file di
decisione dal destinatario. Entrambi i lati ritentano il trasferimento della
decisione con lo stesso codice nascosto finché la risposta viene consegnata o la
sessione va in timeout. Se il destinatario rifiuta il file, il mittente non
avvia il processo `croc send` principale. Se il destinatario accetta, il
mittente avvia il trasferimento del file e il destinatario avvia il download
principale.

- In ricezione, i file di controllo e il file principale vengono prima ricevuti
  in directory temporanee di sessione:

```text
croc --ignore-stdin --yes --overwrite <codice>
```

Il comando mostrato nei dettagli tecnici maschera i codici di trasferimento
interni. Il file finale viene spostato nella destinazione scelta solo dopo la
verifica della dimensione e dell'hash SHA-256 attesi.

- La riproducibilità della build dipende da `uv.lock`, dalla versione di `croc`
  fissata e dagli hash SHA-256 versionati in `pyproject.toml`.

### Struttura

```text
MoonTransfer/
├─ src/
│  └─ moontransfer/
│     ├─ app.py
│     ├─ croc.py
│     ├─ desktop.py
│     ├─ files.py
│     ├─ messages.py
│     ├─ protocol.py
│     ├─ progress.py
│     ├─ runner.py
│     └─ widgets.py
├─ tools/
│  ├─ build.py
│  ├─ check_latest_croc.py
│  └─ fetch_croc.py
├─ scripts/
│  ├─ build.ps1
│  └─ build.sh
├─ tests/
│  ├─ test_check_latest_croc.py
│  ├─ test_croc.py
│  ├─ test_desktop.py
│  ├─ test_fetch_croc.py
│  ├─ test_files.py
│  ├─ test_messages.py
│  ├─ test_protocol.py
│  ├─ test_progress.py
│  └─ test_runner.py
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

Se uno di questi percorsi appare in `git status`, lascialo fuori dal commit.

## Licenze

MoonTransfer è distribuito sotto la GNU General Public License versione 3.
Vedi il testo completo della licenza in [LICENSE](LICENSE).

I componenti di terze parti mantengono le rispettive licenze. Vedi
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) per i componenti di terze
parti, in particolare `croc` e PySide6/Qt for Python.
