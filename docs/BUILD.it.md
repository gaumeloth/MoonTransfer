# Compilare e avviare MoonTransfer desktop

[English](BUILD.md) | [MoonTransfer](../README.it.md)

Esegui i comandi dalla radice del checkout, salvo diversa indicazione. Questa guida riguarda il desktop; per Android usa la [guida dedicata](../android/README.it.md).

## Indice

- [Scaricare il sorgente](#scaricare-il-sorgente)
- [Preparare il sistema](#preparare-il-sistema)
- [Creare la build](#creare-la-build)
- [Avviare MoonTransfer](#avviare-moontransfer)

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
poi PyInstaller usando `MoonTransfer.spec`. Prima del packaging scrive il file
ignorato `build/generated/build-info.json`. Una build locale riceve l'identità
`0.1.0-dev.<commit>`; una build eseguita su un checkout pulito corrispondente a
un tag di pre-release esatto riceve la versione del tag. L'automazione di
release passa versione e commit in modo esplicito, così il nome dell'archivio e
la versione mostrata dall'applicazione non possono divergere.

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
