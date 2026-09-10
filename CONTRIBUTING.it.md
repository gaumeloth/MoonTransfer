# Contribuire a MoonTransfer

[English](CONTRIBUTING.md) | [MoonTransfer](README.it.md)

## Indice

- [Stato del progetto e roadmap](#stato-del-progetto-e-roadmap)
- [Vincoli di progettazione](#vincoli-di-progettazione)
- [Modello di contribuzione](#modello-di-contribuzione)
- [Segnalazioni bug e log tecnici](#segnalazioni-bug-e-log-tecnici)
- [Flusso di contribuzione](#flusso-di-contribuzione)
- [Manutenzione della documentazione](#manutenzione-della-documentazione)
- [Orientamento](#orientamento)
- [Preparazione sviluppo](#preparazione-sviluppo)
- [Policy sulla versione Python](#policy-sulla-versione-python)
- [Modifiche alle dipendenze](#modifiche-alle-dipendenze)
- [Avvio in sviluppo](#avvio-in-sviluppo)
- [Test automatici](#test-automatici)
- [Aspettative di test per tipo di modifica](#aspettative-di-test-per-tipo-di-modifica)
- [Test manuale di trasferimento](#test-manuale-di-trasferimento)
- [Prima del commit](#prima-del-commit)
- [Attività di manutenzione](#attività-di-manutenzione)
- [File generati](#file-generati)
- [Controlli della documentazione](#controlli-della-documentazione)

## Stato del progetto e roadmap

MoonTransfer è in una fase di sviluppo iniziale attiva. Offre già un flusso
grafico di invio/ricezione, include nella build un binario `croc` fissato e
verificato tramite checksum, contiene test unitari per la logica non-GUI e
pubblica archivi alpha nativi pre-buildati per le piattaforme principali. La
linea pubblica attuale è `v0.1.0-alpha.4`. Android è un target con build debug e firmate,
funzionante ma sperimentale per file, cartelle e selezioni miste, non una release
supportata per l'utente finale.

Possibili miglioramenti futuri, in ordine indicativo:

- raccogliere feedback su `alpha.4` e continuare a validare gli artefatti
  `onedir` automatizzati sui rispettivi sistemi;
- continuare a consolidare il target Android basato su Kivy, in particolare
  casi limite del ciclo di vita, payload grandi o molto annidati, copertura di
  dispositivi e provider di documenti e packaging di release, prima di
  considerare Android una piattaforma supportata;
- aggiungere firma e notarizzazione dove opportuno, quindi valutare formati di
  distribuzione più nativi come AppImage, un installer Windows e un'immagine
  disco macOS;
- aggiungere impostazioni avanzate per relay custom di `croc`;
- ridurre i moduli di orchestrazione desktop e Android ancora grandi quando un
  confine concreto di responsabilità giustifica la separazione;
- estendere la copertura automatica di metadati di packaging, comportamento
  specifico delle piattaforme, errori di trasferimento e ripristino del ciclo
  di vita Android;
- eseguire automaticamente sui sistemi principali il controllo di compatibilità
  con l'ultima release di `croc`.

L'idea guida è restare vicini alla filosofia Unix: MoonTransfer deve fare una
cosa sola, delegare bene a `croc`, mantenere il comportamento leggibile e non
nascondere inutilmente gli errori.

## Vincoli di progettazione

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
  stringhe shell. Il desktop usa `QProcess`; Android usa `subprocess.Popen`, evitando dipendenze da bash,
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

## Modello di contribuzione

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

## Segnalazioni bug e log tecnici

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

## Flusso di contribuzione

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

Se modifichi documentazione per utenti o contributori, aggiorna entrambe le
lingue della guida interessata: servono struttura e informazioni equivalenti,
non una traduzione letterale. Mantieni i README come punto d'ingresso utente.

Se testi l'applicazione pacchettizzata in `dist/`, ricostruiscila dopo modifiche
al codice o dopo aver cambiato branch. Il bundle generato non viene aggiornato
automaticamente e potrebbe contenere ancora codice precedente.

## Manutenzione della documentazione

La documentazione per utenti e contributori dovrebbe cambiare insieme al
comportamento che descrive. Una pull request dovrebbe aggiornare le guide
pertinenti in inglese e italiano quando modifica:

- flussi visibili all'utente, etichette, dialoghi, warning o messaggi di errore;
- comandi di installazione, prerequisiti, build o avvio;
- versioni Python supportate, gestione dipendenze o uso di `uv.lock`;
- argomenti dei comandi `croc`, gestione dei codici di trasferimento,
  comportamento dei relay, flusso dei metadati o verifica del trasferimento;
- file generati, struttura della repository, percorsi ignorati o comportamento
  del packaging;
- comandi di test, passaggi di verifica manuale o flusso di contribuzione;
- informazioni di licenza o componenti di terze parti inclusi nel bundle.

Ogni coppia di guide deve mantenere lo stesso ordine delle sezioni e gli stessi fatti.
Non devono essere traduzioni parola per parola: preferisci una formulazione
chiara in ogni lingua, soprattutto quando una traduzione letterale sarebbe poco
naturale.

Quando documenti comandi, mantieni esempi copiabili ed eseguibili e controlla
che percorsi, nomi degli script e flag esistano davvero nella repository. Non
documentare funzionalità pianificate come se esistessero già: le idee future
vanno nella roadmap o in una issue.

## Orientamento

La [guida di build](docs/BUILD.it.md) contiene la preparazione iniziale del sistema. Consulta la [mappa architetturale](docs/ARCHITECTURE.it.md) per scegliere il modulo da modificare e la [guida alle release](docs/RELEASING.it.md) per CI e distribuzione. Tutte le modifiche a `main`, incluse quelle dei manutentori, passano da pull request.

## Preparazione sviluppo

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

## Policy sulla versione Python

La compatibilità Python è dichiarata in due punti:

- `pyproject.toml`, tramite `requires-python`;
- `.python-version`, usato da strumenti come `uv` per selezionare una runtime
  compatibile.

Mantieni allineati entrambi i file. Al momento MoonTransfer supporta Python
`>=3.13,<3.15`, quindi sono accettate le versioni Python 3.13.x e 3.14.x.

Se cambia l'intervallo di versioni Python supportato:

1. aggiorna `requires-python` in `pyproject.toml`;
2. aggiorna `.python-version` con lo stesso intervallo;
3. aggiorna le istruzioni Python nelle versioni inglesi e italiane delle guide di build e contribuzione;
4. esegui `uv lock` se la risoluzione delle dipendenze può essere influenzata;
5. esegui `uv sync --frozen --dev`;
6. esegui i controlli automatici;
7. esegui una build se la modifica può influenzare il packaging.

Non restringere l'intervallo Python supportato senza un motivo concreto, come un
vincolo di dipendenza, una release Python non supportata o un comportamento a
runtime non gestibile in modo pulito.

## Modifiche alle dipendenze

`uv.lock` è committato intenzionalmente. Rende riproducibile la risoluzione
delle dipendenze per sviluppo, test e build locali.

Se cambi le dipendenze Python:

1. modifica `pyproject.toml`;
2. aggiorna `uv.lock` con `uv lock`;
3. esegui `uv sync --frozen --dev`;
4. esegui i controlli automatici;
5. committa sia `pyproject.toml` sia `uv.lock`.

Non modificare `uv.lock` manualmente.

## Avvio in sviluppo

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

## Test automatici

I test unitari coprono la logica non-GUI separata nei moduli runtime e negli
strumenti di manutenzione: inventario dei payload e verifica esatta degli
alberi, validazione del protocollo, costruzione dei comandi, parsing dell'output
di trasferimento, messaggi di stato, helper di integrazione desktop, separazione
dell'output dei processi, selezione degli archivi `croc` fissati e helper per il
controllo e la generazione dell'identità di build, il packaging degli archivi di
release e il controllo dell'ultima release.

Coprono anche eventi simulati sui widget Qt, ma non sostituiscono l'interazione manuale con la GUI e non eseguono un trasferimento
reale per impostazione predefinita. Usa il test manuale di trasferimento per
questi controlli.

Esegui la suite di test:

```sh
uv run --frozen python -m unittest discover -s tests
```

Controlla che i moduli Python compilino:

```sh
uv run --frozen python -m compileall -q src/moontransfer tools
```

## Aspettative di test per tipo di modifica

Usa l'insieme di test più piccolo che copre il rischio della modifica, poi
allargalo quando il comportamento attraversa più moduli o più piattaforme.

- Modifiche solo alla documentazione: esegui `git diff --check`. Se la
  documentazione descrive comandi o percorsi, confrontali anche con la
  repository.
- Modifiche all'identità di build, alla propagazione della versione, ai file
  dati PyInstaller o alla gestione versione nel workflow di release: esegui
  `tests/test_build_info.py`, `tests/test_build_metadata.py`,
  `tests/test_package_release.py` e una build locale del bundle.
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
- Modifiche alla preparazione dei sorgenti Android, alla configurazione
  Buildozer, alla recipe nativa di `croc` o al packaging dell'APK: controlla
  `android/uv.lock`, esegui il sottoinsieme di test Android e
  `./scripts/android.sh doctor`, quindi crea e prepara un APK locale quando la
  modifica riguarda il toolchain o il pacchetto finale.
- Modifiche al flusso principale di trasferimento o al coordinamento GUI:
  esegui l'intera suite di test unitari, avvia MoonTransfer manualmente e fai un
  test manuale di trasferimento.

## Test manuale di trasferimento

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

## Prima del commit

Esegui questi controlli prima di committare:

```sh
uv lock --check
uv run --frozen python -m unittest discover -s tests
uv run --frozen python -m compileall -q src/moontransfer tools
git diff --check
```

Se tocchi script di build, packaging o `MoonTransfer.spec`, esegui anche lo
script di build per la piattaforma modificata.

Per modifiche specifiche di Android esegui anche:

```sh
uv lock --check --project android
PYTHONPATH="$PWD/src" uv run --project android --frozen --group build \
  python -m unittest discover -s tests -p 'test_android*.py' -v
./scripts/android.sh doctor
```

Crea e prepara anche un APK locale quando modifichi il toolchain Android, la
lista dei sorgenti generati consentiti, la recipe nativa o la validazione del
pacchetto finale.

## Attività di manutenzione

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

Il controllo di trasferimento esegue tre brevi sessioni con il binario `croc`
più recente: ricezione automatica con i flag usati per i metadati, accettazione
tramite prompt con i flag usati per il payload principale e rifiuto tramite
prompt. Le sessioni accettate trasferiscono più elementi principali includendo
una cartella annidata, una cartella vuota e un nome file Unicode, quindi
verificano il contenuto ricevuto. La sessione rifiutata controlla che non venga
creato alcun contenuto nella destinazione. Questi controlli richiedono accesso a
Internet e un relay `croc` raggiungibile, quindi non fanno parte del controllo
predefinito.

Per confrontare l'ultima release con una versione precedente di `croc` in
entrambe le direzioni di trasferimento, aggiungi `--compat-version`:

```sh
uv run --frozen python tools/check_latest_croc.py --force --transfer \
  --compat-version 10.7.0
```

Il comando esegue prima i normali controlli ultima-versione verso
ultima-versione, poi prova il mittente precedente con il ricevente più recente
e il mittente più recente con il ricevente precedente. Termina con uno stato
diverso da zero se una coppia fallisce. Per `croc 11.x` contro `10.x` quel
fallimento è il risultato atteso dell'interruzione intenzionale del protocollo
PAKE descritta in [Compatibilità del
trasporto](README.it.md#compatibilità-del-trasporto), non indica una regressione di
MoonTransfer.

Se il controllo passa per una nuova release, aggiorna `[tool.moontransfer.croc]`
in `pyproject.toml` con la nuova versione e gli hash ufficiali, poi esegui la
suite di test normale prima del commit.

## File generati

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

## Controlli della documentazione

Mantieni allineate le coppie inglese/italiano anche in `docs/`, `CONTRIBUTING` e
nelle guide Android. I README rimangono il punto d'ingresso; evita di duplicare
procedure complete tra guide. Aggiorna le etichette dai widget reali e non fissare
nel testo il numero dei test. Le guide di sviluppo usano percorsi dalla radice
del checkout, non dalla cartella del documento.

`tests/test_documentation.py` controlla i collegamenti locali e le ancore nei
formati usati dal progetto, le traduzioni e la documentazione inclusa negli
archivi. Non verifica la disponibilità dei siti esterni né la verità delle
istruzioni: queste richiedono revisione. Aggiungendo una guida, aggiorna anche
`RELEASE_DOCUMENT_NAMES` in `tools/package_release.py` e i collegamenti di
navigazione. Non includere directory di lavoro, chiavi o file generati.

```sh
uv run --frozen python -m unittest tests.test_documentation tests.test_package_release -v
```

Per i test GUI Android opt-in usa il comando nella [guida Android](android/README.it.md#test-gui-locali).
