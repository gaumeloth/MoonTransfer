# MoonTransfer

<p align="center">
  <img
    src="src/moontransfer/assets/branding/moontransfer-logo.png"
    alt="Logo di MoonTransfer"
    width="640"
  >
</p>

Versione inglese: [README.md](README.md)

MoonTransfer è una GUI per inviare e ricevere file e cartelle tramite
[`croc`](https://github.com/schollz/croc).

L'obiettivo è offrire un trasferimento semplice: chi invia sceglie uno o più
file e cartelle, MoonTransfer mostra un codice, chi riceve incolla quel codice
e salva il contenuto selezionato.

MoonTransfer non implementa un protocollo crittografico proprio. La sicurezza,
la connessione e il trasferimento sono gestiti da `croc`; MoonTransfer fornisce
solo l'interfaccia grafica e include il binario `croc` nell'app buildata.

## Stato attuale

MoonTransfer è in fase iniziale. Il flusso principale è già funzionante:

- invio di uno o più file, cartelle o una selezione mista;
- conservazione delle cartelle annidate e vuote;
- ricezione tramite codice di un manifest con limiti espliciti prima di
  accettare il download principale;
- uso del prompt nativo di `croc` per accettare o rifiutare il trasferimento
  principale;
- visualizzazione dell'output di `croc` nella GUI;
- generazione di un solo codice visibile all'utente, con codici di controllo
  interni nascosti;
- visualizzazione degli elementi principali, della dimensione totale e delle
  informazioni SHA-256 per ogni file prima del download principale;
- ricezione in staging isolato, controllo del manifest esatto e pubblicazione
  del risultato solo dopo la verifica;
- build locale con PyInstaller;
- download automatico del binario `croc` durante la build;
- versione `croc` fissata e verifica SHA-256 per le piattaforme supportate;
- bundle finale con `croc` incluso;
- artefatti `onedir` automatizzati e testabili per Linux x86_64, Windows
  x86_64, macOS Intel e macOS Apple Silicon.

La prima alpha pubblica viene distribuita dalla
[pagina GitHub Releases](https://github.com/gaumeloth/MoonTransfer/releases)
come archivi `onedir` pre-buildati. Le build non sono firmate né notarizzate e
sono destinate ai primi test, non all'uso in produzione. Non sono ancora
disponibili installer nativi.

Su Linux e Windows l'archivio contiene una cartella portabile `MoonTransfer`: va
mantenuta interamente, non soltanto il suo eseguibile. Su macOS contiene invece
il bundle applicazione `MoonTransfer.app`, che deve essere mantenuto integro
allo stesso modo.

## Guida rapida

Per usare l'alpha pre-buildata, segui questi passaggi nell'ordine:

1. apri la [pagina Releases](https://github.com/gaumeloth/MoonTransfer/releases);
2. apri la release alpha più recente;
3. scarica l'archivio adatto al tuo sistema operativo e alla tua architettura;
4. estrai l'intero archivio;
5. apri la cartella estratta e avvia MoonTransfer.

Quando usi un archivio pre-buildato non devi installare Python, `uv` o `croc`.

## Scaricare un'alpha pre-buildata

I file delle release hanno nomi come:

```text
MoonTransfer-0.1.0-alpha.1-linux-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.1-windows-x86_64.zip
MoonTransfer-0.1.0-alpha.1-macos-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.1-macos-arm64.tar.gz
```

Il numero di versione potrebbe essere più recente rispetto all'esempio. Scarica
soltanto file allegati alla [pagina Releases ufficiale di
MoonTransfer](https://github.com/gaumeloth/MoonTransfer/releases).

Espandi solo il sistema operativo che stai usando.

<details>
<summary>Linux</summary>

L'archivio Linux pubblicato supporta attualmente sistemi Intel/AMD x86_64. Puoi
controllare la tua architettura con:

```sh
uname -m
```

Se l'output è `x86_64`, scarica il file che termina in
`linux-x86_64.tar.gz`. Estrailo, apri la cartella con la versione ottenuta e
avvia il file `MoonTransfer`.

Da un terminale aperto dentro la cartella estratta puoi invece eseguire:

```sh
./MoonTransfer
```

Linux ARM64 è supportato dagli strumenti di build ma al momento non viene
pubblicato come artefatto di release automatizzato. Su quell'architettura crea
la build dal sorgente.

</details>

<details>
<summary>Windows</summary>

L'archivio Windows pubblicato supporta attualmente sistemi Intel/AMD x86_64,
inclusa la maggior parte dei computer con Windows 10 e Windows 11.

1. Scarica il file che termina in `windows-x86_64.zip`.
2. Fai click destro sul file ZIP e scegli **Estrai tutto**.
3. Apri la cartella con la versione estratta.
4. Fai doppio click su `MoonTransfer.exe`.

Non avviare l'eseguibile direttamente da dentro il file ZIP e non separarlo
dalla cartella `_internal`.

L'alpha non è firmata, quindi Microsoft Defender SmartScreen potrebbe mostrare
un avviso relativo a un autore sconosciuto. Controlla che l'archivio provenga
dalla pagina Releases ufficiale e verificane il checksum prima di scegliere
**Ulteriori informazioni > Esegui comunque**.

</details>

<details>
<summary>macOS</summary>

Scarica l'archivio corrispondente al processore del Mac:

- `macos-arm64.tar.gz` per Mac Apple Silicon con processore serie M;
- `macos-x86_64.tar.gz` per Mac Intel.

Fai doppio click sull'archivio scaricato per estrarlo, apri la cartella con la
versione ottenuta e avvia `MoonTransfer.app`.

L'alpha non è firmata né notarizzata. Al primo avvio fai Control-click su
`MoonTransfer.app`, scegli **Apri** e conferma. A seconda della versione di
macOS, puoi autorizzarla anche da **Impostazioni di Sistema > Privacy e
sicurezza**.

</details>

Ogni release alpha contiene anche `SHA256SUMS`, che elenca il digest SHA-256
atteso per ogni archivio scaricabile e permette di controllare che il download
sia completo e non modificato.

## Scaricare il sorgente

Creare la build dal sorgente resta utile per chi contribuisce, per le
architetture non distribuite come release o per chi vuole controllare l'intero
processo di build.

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
<summary>Linux</summary>

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
<summary>macOS</summary>

Dalla cartella del progetto:

```sh
./scripts/build.sh
```

Il comando può essere lanciato da fish, bash o zsh come `./scripts/build.sh`.
Non eseguirlo come `fish scripts/build.sh`.

Se la build termina correttamente, troverai il bundle applicazione in:

```text
dist/MoonTransfer.app
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

L'icona dell'applicazione ha un unico sorgente PNG versionato. Qt carica
direttamente quel PNG durante l'esecuzione. Su Windows e macOS, PyInstaller usa
la dipendenza di sviluppo Pillow per convertirlo nell'icona nativa
dell'applicazione durante la build, quindi non è necessario mantenere sorgenti
`.ico` e `.icns` separati.

Per controllare l'ultima release upstream di `croc` senza cambiare il pin di
build:

```sh
uv run --frozen python tools/fetch_croc.py --latest
```

</details>

## Avviare MoonTransfer

Dopo la build, usa l'output descritto qui sotto per il tuo sistema operativo. Su
Linux e Windows mantieni unita l'intera cartella generata: l'eseguibile deve
restare accanto ai file e alle cartelle creati da PyInstaller. Su macOS mantieni
intatto il bundle dell'applicazione.

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

Apri `dist/` nel Finder e avvia:

```text
MoonTransfer.app
```

Al momento l'applicazione non è firmata né notarizzata. Se macOS ne blocca il
primo avvio, fai Control-click su `MoonTransfer.app`, scegli **Apri** e conferma.
A seconda della versione di macOS, puoi autorizzarla anche da **Impostazioni di
Sistema > Privacy e sicurezza**.

Dalla cartella del progetto puoi anche chiedere al Finder di aprire
l'applicazione con:

```sh
open dist/MoonTransfer.app
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

### Inviare file e cartelle

Sul computer del mittente:

1. apri MoonTransfer;
2. vai nella scheda **Invia**;
3. trascina file e cartelle nell'elenco di selezione oppure usa **Aggiungi
   file** e **Aggiungi cartella**;
4. controlla l'elenco e, se necessario, usa **Rimuovi** o **Svuota**;
5. premi **Invia**;
6. attendi che MoonTransfer analizzi la selezione e calcoli gli hash SHA-256;
7. comunica al destinatario il codice visualizzato.

Il codice permette prima al destinatario di scaricare un manifest con limiti
espliciti contenente percorsi selezionati, dimensioni e hash SHA-256 di ogni
file. MoonTransfer apre poi un unico trasferimento `croc` principale per
l'intero payload e attende che il destinatario lo accetti o lo rifiuti tramite
il prompt nativo di `croc`.

Durante il trasferimento principale, MoonTransfer mostra avanzamento
complessivo, dimensione inviata, velocità attuale, tempo trascorso e tempo
stimato rimanente quando `croc` fornisce informazioni di progresso sufficienti.

MoonTransfer analizza e calcola il fingerprint dei file regolari in background
prima di mostrare il codice. Controlla nuovamente l'albero selezionato prima di
avviare il processo principale. Il pulsante **Stop** può annullare preparazione,
verifica o trasferimento attivo.

Il codice è monouso: serve per quel trasferimento e non va riutilizzato.

### Ricevere file e cartelle

Sul computer del destinatario:

1. apri MoonTransfer;
2. vai nella scheda **Ricevi**;
3. incolla il codice ricevuto;
4. scegli la cartella di destinazione;
5. premi **Ricevi**;
6. controlla gli elementi principali, il numero di file e cartelle, la
   dimensione totale e le informazioni SHA-256 mostrate da MoonTransfer;
7. espandi i dettagli del manifest se ti servono percorso, dimensione e hash di
   ogni file;
8. accetta o rifiuta il trasferimento;
9. se esiste già un singolo file con lo stesso nome, scegli se non scaricarlo,
   sovrascriverlo o salvare il file in arrivo con un altro nome;
10. se una cartella o un gruppo è in conflitto con contenuto esistente,
    rifiutalo oppure usa il nome univoco proposto;
11. attendi il completamento del trasferimento.

Il payload principale viene scaricato solo dopo che MoonTransfer accetta il
prompt del trasferimento principale di `croc`. Se rifiuti il trasferimento,
MoonTransfer si collega solo per rifiutare il trasferimento principale e non ne
scarica il contenuto. Al termine MoonTransfer verifica l'insieme esatto dei
percorsi, i tipi degli elementi, le dimensioni e gli hash SHA-256 di ogni file
prima di pubblicare qualunque elemento nella destinazione finale.

Il confronto con la destinazione e la verifica SHA-256 finale vengono eseguiti
in background. Il pulsante **Stop** resta disponibile durante questi controlli.

Durante il trasferimento principale, MoonTransfer mostra avanzamento
complessivo, dimensione scaricata, velocità attuale, tempo trascorso e tempo
stimato rimanente quando `croc` fornisce informazioni di progresso sufficienti.

Un singolo file o una singola cartella ricevuti conservano il nome originale
dell'elemento principale. Una selezione con più elementi principali viene
salvata in una cartella contenitore `MoonTransfer`. Le cartelle esistenti non
vengono mai unite o sovrascritte ricorsivamente: MoonTransfer propone invece un
nome univoco come `MoonTransfer (1)`.

### Limiti attuali dei payload

MoonTransfer accetta attualmente file regolari e cartelle ordinarie, incluse
quelle vuote. Collegamenti simbolici, elementi simili alle junction, socket,
FIFO, dispositivi e altri oggetti speciali del filesystem vengono rifiutati
invece di essere seguiti o ricreati.

Un payload può contenere al massimo 10.000 elementi nel manifest e 256 elementi
principali selezionati. Il manifest è limitato a 4 MiB. Non si possono
selezionare come elementi principali separati una cartella e uno dei suoi
discendenti; vengono inoltre rifiutati nomi principali che entrerebbero in
conflitto su filesystem case-insensitive o che normalizzano Unicode.

Se il trasferimento non parte, verifica che entrambi i computer siano connessi a
Internet e che eventuali firewall o reti aziendali non blocchino le connessioni
usate da `croc`.

## Per chi contribuisce

### Stato del progetto e roadmap

MoonTransfer è in una fase di sviluppo iniziale attiva. Offre già un flusso
grafico di invio/ricezione, include nella build un binario `croc` fissato e
verificato tramite checksum, contiene test unitari per la logica non-GUI e
pubblica archivi alpha nativi pre-buildati per le piattaforme principali.

Possibili miglioramenti futuri, in ordine indicativo:

- raccogliere feedback sulla prima alpha e continuare a validare gli artefatti
  `onedir` automatizzati sui rispettivi sistemi;
- validare il target Android sperimentale basato su Kivy, inclusi
  l'integrazione con lo Storage Access Framework, l'esecuzione in background e
  il packaging di `croc`, prima di considerare Android una piattaforma
  supportata;
- aggiungere firma e notarizzazione dove opportuno, quindi valutare formati di
  distribuzione più nativi come AppImage, un installer Windows e un'immagine
  disco macOS;
- permettere al mittente di scegliere il nome del contenitore per payload con
  più elementi principali;
- ricordare l'ultima cartella di destinazione usata;
- aggiungere impostazioni avanzate per relay custom di `croc`;
- separare ulteriormente logica di trasferimento, parsing del progresso e
  interfaccia grafica;
- aggiungere altri test automatici per parsing output, argomenti di `croc` e
  gestione errori;
- eseguire automaticamente sui sistemi principali il controllo di compatibilità
  con l'ultima release di `croc`.

L'idea guida è restare vicini alla filosofia Unix: MoonTransfer deve fare una
cosa sola, delegare bene a `croc`, mantenere il comportamento leggibile e non
nascondere inutilmente gli errori.

### Vincoli di progettazione

Le contribuzioni dovrebbero preservare l'ambito attuale del progetto:

- MoonTransfer è un wrapper grafico intorno a `croc`, non un sostituto di
  `croc`. Trasferimento file, negoziazione del relay, cifratura e canale dati
  finale dovrebbero restare delegati a `croc`, salvo motivi forti per fare
  diversamente.
- Evita di aggiungere servizi esterni obbligatori. Il flusso normale di
  trasferimento non dovrebbe richiedere un server posseduto da MoonTransfer o un
  sistema di account.
- Mantieni la costruzione dei comandi `croc` centralizzata in
  `src/moontransfer/croc.py`. Così flag di trasferimento, gestione
  dell'ambiente e anteprime dei comandi nei log restano più facili da
  controllare.
- Avvia i comandi esterni tramite API strutturate di processo, non tramite
  stringhe shell. L'applicazione usa `QProcess`, evitando dipendenze da bash,
  fish, PowerShell o regole di quoting specifiche di una piattaforma.
- Preferisci errori chiari e output tecnico visibile invece di nascondere i
  fallimenti. La GUI può mostrare messaggi comprensibili, ma i dettagli tecnici
  devono aiutare a diagnosticare problemi di `croc`, rete, packaging e
  integrazione desktop.
- Mantieni riproducibili le build locali. Le build normali devono usare
  `uv.lock` committato, la versione fissata di `croc` e gli hash SHA-256
  dichiarati in `pyproject.toml`.
- Non committare file generati o binari inclusi localmente come `dist/`,
  `build/`, `.venv/`, directory di cache o `third_party/croc/`.

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

### Segnalazioni bug e log tecnici

Una segnalazione utile deve rendere il problema riproducibile senza esporre
informazioni private del trasferimento.

Quando segnali un problema, includi:

- sistema operativo e versione di mittente e destinatario quando sono coinvolti
  entrambi;
- se MoonTransfer è stato avviato con `uv run moontransfer` oppure dal bundle
  pacchettizzato in `dist/MoonTransfer/`;
- branch, commit o release usati;
- se il bundle è stato ricostruito dopo l'ultima modifica al codice o dopo un
  cambio branch;
- i passaggi precisi che hanno portato al problema;
- cosa ti aspettavi e cosa è successo invece;
- messaggi rilevanti dal pannello dei dettagli tecnici della GUI o dall'output
  del terminale.

Non incollare codici di trasferimento completi, valori grezzi di `CROC_SECRET`
o percorsi privati se non sono necessari e sicuri da condividere. MoonTransfer
mostra nei log valori brevi `code-id` per i codici interni; di solito sono più
adatti da condividere rispetto ai codici completi.

Per errori di trasferimento, includi quando possibile i log di entrambi i lati.
È utile indicare quale lato inviava, quale lato riceveva, se entrambe le build
arrivavano dallo stesso commit e se potrebbero essere coinvolti firewall, VPN,
proxy o reti aziendali.

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

Se testi l'applicazione pacchettizzata in `dist/`, ricostruiscila dopo modifiche
al codice o dopo aver cambiato branch. Il bundle generato non viene aggiornato
automaticamente e potrebbe contenere ancora codice precedente.

### Manutenzione della documentazione

La documentazione per utenti e contributori dovrebbe cambiare insieme al
comportamento che descrive. Una pull request dovrebbe aggiornare sia `README.md`
sia `README.it.md` quando modifica:

- flussi visibili all'utente, etichette, dialoghi, warning o messaggi di errore;
- comandi di installazione, prerequisiti, build o avvio;
- versioni Python supportate, gestione dipendenze o uso di `uv.lock`;
- argomenti dei comandi `croc`, gestione dei codici di trasferimento,
  comportamento dei relay, flusso dei metadati o verifica del trasferimento;
- file generati, struttura della repository, percorsi ignorati o comportamento
  del packaging;
- comandi di test, passaggi di verifica manuale o flusso di contribuzione;
- informazioni di licenza o componenti di terze parti inclusi nel bundle.

I due README devono mantenere lo stesso ordine delle sezioni e gli stessi fatti.
Non devono essere traduzioni parola per parola: preferisci una formulazione
chiara in ogni lingua, soprattutto quando una traduzione letterale sarebbe poco
naturale.

Quando documenti comandi, mantieni esempi copiabili ed eseguibili e controlla
che percorsi, nomi degli script e flag esistano davvero nella repository. Non
documentare funzionalità pianificate come se esistessero già: le idee future
vanno nella roadmap o in una issue.

### Futuro CONTRIBUTING.md

Per ora il README è la guida canonica per chi contribuisce. Questo mantiene il
progetto piccolo ed evita di dividere le istruzioni essenziali di setup tra più
file.

Se la documentazione per contributori diventasse troppo grande, potrà essere
spostata in un `CONTRIBUTING.md` separato. In quel caso:

- mantieni il README rivolto agli utenti su download, build, avvio, uso,
  troubleshooting, licenza e un breve punto d'ingresso per contribuire;
- sposta in `CONTRIBUTING.md` il flusso dettagliato delle pull request, la
  politica di test, le note architetturali e le attività di manutenzione;
- linka `CONTRIBUTING.md` da entrambi i README;
- mantieni allineata la documentazione inglese e italiana, con file equivalenti
  tradotti oppure con una nota chiara su quale file è autorevole.

### Dove intervenire

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
- `tools/fetch_croc.py`: selezione della release `croc` fissata, download,
  verifica checksum, estrazione archivio e installazione del binario incluso nel
  bundle.
- `tools/check_latest_croc.py`: controlli di compatibilità con l'ultima release
  upstream di `croc`.
- `tools/package_release.py`: controllo host/target, verifica della versione di
  `croc` inclusa e creazione degli archivi di release versionati con licenza e
  documentazione.
- `scripts/build.sh` e `scripts/build.ps1`: wrapper di build rivolti all'utente
  e controlli dei prerequisiti.
- `MoonTransfer.spec`: configurazione di packaging `onedir` PyInstaller,
  compreso il bundle applicazione nativo per macOS.
- `.github/workflows/release-builds.yml`: automazione di test, build, artefatti,
  checksum e bozze di pre-release su runner nativi.
- `.github/dependabot.yml`: pull request mensili per aggiornare le GitHub Action
  fissate.

Quando modifichi un modulo runtime, aggiorna o aggiungi quando possibile il test
corrispondente in `tests/`. I nomi dei test rispecchiano già la maggior parte
dei moduli runtime e di manutenzione.

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

### Policy sulla versione Python

La compatibilità Python è dichiarata in due punti:

- `pyproject.toml`, tramite `requires-python`;
- `.python-version`, usato da strumenti come `uv` per selezionare una runtime
  compatibile.

Mantieni allineati entrambi i file. Al momento MoonTransfer supporta Python
`>=3.13,<3.15`, quindi sono accettate le versioni Python 3.13.x e 3.14.x.

Se cambia l'intervallo di versioni Python supportato:

1. aggiorna `requires-python` in `pyproject.toml`;
2. aggiorna `.python-version` con lo stesso intervallo;
3. aggiorna le istruzioni Python in entrambi i README;
4. esegui `uv lock` se la risoluzione delle dipendenze può essere influenzata;
5. esegui `uv sync --frozen --dev`;
6. esegui i controlli automatici;
7. esegui una build se la modifica può influenzare il packaging.

Non restringere l'intervallo Python supportato senza un motivo concreto, come un
vincolo di dipendenza, una release Python non supportata o un comportamento a
runtime non gestibile in modo pulito.

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
- [PyInstaller](https://pyinstaller.org/en/stable/), creazione del bundle;
- [Pillow](https://pillow.readthedocs.io/en/stable/), conversione dell'icona
  dell'applicazione durante la build.

### Test automatici

I test unitari coprono la logica non-GUI separata nei moduli runtime e negli
strumenti di manutenzione: inventario dei payload e verifica esatta degli
alberi, validazione del protocollo, costruzione dei comandi, parsing dell'output
di trasferimento, messaggi di stato, helper di integrazione desktop, separazione
dell'output dei processi, selezione degli archivi `croc` fissati e helper per il
packaging degli archivi di release e per il controllo dell'ultima release.

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

### Aspettative di test per tipo di modifica

Usa l'insieme di test più piccolo che copre il rischio della modifica, poi
allargalo quando il comportamento attraversa più moduli o più piattaforme.

- Modifiche solo alla documentazione: esegui `git diff --check`. Se la
  documentazione descrive comandi o percorsi, confrontali anche con la
  repository.
- Modifiche agli argomenti di `croc`, a `CROC_SECRET`, alle anteprime dei
  comandi o alla configurazione isolata: esegui `tests/test_croc.py`,
  `tests/test_check_latest_croc.py` e l'intera suite di test unitari.
- Modifiche al JSON dei metadati, ai codici generati, alla validazione dei nomi,
  alla validazione hash, ai manifest o alla versione del protocollo: esegui
  `tests/test_protocol.py`, `tests/test_payload.py` e `tests/test_files.py`.
- Modifiche alla scansione della sorgente, alla destinazione, a
  sovrascrittura/rinomina, hashing, verifica dell'albero ricevuto o
  posizionamento finale: esegui `tests/test_payload.py` e
  `tests/test_files.py`, poi fai un test manuale di ricezione.
- Modifiche al parsing del progresso o alle statistiche mostrate durante il
  trasferimento: esegui `tests/test_progress.py` con esempi rappresentativi di
  output di `croc`.
- Modifiche ai testi di stato rivolti all'utente: esegui
  `tests/test_messages.py` e controlla manualmente le diciture nella GUI.
- Modifiche al ciclo di vita dei processi, risposte su stdin, cancellazione o
  parsing di stdout/stderr: esegui `tests/test_runner.py` e fai un test manuale
  di trasferimento.
- Modifiche all'apertura cartelle o all'integrazione desktop: esegui
  `tests/test_desktop.py` e, se possibile, testa manualmente la piattaforma
  interessata.
- Modifiche a `tools/fetch_croc.py`, `tools/check_latest_croc.py`, versioni
  `croc` fissate o hash di release: esegui i test dei tool relativi e il
  controllo sull'ultima release di `croc` quando è disponibile l'accesso alla
  rete.
- Modifiche ai wrapper di build, alla configurazione PyInstaller o alle risorse
  pacchettizzate: esegui lo script di build per la piattaforma interessata e
  avvia il bundle generato da `dist/MoonTransfer/`.
- Modifiche al flusso principale di trasferimento o al coordinamento GUI:
  esegui l'intera suite di test unitari, avvia MoonTransfer manualmente e fai un
  test manuale di trasferimento.

### Test manuale di trasferimento

Per verificare il flusso completo durante lo sviluppo puoi usare due istanze
dell'app sulla stessa macchina:

1. apri due istanze di MoonTransfer;
2. nella prima istanza seleziona un piccolo file e una cartella contenente un
   file annidato e una cartella vuota;
3. copia il codice mostrato;
4. nella seconda istanza ricevi in una cartella diversa;
5. controlla che il contenitore `MoonTransfer` includa ogni elemento principale,
   il file annidato e la cartella vuota.

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

### Artefatti di release automatizzati

`.github/workflows/release-builds.yml` verifica lo stesso flusso di packaging
`onedir` su runner GitHub nativi. Al momento copre:

- Linux x86_64 su Ubuntu 22.04;
- Windows x86_64 su Windows Server 2022;
- macOS x86_64 su un runner Intel;
- macOS ARM64 su un runner Apple Silicon.

Ogni job installa le versioni fissate nel workflow di `uv` e Python 3.13,
controlla `uv.lock`, installa le dipendenze bloccate, esegue l'intera suite di
test unitari, scarica il binario `croc` verificato tramite checksum, builda
MoonTransfer, controlla la versione di `croc` inclusa e crea un archivio
scaricabile.

Gli artefatti Linux e macOS usano `tar.gz` per conservare permessi eseguibili e
link simbolici. Windows usa ZIP. L'archivio macOS contiene un bundle
`MoonTransfer.app`, mentre le altre piattaforme mantengono la normale struttura
`onedir` di PyInstaller. Ogni archivio contiene anche `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `README.md` e `README.it.md`.

Le pull request, i push su `main` e le esecuzioni manuali del workflow creano
artefatti di prova senza pubblicare una release. Le build senza tag usano una
versione `dev` contenente il numero dell'esecuzione e il prefisso del commit.
Gli artefatti sono disponibili nel riepilogo dell'esecuzione del workflow per
14 giorni e possono essere scaricati per i test manuali sui sistemi
destinazione.

La pubblicazione è intenzionalmente più restrittiva:

- solo tag come `v0.1.0-alpha.1`, `v0.1.0-beta.1` o `v0.1.0-rc.1` avviano il
  job di release;
- la base numerica del tag deve corrispondere a `[project].version` in
  `pyproject.toml`;
- tutte le build di piattaforma devono terminare prima di avviare il job di
  release;
- il workflow genera `SHA256SUMS`;
- GitHub crea una bozza marcata come pre-release, mai una release pubblicata
  immediatamente;
- una nuova esecuzione può aggiornare una bozza esistente ma si rifiuta di
  sovrascrivere una release pubblicata.

Il progetto è attualmente in fase alpha: comportamento principale e
distribuzione sono ancora in espansione e validazione. Il passaggio a beta
andrebbe fatto solo quando l'insieme di funzionalità previsto per la prima
release stabile sarà completo e lo sviluppo si concentrerà soprattutto su
compatibilità, correzioni di usabilità e stabilizzazione. Il workflow attuale
non accetta intenzionalmente tag stabili.

Per preparare una release alpha o beta:

1. assicurati che il commit previsto sia su `main` e che tutti i controlli
   normali passino;
2. aggiorna `[project].version` e `uv.lock` se cambia la versione numerica di
   base;
3. crea un tag annotato di pre-release, per esempio
   `git tag -a v0.1.0-alpha.1 -m "MoonTransfer 0.1.0 alpha 1"`;
4. invia quel tag esatto con `git push origin v0.1.0-alpha.1`;
5. attendi il completamento di tutte le build native e del job che crea la
   bozza;
6. scarica ogni archivio dalla bozza e provalo sul sistema operativo
   corrispondente;
7. confronta i file scaricati con `SHA256SUMS` e controlla note di release e
   documenti inclusi;
8. pubblica manualmente la bozza solo dopo il superamento dei test richiesti.

Non spostare o riutilizzare un tag che potrebbe essere già stato scaricato. Se
una release candidata è difettosa, correggi il problema e crea il tag di
pre-release successivo, per esempio `v0.1.0-alpha.2`.

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

Il controllo di trasferimento esegue tre brevi sessioni con il binario `croc`
più recente: ricezione automatica con i flag usati per i metadati, accettazione
tramite prompt con i flag usati per il payload principale e rifiuto tramite
prompt. Le sessioni accettate trasferiscono più elementi principali includendo
una cartella annidata, una cartella vuota e un nome file Unicode, quindi
verificano il contenuto ricevuto. La sessione rifiutata controlla che non venga
creato alcun contenuto nella destinazione. Questi controlli richiedono accesso a
Internet e un relay `croc` raggiungibile, quindi non fanno parte del controllo
predefinito.

Se il controllo passa per una nuova release, aggiorna `[tool.moontransfer.croc]`
in `pyproject.toml` con la nuova versione e gli hash ufficiali, poi esegui la
suite di test normale prima del commit.

### Note architetturali

- MoonTransfer avvia `croc` con `QProcess`, senza passare da shell come bash,
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

Dopo il trasferimento dei metadati, il mittente verifica che gli elementi
inventariati non siano cambiati, avvia un unico processo `croc send` principale
con tutti gli elementi selezionati e rimane in attesa. Il destinatario avvia il
processo `croc` principale senza `--yes`, poi MoonTransfer scrive `y` o `n` su
quel processo in base alla scelta fatta nella GUI. In questo modo viene usato
il prompt accetta/rifiuta di `croc` invece di un trasferimento di decisione
separato di MoonTransfer. Se il destinatario rifiuta il payload, il
trasferimento principale viene rifiutato e nessun contenuto del payload viene
scaricato.

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

- Le operazioni locali potenzialmente lunghe vengono eseguite in un `QThread`
  annullabile: inventario e fingerprint del mittente, confronto con contenuto
  già presente, verifica finale dell'albero ricevuto e copie tra filesystem. Il
  mittente registra l'identità di ogni file sorgente assieme al suo hash,
  analizza nuovamente gli elementi selezionati e controlla i fingerprint prima
  di avviare il processo `croc` principale. La verifica finale del destinatario
  resta autorevole perché `croc` apre i percorsi sorgente dopo l'ultimo controllo
  locale di MoonTransfer.
- La riproducibilità della build dipende da `uv.lock`, dalla versione di `croc`
  fissata e dagli hash SHA-256 versionati in `pyproject.toml`.

### Target Android sperimentale

Il lavoro di fattibilità per Android è isolato sotto `android/` e non
sostituisce l'applicazione desktop PySide6. Usa un ambiente Python 3.13
separato, Kivy, Buildozer e un proprio `uv.lock`. L'albero sorgente Android
viene generato da una lista esplicita di moduli MoonTransfer indipendenti da Qt,
così il protocollo viene condiviso senza aggiungere Kivy alle dipendenze runtime
desktop.

Il prototipo attuale include un eseguibile `croc` ARM64 verificato e può inviare
o ricevere un file tra Android e l'applicazione desktop usando il manifest
condiviso del protocollo v2 e lo Storage Access Framework di Android. Un
foreground service `dataSync` possiede i trasferimenti attivi, quindi passare a
un'altra applicazione non interrompe `croc`; una notifica privata legata allo
stato mostra fase e metriche di avanzamento disponibili e fornisce un'azione di
arresto legata alla sessione, quindi lascia un risultato dismissibile. Il
servizio gestisce i timeout `dataSync` di Android 15 e i riavvii sticky non
validi, ma le sessioni interrotte non possono ancora essere riprese. File
multipli, cartelle e packaging release non sono implementati.
Configurazione, diagnostica, comandi di build, dettagli
progettuali e test manuali di compatibilità sono documentati in
[android/README.it.md](android/README.it.md).

### Struttura

```text
MoonTransfer/
├─ .github/
│  ├─ workflows/
│  │  └─ release-builds.yml
│  └─ dependabot.yml
├─ android/
│  ├─ app/
│  │  └─ moontransfer_android/
│  │     ├─ __init__.py
│  │     ├─ android_runtime.py
│  │     ├─ application.py
│  │     ├─ receiver.py
│  │     ├─ sender.py
│  │     ├─ service.py
│  │     ├─ service_client.py
│  │     ├─ service_protocol.py
│  │     ├─ storage.py
│  │     ├─ transfer_service.py
│  │     └─ transport.py
│  ├─ recipes/
│  │  ├─ croc/
│  │  │  └─ __init__.py
│  │  └─ README.md
│  ├─ .python-version
│  ├─ README.md
│  ├─ README.it.md
│  ├─ buildozer.spec
│  ├─ pyproject.toml
│  └─ uv.lock
├─ src/
│  └─ moontransfer/
│     ├─ assets/
│     │  ├─ branding/
│     │  │  └─ moontransfer-logo.png
│     │  └─ icons/
│     │     └─ moontransfer-icon.png
│     ├─ app.py
│     ├─ cancellation.py
│     ├─ croc.py
│     ├─ desktop.py
│     ├─ files.py
│     ├─ messages.py
│     ├─ payload.py
│     ├─ protocol.py
│     ├─ progress.py
│     ├─ resources.py
│     ├─ runner.py
│     ├─ tasks.py
│     ├─ transfer.py
│     └─ widgets.py
├─ tools/
│  ├─ android.py
│  ├─ build.py
│  ├─ check_latest_croc.py
│  ├─ fetch_croc.py
│  ├─ package_release.py
│  └─ prepare_android.py
├─ scripts/
│  ├─ android.sh
│  ├─ build.ps1
│  └─ build.sh
├─ tests/
│  ├─ test_android_setup.py
│  ├─ test_android_receiver.py
│  ├─ test_android_sender.py
│  ├─ test_android_service.py
│  ├─ test_android_storage.py
│  ├─ test_android_transport.py
│  ├─ test_app.py
│  ├─ test_check_latest_croc.py
│  ├─ test_croc.py
│  ├─ test_desktop.py
│  ├─ test_fetch_croc.py
│  ├─ test_files.py
│  ├─ test_messages.py
│  ├─ test_package_release.py
│  ├─ test_payload.py
│  ├─ test_protocol.py
│  ├─ test_progress.py
│  ├─ test_runner.py
│  ├─ test_tasks.py
│  ├─ test_transfer.py
│  └─ test_widgets.py
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
android/.buildozer/
android/.venv/
build/
dist/
release/
third_party/croc/
__pycache__/
```

Se uno di questi percorsi appare in `git status`, lascialo fuori dal commit.

## Licenze

MoonTransfer è distribuito sotto la GNU General Public License versione 3.
Vedi il testo completo della licenza in [LICENSE](LICENSE).

I componenti di terze parti mantengono le rispettive licenze. Vedi
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) per i componenti di terze
parti, in particolare `croc`, PySide6/Qt for Python, Kivy, Buildozer e
python-for-android.
