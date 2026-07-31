# Esperimento Android di MoonTransfer

Versione inglese: [README.md](README.md)

Questa directory contiene un ambiente Kivy e Buildozer isolato per il prototipo
di fattibilità Android. Non sostituisce l'applicazione desktop PySide6 e non fa
parte degli artefatti delle release desktop.

## Ambito attuale

Lo scaffold attualmente fornisce:

- un ambiente di sviluppo Python 3.13 e Kivy 2.3.1;
- un entry point Kivy minimale che importa il protocollo MoonTransfer condiviso;
- sorgenti di build Android generati contenenti solamente moduli MoonTransfer
  esplicitamente approvati e indipendenti da Qt;
- una configurazione Buildozer e python-for-android con versioni fissate;
- un target APK di debug `arm64-v8a`;
- una directory di recipe private per la futura integrazione Android di `croc`.

Non sono ancora disponibili selezione dei file, trasferimenti, servizi Android
o un eseguibile `croc` incluso. Viene dichiarato solamente il permesso
`INTERNET`. L'accesso ai file userà lo Storage Access Framework di Android
invece di permessi di archiviazione estesi.

## Prerequisiti del sistema host

Le build Android richiedono Linux o macOS. La configurazione attuale prevede
Java 17, i normali strumenti di compilazione nativa e Rust. Buildozer scarica
Android SDK e NDK configurati quando necessario.

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
  pkgconf cmake libffi openssl automake gettext make gcc
```

Installa Rust con il metodo documentato su <https://rustup.rs/> e assicurati
che `cargo` e `rustc` siano disponibili nel `PATH`.

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

`doctor` controlla i prerequisiti del sistema host. `prepare` ricrea l'albero
dei sorgenti generati sotto `build/android/source`. `run` avvia lo scaffold
Kivy sul desktop per un rapido smoke test della GUI. `build` produce un APK di
debug sotto `dist/android`.

La prima esecuzione può scaricare pacchetti Python, strumenti Android e archivi
sorgente. I sorgenti generati e gli output di build non devono essere modificati
o committati.

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
