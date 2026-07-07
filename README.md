# MoonTransfer

MoonTransfer è una GUI cross-platform pensata per inviare e ricevere file in modo semplice usando `croc` sotto al cofano.

L'obiettivo è rendere il trasferimento sicuro di file utilizzabile anche da persone non tecniche:

1. scegli un file;
2. premi **Invia**;
3. condividi il codice monouso;
4. l'altra persona apre MoonTransfer, incolla il codice e riceve il file.

MoonTransfer **non implementa un protocollo crittografico proprio**. Usa `croc` come motore di trasferimento e fornisce una GUI semplice per interagirci.

---

## Stato del progetto

Versione iniziale / MVP.

Funzionalità già previste o implementate:

- invio di file;
- ricezione di file;
- output stile terminale integrato nella GUI;
- estrazione automatica del codice generato da `croc`;
- ricezione tramite variabile d'ambiente `CROC_SECRET`;
- gestione ambiente Python con `uv`;
- build con PyInstaller;
- download automatico di `croc` durante la build;
- bundle del binario `croc` dentro l'applicazione finale.

Funzionalità non ancora implementate:

- invio cartelle tramite GUI;
- cronologia trasferimenti;
- configurazione relay custom;
- QR code;
- installer firmati;
- pipeline GitHub Actions per release automatiche;
- pacchetti `.deb`, `.rpm`, AppImage, `.dmg` o installer Windows.

---

## Come funziona

MoonTransfer avvia `croc` come processo esterno e mostra l'output nella GUI.

### Invio

In modalità invio, MoonTransfer esegue concettualmente:

```text
croc --disable-clipboard send <file>
```

`croc` genera un codice monouso. MoonTransfer intercetta la riga dell'output contenente il codice e lo mostra nella GUI.

### Ricezione

In modalità ricezione, MoonTransfer non passa il codice come argomento della riga di comando. Imposta invece la variabile d'ambiente:

```text
CROC_SECRET=<codice>
```

e poi esegue:

```text
croc --yes --overwrite
```

Questo evita di esporre il codice direttamente negli argomenti del processo, cosa particolarmente utile su Linux/macOS dove gli argomenti dei processi possono essere ispezionabili da altri strumenti locali.

---

## Requisiti per lo sviluppo

Per sviluppare o buildare MoonTransfer servono:

- Git;
- `uv`;
- una versione di Python compatibile con `pyproject.toml`;
- accesso a Internet durante la build, perché `tools/fetch_croc.py` scarica l'ultima versione disponibile di `croc`.

---

## Installare uv

### Arch Linux

```bash
sudo pacman -S uv
```

### Linux/macOS tramite installer ufficiale

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Dopo l'installazione, verifica:

```bash
uv --version
```

---

## Clonare la repository

```bash
git clone https://github.com/gaumeloth/MoonTransfer.git
cd MoonTransfer
```

---

## Setup ambiente di sviluppo

Dalla root del progetto:

```bash
uv sync
```

Questo comando crea/aggiorna l'ambiente virtuale `.venv` e installa le dipendenze definite in `pyproject.toml` e `uv.lock`.

---

## Scaricare croc per lo sviluppo

Prima di avviare la GUI in modalità sviluppo, esegui:

```bash
uv run python tools/fetch_croc.py
```

Questo script:

1. controlla l'ultima release disponibile di `croc`;
2. scarica l'asset corretto per il sistema operativo corrente;
3. verifica il checksum;
4. estrae il binario;
5. lo posiziona in:

```text
third_party/croc/
```

Su Linux/macOS il binario sarà:

```text
third_party/croc/croc
```

Su Windows sarà:

```text
third_party/croc/croc.exe
```

Verrà creato anche un file:

```text
third_party/croc/VERSION
```

La cartella `third_party/croc/` è generata automaticamente e non dovrebbe essere committata in git.

---

## Avviare MoonTransfer in sviluppo

Dopo aver eseguito `uv sync` e `tools/fetch_croc.py`:

```bash
uv run moontransfer
```

In alternativa:

```bash
uv run python src/moontransfer/app.py
```

---

## Build da sorgente

MoonTransfer usa PyInstaller per produrre un pacchetto eseguibile in modalità `onedir`.

Durante la build:

1. viene eseguito `tools/fetch_croc.py`;
2. viene scaricata/aggiornata la versione di `croc`;
3. PyInstaller include `croc` nel bundle finale;
4. viene generata la cartella `dist/MoonTransfer/`.

---

## Build su Linux/macOS

Dalla root del progetto:

```bash
./scripts/build.sh
```

Output atteso:

```text
dist/MoonTransfer/
```

Avvio dell'applicazione buildata:

```bash
./dist/MoonTransfer/MoonTransfer
```

Se lo script non è eseguibile:

```bash
chmod +x scripts/build.sh
./scripts/build.sh
```

---

## Build su Windows

Da PowerShell, nella root del progetto:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Output atteso:

```text
dist\MoonTransfer\
```

Avvio dell'applicazione buildata:

```powershell
.\dist\MoonTransfer\MoonTransfer.exe
```

---

## Struttura del progetto

```text
MoonTransfer/
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ .gitignore
├─ MoonTransfer.spec
├─ THIRD_PARTY_NOTICES.md
├─ src/
│  └─ moontransfer/
│     ├─ __init__.py
│     └─ app.py
├─ tools/
│  ├─ fetch_croc.py
│  └─ build.py
├─ scripts/
│  ├─ build.sh
│  └─ build.ps1
└─ third_party/
   └─ croc/
      ├─ croc / croc.exe
      └─ VERSION
```

Nota: `third_party/croc/`, `.cache/`, `.venv/`, `build/` e `dist/` sono generati automaticamente e non dovrebbero essere versionati.

---

## File importanti

### `src/moontransfer/app.py`

Contiene la GUI PySide6 e il wrapper intorno a `croc`.

Responsabilità principali:

- risolvere il percorso di `croc`;
- gestire invio e ricezione;
- avviare `croc` con `QProcess`;
- mostrare stdout/stderr nella GUI;
- intercettare il codice generato durante l'invio;
- impostare `CROC_SECRET` durante la ricezione.

### `tools/fetch_croc.py`

Scarica e prepara il binario `croc` per la piattaforma corrente.

Comportamento attuale:

- usa sempre la latest release disponibile online;
- verifica il checksum dell'archivio;
- aggiorna il binario locale se necessario;
- scrive `third_party/croc/VERSION`.

### `tools/build.py`

Orchestra la build:

1. esegue `tools/fetch_croc.py`;
2. esegue PyInstaller usando `MoonTransfer.spec`.

### `MoonTransfer.spec`

Specifica di PyInstaller.

Include:

- entrypoint Python;
- path `src/`;
- binario `croc`;
- configurazione `onedir`.

### `scripts/build.sh`

Script di build per Linux/macOS basato su `uv`.

### `scripts/build.ps1`

Script di build per Windows PowerShell basato su `uv`.

---

## Policy git consigliata

### Da committare

- `pyproject.toml`
- `uv.lock`
- `README.md`
- `.gitignore`
- `MoonTransfer.spec`
- `THIRD_PARTY_NOTICES.md`
- `src/`
- `tools/`
- `scripts/`

### Da non committare

- `.venv/`
- `.cache/`
- `build/`
- `dist/`
- `third_party/croc/`
- `__pycache__/`

---

## Esempio `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.egg-info/

# uv / virtualenv
.venv/

# Build
build/
dist/
*.spec.bak

# Cache
.cache/
.pytest_cache/
.ruff_cache/

# Bundled third-party binaries generated by tools/fetch_croc.py
third_party/croc/

# OS/editor
.DS_Store
Thumbs.db
.idea/
.vscode/
```

---

## Test consigliati

### 1. Test download croc

```bash
uv run python tools/fetch_croc.py
```

Controlla che venga creata la cartella:

```text
third_party/croc/
```

### 2. Test GUI in sviluppo

```bash
uv run moontransfer
```

La GUI dovrebbe aprirsi senza errori.

### 3. Test build

Linux/macOS:

```bash
./scripts/build.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

### 4. Test trasferimento locale

Puoi testare MoonTransfer anche su un singolo computer:

1. apri una prima istanza dell'app;
2. vai su **Invia**;
3. scegli un piccolo file di prova;
4. premi **Invia**;
5. copia il codice;
6. apri una seconda istanza dell'app;
7. vai su **Ricevi**;
8. incolla il codice;
9. scegli una cartella di destinazione diversa;
10. premi **Ricevi**.

Se il file viene trasferito correttamente, il wrapper GUI e `croc` stanno funzionando.

---

## Note sulla riproducibilità della build

MoonTransfer attualmente scarica sempre l'ultima versione disponibile di `croc` durante la build.

Questo comportamento è comodo perché mantiene aggiornato il motore di trasferimento, ma significa che due build eseguite in momenti diversi potrebbero includere versioni diverse di `croc`.

Per il momento questa è una scelta intenzionale del progetto.

---

## Licenze e software terzi

MoonTransfer usa e/o include software di terze parti.

Vedi:

```text
THIRD_PARTY_NOTICES.md
```

Componenti principali:

- `croc`, usato come motore di trasferimento;
- PySide6 / Qt for Python, usato per la GUI.

---

## Roadmap

Possibili miglioramenti futuri:

- supporto GUI per inviare cartelle;
- supporto drag and drop;
- QR code del codice di trasferimento;
- impostazioni per relay custom;
- profili relay;
- cronologia trasferimenti;
- verifica hash post-trasferimento;
- GitHub Actions per build automatiche;
- pacchetti release per Windows, Linux e macOS;
- firma degli eseguibili.
