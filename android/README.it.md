# Esperimento Android di MoonTransfer

Versione inglese: [README.md](README.md)

Questa directory contiene un ambiente Kivy e Buildozer isolato per il prototipo
di fattibilità Android. Non sostituisce l'applicazione desktop PySide6 e non fa
parte degli artefatti delle release desktop.

## Ambito attuale

Il prototipo attualmente fornisce:

- un ambiente di sviluppo Python 3.13 e Kivy 2.3.1;
- un'interfaccia Kivy con viste separate per inviare e ricevere un file;
- sorgenti di build Android generati contenenti solamente moduli MoonTransfer
  esplicitamente approvati e indipendenti da Qt;
- una configurazione Buildozer e python-for-android con versioni fissate;
- un target APK di debug `arm64-v8a`;
- una recipe privata che verifica e compila per Android il sorgente `croc`
  fissato;
- un probe runtime Android che individua l'eseguibile incluso e ne controlla la
  versione senza esporre un segreto di trasferimento;
- selezione della sorgente e salvataggio verificato della destinazione tramite
  lo Storage Access Framework (SAF) di Android;
- invio da Android a desktop e ricezione da desktop ad Android compatibili con
  il protocollo v2 di MoonTransfer;
- visualizzazione di nome, dimensione e SHA-256 prima del download;
- accettazione e rifiuto tramite la connessione principale `croc` con prompt;
- un foreground service `dataSync` che possiede il processo `croc` attivo e
  mantiene il trasferimento mentre l'utente passa a un'altra applicazione;
- una notifica foreground privata e legata allo stato, con fase, nome del file,
  byte trasferiti, velocità attuale e tempo stimato rimanente quando disponibili,
  seguita da una notifica dismissibile di completamento, rifiuto o errore;
- avanzamento, annullamento, timeout di inattività e decisione, verifica
  dell'integrità e pulizia dei file temporanei privati.

Rimane un client sperimentale limitato a un singolo file. Non può selezionare o
ricevere più file o cartelle, riprendere un trasferimento interrotto o produrre
artefatti release per architetture diverse da `arm64-v8a`. Dichiara `INTERNET`,
i permessi per foreground service richiesti da `dataSync` e il permesso di
notifica usato per mostrare lo stato del trasferimento. La versione pubblica
visibile sulla schermata bloccata è volutamente generica: codici di trasferimento,
hash, percorsi, content URI ed errori tecnici non vengono mai mostrati lì. SAF
fornisce accesso solo ai documenti scelti esplicitamente dall'utente; non viene
richiesto alcun permesso di archiviazione esteso.

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

## Testare i trasferimenti con l'applicazione desktop

Questi sono test manuali di compatibilità del prototipo Android, non una
procedura di release per l'utente finale.

1. Compila l'applicazione desktop corrente e l'APK Android di debug dalla stessa
   revisione.
2. Installa l'APK generato
   `dist/android/moontransfer-<version>-arm64-v8a-debug.apk` su un dispositivo
   Android ARM64.

### Inviare da Android a desktop

1. Avvia MoonTransfer sul desktop, apri **Ricevi** e scegli una cartella di
   destinazione.
2. Avvia l'app Android e attendi lo stato verde del trasporto `croc`.
3. In **Invia**, premi **Seleziona file** e scegli un documento piccolo e non
   sensibile dal selettore di sistema Android.
4. Controlla nome e dimensione visualizzati, quindi premi **Prepara e invia**.
5. L'app calcola l'hash della copia privata e mostra un codice di 32 caratteri.
   Il codice viene anche copiato negli appunti Android.
6. Passa all'applicazione di messaggistica usata per comunicare il codice. Lascia
   MoonTransfer in background mentre il destinatario lo inserisce; la notifica
   del trasferimento in corso deve restare visibile e indicare la fase corrente.
7. Inserisci quel codice nella scheda **Ricevi** del desktop e avvia la
   ricezione.
8. Controlla nome, dimensione e informazioni SHA-256 mostrate dall'app desktop,
   quindi accetta o rifiuta il trasferimento.
9. Se accetti, entrambe le applicazioni dovrebbero mostrare avanzamento e
   completamento. Controlla che il file verificato appaia nella destinazione
   desktop scelta. Se rifiuti, Android dovrebbe comunicare la decisione senza
   inviare il payload principale.
10. Torna in MoonTransfer e verifica che sia possibile selezionare un nuovo file
    e avviare un altro trasferimento senza chiudere o riavviare l'applicazione.

### Ricevere da desktop su Android

1. Avvia MoonTransfer sul desktop, apri **Invia** e scegli un singolo file
   piccolo e non sensibile.
2. Avvia l'app Android, apri **Ricevi**, inserisci il codice mostrato
   dall'applicazione desktop e premi **Ricevi informazioni**.
3. Controlla nome, dimensione e SHA-256 mostrati su Android.
4. Premi **Rifiuta** per avvisare il mittente desktop senza scaricare il payload,
   oppure **Accetta** per continuare.
5. Dopo aver scaricato il file accettato nell'area privata e verificato il
   manifest, Android apre il selettore di sistema per il salvataggio.
6. Scegli nome e posizione finali. Il selettore di sistema gestisce la conferma
   per un file già esistente; MoonTransfer non apre la destinazione prima che la
   verifica sia riuscita.
7. Controlla che entrambe le applicazioni segnalino il completamento e che il
   file sia disponibile tramite il provider di documenti Android scelto.
8. Verifica che il campo del codice e i controlli di trasferimento siano di nuovo
   utilizzabili senza chiudere o riavviare MoonTransfer.

Se il selettore di salvataggio viene annullato, la copia privata verificata
rimane disponibile finché il foreground service del trasferimento resta attivo.
Premi **Scegli dove salvare** per riprovare oppure **Interrompi** per eliminarla.

Premere Home o passare a un'altra applicazione non annulla un'operazione attiva:
il foreground service la continua e la GUI si ricollega alla sessione persistita
quando viene riaperta. **Interrompi** invia un comando di annullamento al
servizio. Il servizio è sticky e rimuovere MoonTransfer dalla schermata delle
applicazioni recenti non lo arresta intenzionalmente. Usare **Forza
interruzione** dalle impostazioni Android, riavviare il dispositivo o una reale
terminazione del processo del servizio da parte del sistema operativo possono
ancora interrompere l'operazione; i trasferimenti interrotti non riprendono
automaticamente. Se la GUI trova uno stato attivo persistito ma non riceve più
l'heartbeat del servizio, arresta l'eventuale istanza residua, elimina la
sessione privata abbandonata e sblocca i controlli invece di ripristinare un
trasferimento che non esiste più.

La notifica persistente usa una barra indeterminata mentre MoonTransfer prepara
i metadati, si connette o verifica, nessuna barra durante l'attesa di una
decisione e una barra determinata durante il trasferimento del payload e il
salvataggio SAF finale. Quando `croc` fornisce dati sufficienti, lo stato
compatto mostra anche byte trasferiti e totali, velocità attuale e tempo stimato
rimanente. Toccando la notifica si apre MoonTransfer. La notifica foreground
viene rimossa insieme al servizio; completamento, rifiuto ed errore lasciano una
notifica di risultato separata e dismissibile. L'annullamento richiesto
dall'utente non lascia una notifica di risultato.

## Progettazione del trasferimento Android

Il selettore di sistema restituisce un content URI invece di un normale percorso
del filesystem. MoonTransfer legge il nome portabile e la dimensione opzionale,
apre l'URI tramite `ContentResolver` e lo copia in una nuova directory privata
dell'app con modalità `0600`. La copia privata è la sorgente controllata usata
per l'hash e da `croc`; il suo fingerprint viene verificato nuovamente prima di
avviare il mittente principale. Viene eliminata dopo completamento, rifiuto,
errore o annullamento. Le directory di staging e sessione residue, ma
appartenenti all'app, vengono eliminate all'avvio successivo solo quando non è
attivo alcun trasferimento foreground.

L'Activity Kivy non possiede il controller del trasferimento né il processo
figlio `croc`. Dopo aver validato l'azione dell'utente crea una sessione privata
e avvia un foreground service sticky di tipo `dataSync`; quel processo separato
possiede il controller per l'intera durata del trasferimento e non viene
arrestato soltanto perché il task dell'Activity viene rimosso. Activity e
servizio si scambiano snapshot JSON versionati e comandi monouso tramite file
privati dell'app scritti atomicamente con permessi restrittivi. Nell'intent del
servizio Android viene inserito solamente un identificatore di sessione casuale;
codici di trasferimento, percorsi dei documenti, stato e content URI di
destinazione restano nell'area privata dell'app. Ricreare l'Activity ricostruisce
quindi lo stato visibile senza riavviare `croc` o eliminare una directory di
staging attiva. Un heartbeat aggiornato periodicamente permette all'Activity di
distinguere un'operazione in background ancora viva dallo stato lasciato da un
processo del servizio terminato.

Il servizio deriva il contenuto della notifica dallo stesso stato in memoria che
scrive nello snapshot privato della sessione. Gli aggiornamenti della notifica
guidati dall'avanzamento sono limitati a circa uno al secondo per evitare lavoro
di sistema inutile; i cambi di stato e i risultati terminali vengono comunicati
subito. La notifica dettagliata è marcata come privata e dispone di una versione
pubblica generica per la schermata bloccata. Nessuna delle due notifiche include
segreti di trasferimento, valori SHA-256, percorsi del filesystem, content URI,
indirizzi relay o errori grezzi dei processi.

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

Il ricevitore Android segue il flusso inverso:

1. riceve il manifest con limiti espliciti in una directory privata e isolata;
2. valida ogni campo del protocollo e rifiuta i payload con più elementi non
   ancora supportati;
3. mostra nome portabile, dimensione dichiarata e SHA-256 del singolo file prima
   di scaricarlo;
4. avvia il ricevitore principale con prompt e scrive `y` oppure `n` a `croc`,
   così il mittente desktop riceve un'accettazione o un rifiuto a livello di
   protocollo;
5. per i trasferimenti accettati, controlla lo spazio privato disponibile e fa
   rispettare il limite di byte dichiarato durante la ricezione;
6. verifica albero ricevuto, dimensione e SHA-256 rispetto al manifest;
7. soltanto dopo la verifica avvia il selettore Android
   `ACTION_CREATE_DOCUMENT` e copia il file verificato nel content URI
   restituito;
8. elimina manifest e payload privato dopo completamento, rifiuto, annullamento
   o errore.

Annullare il selettore di salvataggio non elimina la copia privata verificata:
l'utente può riaprirlo mentre il servizio resta attivo oppure annullare il
trasferimento per eliminarla. Questo ordine evita di modificare un file
esistente prima del superamento dei controlli di integrità. Il provider di
documenti di sistema rimane responsabile dei conflitti sul nome finale e della
conferma di sovrascrittura.

Entrambi i segreti vengono passati in `CROC_SECRET`, mai come argomenti della
riga di comando. Ogni sessione riceve una directory di configurazione `croc`
isolata. L'output dei processi viene consumato in parallelo da stdout e stderr,
limitato per record e oscurato prima di raggiungere le callback. Il completamento
del processo viene determinato dallo stato di uscita; l'output testuale viene
analizzato solamente per avanzamento e stato relativo al rifiuto. Un timeout di
inattività di 15 minuti viene azzerato ogni volta che `croc` produce output,
quindi non impone una durata massima fissa a un trasferimento attivo. Un timeout
separato di 15 minuti per la decisione rifiuta automaticamente una proposta
senza risposta invece di lasciare il mittente desktop in attesa indefinita. Può
essere attiva una sola operazione di invio o ricezione alla volta.

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

- su Android sono implementati solamente invio e ricezione di un singolo file;
- cartelle e payload con più file non sono implementati e quelli in arrivo
  vengono rifiutati prima di scaricare il payload principale;
- la copia SAF finale non può essere atomica con ogni provider di documenti di
  terze parti; un'interruzione durante questa copia locale può lasciare una
  destinazione parziale;
- l'esecuzione in background è protetta quando l'app viene coperta, l'utente
  passa a un'altra applicazione o il task viene rimosso dalla schermata delle
  app recenti, ma la terminazione forzata, il riavvio del dispositivo o un
  errore del servizio/processo terminano comunque il trasferimento;
- i trasferimenti interrotti non possono ancora riprendere da un payload
  parziale;
- viene prodotto solamente un APK di debug `arm64-v8a`;
- lo stato del trasferimento dipende ancora in parte dall'output leggibile di
  `croc`, che non espone un'API strutturata per l'avanzamento.
