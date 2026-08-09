# Esperimento Android di MoonTransfer

Versione inglese: [README.md](README.md)

Questa directory contiene un ambiente Kivy e Buildozer isolato per il prototipo
di fattibilità Android. Non sostituisce l'applicazione desktop PySide6 e non fa
parte degli artefatti delle release desktop.

## Ambito attuale

Il prototipo attualmente fornisce:

- un ambiente di sviluppo Python 3.13 e Kivy 2.3.1;
- un'interfaccia Kivy con viste separate per inviare e ricevere uno o più file
  regolari;
- sorgenti di build Android generati contenenti solamente moduli MoonTransfer
  esplicitamente approvati e indipendenti da Qt;
- una configurazione Buildozer e python-for-android con versioni fissate;
- un target APK di debug `arm64-v8a`;
- un workflow GitHub Actions dedicato che testa, valida e rende disponibile un
  APK ARM64 di debug utilizzabile per i test di ogni revisione rilevante;
- una recipe privata che verifica e compila per Android il sorgente `croc`
  fissato;
- un probe runtime Android che individua l'eseguibile incluso e ne controlla la
  versione senza esporre un segreto di trasferimento;
- identità della build incorporata e mostrata nell'intestazione e in un dialogo
  informativo copiabile, con commit sorgente, `croc` incluso, protocollo,
  runtime Python e piattaforma ma senza codici di trasferimento o percorsi
  locali;
- selezione di uno o più file sorgente e salvataggio verificato della
  destinazione tramite lo Storage Access Framework (SAF) di Android;
- invio da Android a desktop e ricezione da desktop ad Android compatibili con
  il protocollo v2 di MoonTransfer;
- visualizzazione di nomi principali, numero di file, dimensione totale e
  informazioni SHA-256 prima del download;
- accettazione e rifiuto tramite la connessione principale `croc` con prompt;
- un foreground service `dataSync` che possiede il processo `croc` attivo e
  mantiene il trasferimento mentre l'utente passa a un'altra applicazione;
- una notifica foreground privata e legata allo stato, con fase, nome del file,
  byte trasferiti, velocità attuale e tempo stimato rimanente quando disponibili,
  un'azione **Interrompi** legata alla sessione e una notifica dismissibile di
  completamento, rifiuto o errore;
- avanzamento, annullamento, timeout di inattività e decisione, verifica
  dell'integrità e pulizia dei file temporanei privati.

Rimane un client sperimentale per file regolari. Può trasferire un singolo file
o un gruppo di file scelti nella stessa operazione del selettore, ma non può
trasferire cartelle o riprendere un trasferimento interrotto. Le build
automatizzate producono attualmente solamente un APK ARM64 di debug; release
Android firmate e altre architetture non sono implementate. L'app dichiara
`INTERNET`, i permessi per foreground service richiesti da `dataSync` e il
permesso di notifica usato per mostrare lo stato del trasferimento. La versione
pubblica visibile sulla schermata bloccata è volutamente generica: codici di
trasferimento, hash, percorsi, content URI ed errori tecnici non vengono mai
mostrati lì. SAF fornisce accesso solo ai documenti o alle directory di
destinazione scelti esplicitamente dall'utente; non viene richiesto alcun
permesso di archiviazione esteso.

## Compatibilità del trasporto

> [!IMPORTANT]
> La recipe Android attuale compila `croc 11.0.1`. Un APK prodotto da questo
> sorgente non può trasferire dati da o verso build desktop o vecchi APK
> sperimentali basati su `croc 10.x`. Crea o aggiorna assieme entrambi gli
> endpoint e, per i test, usa la stessa revisione della repository sui due
> dispositivi.

Le versioni rilevanti sono:

| Build di MoonTransfer | `croc` incluso | Compatibile con l'APK Android attuale |
| --- | --- | --- |
| Desktop `v0.1.0-alpha.1` | `10.4.13` | No |
| Desktop `v0.1.0-alpha.2` e APK precedenti del prototipo | `10.7.0` | No |
| Desktop `v0.1.0-alpha.3`, sorgente e recipe Android attuali | `11.0.1` | Sì |

Per i test di compatibilità ricrea l'APK dalla revisione desiderata e controlla
che il probe verde del trasporto riporti `croc 11.0.1`. Non usare un vecchio APK
di debug con una build desktop attuale, né un APK attuale con le alpha desktop
precedenti a `croc 11`. Questo confine non dipende dal sistema operativo o
dall'architettura della CPU.

`croc 11` ha introdotto la versione 2 del proprio protocollo PAKE sul canale e
rifiuta intenzionalmente l'handshake precedente. Lega la creazione della chiave
ai peer, ai ruoli, alla sessione, alla room e al transcript, rafforza la
derivazione delle chiavi e la gestione del salt e aggiunge la conferma reciproca
della chiave. Non esiste un fallback di compatibilità, perché usarlo
eliminerebbe queste proprietà di sicurezza. Consulta le [note ufficiali della
release `croc
11.0.0`](https://github.com/schollz/croc/releases/tag/v11.0.0) e
l'[aggiornamento di sicurezza
upstream](https://github.com/schollz/croc/pull/1212).

Una coppia mista `croc 10`/`croc 11` fallisce durante la messa in sicurezza del
canale, prima del trasferimento del manifest dei metadati o del payload
principale di MoonTransfer. I dettagli tecnici possono indicare una versione
del protocollo PAKE non supportata oppure l'errore generico `could not secure
channel`. Questo è il fallimento di compatibilità atteso; non indica un problema
dello storage Android o del foreground service.

## Prerequisiti del sistema host

Le build Android richiedono Linux o macOS. La configurazione attuale prevede
Java 17, Go 1.25 o successivo, i normali strumenti di compilazione nativa e
Rust. Buildozer scarica Android SDK e NDK configurati quando necessario.

Su Ubuntu, installa i prerequisiti di sistema prima di compilare:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool \
  pkg-config cmake libffi-dev libssl-dev automake autopoint gettext \
  build-essential libltdl-dev libncurses5-dev libncursesw5-dev \
  libtinfo6 zlib1g-dev
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
./scripts/android.sh package
```

`doctor` controlla i prerequisiti del sistema host, incluse le versioni di Java
e Go. `prepare` ricrea l'albero dei sorgenti generati sotto
`build/android/source`. `run` avvia lo scaffold Kivy sul desktop per un rapido
smoke test della GUI. `build` produce un APK di debug sotto `dist/android`.
Dopo una build riuscita, `package` ne valida struttura, architettura nativa,
file applicativi richiesti e identità incorporata, quindi prepara una copia
versionata sotto `release/`. Il wrapper esegue sempre l'ambiente Android bloccato
con `uv run --frozen`, quindi questi comandi non aggiornano mai implicitamente
`android/uv.lock`.

La preparazione incorpora anche `build-info.json`. Se il checkout è pulito e la
revisione coincide con un tag di pre-release esatto, viene mostrata la versione
del tag; altrimenti l'APK mostra una versione di sviluppo con il prefisso del
commit corrente. Il pulsante informativo nell'intestazione apre il riepilogo
diagnostico completo e copiabile.

Quando l'APK viene avviato su Android, individua `libcroc.so` nella directory
delle librerie native dell'applicazione ed esegue `croc --version` in un thread
di lavoro. Uno stato verde conferma che l'eseguibile del trasporto può essere
avviato sul dispositivo.

La prima esecuzione può scaricare pacchetti Python, strumenti Android e archivi
sorgente. I sorgenti generati e gli output di build non devono essere modificati
o committati.

## Artefatto di integrazione continua

`.github/workflows/android-build.yml` viene eseguito per pull request, push su
`main`, tag di pre-release e avvii manuali del workflow. Il job Ubuntu 24.04
installa versioni fissate di `uv`, Python 3.13.14, Java 17, Go 1.25.12 e Rust
1.97.1, verifica `android/uv.lock`, installa il gruppo bloccato delle dipendenze
di build, esegue tutti i test `test_android*.py`, avvia `doctor` e crea l'APK di
debug `arm64-v8a`.

Il workflow seleziona il profilo Buildozer dedicato `ci`. Questo profilo accetta
in modo non interattivo le licenze Android SDK configurate mentre Buildozer
installa SDK e NDK isolati. Le normali build locali non selezionano il profilo e
mantengono la richiesta interattiva di Buildozer per le licenze.

Il workflow memorizza nella cache Android SDK/NDK scaricati e i dati Gradle.
Intenzionalmente non include ancora nella cache la build nativa molto più grande
di python-for-android: ciò rende la prima implementazione più semplice da
invalidare e controllare, al costo di una build pulita più lenta. La decisione
potrà essere rivalutata dopo aver raccolto tempi e dati di affidabilità della
cache da esecuzioni reali.

Prima del caricamento, `package` verifica l'APK come archivio ZIP, rifiuta
percorsi duplicati o non sicuri e asset `.xcf` riservati ai sorgenti, richiede le
librerie ARM64 attese di `croc`, Python e dell'applicazione, controlla i file
dell'applicazione privata generata e confronta i metadati incorporati di
versione, commit, `croc` e protocollo con la build richiesta. `aapt` di Android
controlla quindi ID dell'applicazione, nome e codice versione, limiti SDK, stato
debug e architettura nativa dichiarata. Il file grezzo
`MoonTransfer-<version>-android-arm64-debug.apk` risultante è scaricabile dal
riepilogo dell'esecuzione del workflow per 14 giorni senza un ulteriore
contenitore di archivio.

Questo file è solamente un artefatto di test. Non viene allegato alle GitHub
Release e non è firmato con una chiave di release controllata dal progetto.
L'identità di firma debug di Buildozer può essere diversa tra build locali e
runner GitHub, quindi Android può rifiutare un aggiornamento diretto tra esse.
Disinstallare prima il prototipo esistente risolve la mancata corrispondenza
della firma, ma elimina anche i dati privati dell'app.

La versione completa della build e il commit sono incorporati in
`build-info.json`, mentre la versione completa viene usata come `versionName` di
Android. Durante la fase di prototipo il `versionCode` di Buildozer resta fissato
a `1`. Prima di pubblicare artefatti Android di release, un flusso di
distribuzione firmato dovrà sostituire questo valore provvisorio con una politica
di codici versione monotonicamente crescenti.

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
3. In **Invia**, premi **Seleziona file** e scegli uno o più documenti piccoli e
   non sensibili nel selettore di sistema Android. Non selezionare una cartella.
4. Controlla il nome del file oppure il numero di file e la dimensione totale,
   quindi premi **Prepara e invia**.
5. L'app calcola l'hash di ogni copia privata e mostra un codice di 32 caratteri.
   Il codice viene anche copiato negli appunti Android.
6. Passa all'applicazione di messaggistica usata per comunicare il codice. Lascia
   MoonTransfer in background mentre il destinatario lo inserisce; la notifica
   del trasferimento in corso deve restare visibile e indicare la fase corrente.
7. Inserisci quel codice nella scheda **Ricevi** del desktop e avvia la
   ricezione.
8. Controlla nomi, conteggi, dimensione totale e informazioni SHA-256 mostrate
   dall'app desktop, quindi accetta o rifiuta il trasferimento.
9. Se accetti, entrambe le applicazioni dovrebbero mostrare avanzamento e
   completamento. Controlla che ogni file verificato appaia nella destinazione
   desktop scelta. Un payload multi-file viene inserito nel contenitore desktop
   `MoonTransfer`. Se rifiuti, Android dovrebbe comunicare la decisione senza
   inviare il payload principale.
10. Torna in MoonTransfer e verifica che sia possibile effettuare una nuova
    selezione e avviare un altro trasferimento senza chiudere o riavviare
    l'applicazione.

### Ricevere da desktop su Android

1. Avvia MoonTransfer sul desktop, apri **Invia** e scegli uno o più file piccoli
   e non sensibili. Non includere cartelle in questo test di compatibilità
   Android.
2. Avvia l'app Android, apri **Ricevi**, inserisci il codice mostrato
   dall'applicazione desktop e premi **Ricevi informazioni**.
3. Per un solo file controlla nome, dimensione e SHA-256. Per più file controlla
   numero, dimensione totale, nomi principali elencati e l'indicazione che ogni
   file include un SHA-256.
4. Premi **Rifiuta** per avvisare il mittente desktop senza scaricare il payload,
   oppure **Accetta** per continuare.
5. Dopo aver scaricato il payload accettato nell'area privata e verificato il
   manifest, Android apre il selettore di sistema per il salvataggio.
6. Per un file scegli nome e posizione finali. Per più file scegli una directory
   di destinazione: MoonTransfer crea al suo interno una directory dedicata
   `MoonTransfer` e vi scrive i file verificati. MoonTransfer non apre né crea
   la destinazione prima che la verifica sia riuscita.
7. Controlla che entrambe le applicazioni segnalino il completamento e che ogni
   file salvato sia disponibile tramite il provider di documenti Android scelto.
8. Verifica che il campo del codice e i controlli di trasferimento siano di nuovo
   utilizzabili senza chiudere o riavviare MoonTransfer.

### Controlli del ciclo di vita e del recupero

Prima di considerare validata manualmente una modifica Android, verifica anche
questi casi con un payload piccolo e non sensibile:

1. Avvia un invio, attendi il codice, premi Home o passa all'app di
   messaggistica, quindi riapri MoonTransfer. La notifica deve rimanere
   disponibile e la GUI deve ricollegarsi alla stessa fase senza avviare un
   altro trasferimento.
2. Mentre un trasferimento è attivo, rimuovi MoonTransfer dalla schermata delle
   applicazioni recenti e riaprilo. I controlli che potrebbero avviare una
   seconda operazione devono restare disabilitati finché il servizio esistente
   non termina o viene annullato.
3. Ruota il dispositivo durante lo scambio dei metadati, il trasferimento del
   payload e la decisione del destinatario. La ricreazione dell'Activity non
   deve duplicare `croc`, perdere la proposta o sbloccare controlli in conflitto.
4. Annulla il selettore della sorgente prima di scegliere un file. Separatamente,
   annulla il selettore di salvataggio dopo una ricezione verificata, quindi
   riaprilo con **Scegli dove salvare**. Entrambi i percorsi devono restituire
   controlli utilizzabili.
5. Annulla un trasferimento attivo con **Interrompi** nell'app e un altro con
   l'azione della notifica. Entrambe devono arrestare la stessa sessione corrente
   senza lasciare la GUI bloccata permanentemente.
6. Dopo completamento, rifiuto e annullamento, avvia un altro trasferimento in
   entrambe le direzioni senza riavviare l'applicazione.
7. Come test distruttivo del recupero, usa **Forza interruzione** di Android
   durante un trasferimento e riapri l'app. Trascorso il periodo di tolleranza
   limitato, MoonTransfer deve segnalare la sessione abbandonata, eliminarla e
   sbloccare i controlli invece di restarvi collegato indefinitamente.
8. Su Android 13 o successivo, ripeti un piccolo trasferimento dopo aver negato
   il permesso per le notifiche. Il trasferimento deve avviarsi secondo le regole
   di piattaforma per i foreground service oppure fallire con una spiegazione
   visibile; non deve lasciare silenziosamente una sessione attiva o bloccata.

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
automaticamente. Alla riapertura la GUI si ricollega prima alla richiesta del
servizio persistita e tollera brevemente uno snapshot di stato temporaneamente
non disponibile. Finché è collegato un client del servizio, i controlli non
possono avviare un'operazione in conflitto nemmeno prima dell'arrivo del primo
snapshot valido. Se lo snapshot resta illeggibile o l'heartbeat del servizio
rimane invariato per circa 15 secondi, MoonTransfer segnala l'errore, arresta
l'eventuale istanza residua, elimina la sessione privata abbandonata e sblocca i
controlli invece di attendere indefinitamente.

La notifica persistente usa una barra indeterminata mentre MoonTransfer prepara
i metadati, si connette o verifica, nessuna barra durante l'attesa di una
decisione e una barra determinata durante il trasferimento del payload e il
salvataggio SAF finale. Quando `croc` fornisce dati sufficienti, lo stato
compatto mostra anche byte trasferiti e totali, velocità attuale e tempo stimato
rimanente. Toccando la notifica si apre MoonTransfer; **Interrompi** richiede
l'annullamento senza riaprire l'Activity. L'azione è disponibile solamente nella
notifica privata della sessione attiva. La versione generica per la schermata
bloccata e le notifiche di risultato terminali non la espongono. La notifica
foreground viene rimossa insieme al servizio; completamento, rifiuto ed errore
lasciano una notifica di risultato separata e dismissibile. L'annullamento
richiesto dall'utente non lascia una notifica di risultato.

## Progettazione del trasferimento Android

Il selettore di sistema restituisce uno o più content URI invece di normali
percorsi del filesystem. MoonTransfer legge per ciascuno il nome portabile e la
dimensione opzionale, rifiuta collisioni tra nomi portabili, apre ogni URI
tramite `ContentResolver` e copia ogni documento in una directory privata
separata dell'app con modalità `0600`. Le copie private sono le sorgenti
controllate usate per gli hash e da `croc`; i loro fingerprint vengono verificati
nuovamente prima di avviare il mittente principale. Vengono eliminate dopo
completamento, rifiuto, errore o annullamento. Le directory di staging e sessione
residue, ma appartenenti all'app, vengono eliminate all'avvio successivo solo
quando non è attivo alcun trasferimento foreground.

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
staging attiva. Il recupero individua la richiesta valida più recente prima di
leggerne lo snapshot, quindi un file di stato temporaneamente mancante o
illeggibile non viene subito scambiato per l'assenza di un trasferimento. Ogni
snapshot viene accettato solo se sessione, operazione e indicatore terminale sono
coerenti con la richiesta e con la macchina a stati Android. Il client del
servizio collegato mantiene a sua volta disabilitati i controlli in conflitto.
Periodi di tolleranza separati di 15 secondi per uno snapshot illeggibile e per
un heartbeat invariato assorbono brevi ritardi dello scheduler o del filesystem,
pur mantenendo limitato il recupero da un processo del servizio terminato.

La classe del servizio mantenuta nel repository rifiuta un riavvio sticky di
Android privo di un identificatore di sessione valido. Su Android 15 e versioni
successive gestisce inoltre il timeout di piattaforma per `dataSync` richiedendo
l'annullamento, uscendo dalla modalità foreground e arrestando il servizio entro
il breve periodo concesso. Android limita questo tipo di servizio a sei ore
complessive in background ogni 24 ore, condivise tra i servizi `dataSync`
dell'applicazione; riportare l'app in primo piano azzera il tempo conteggiato. Se
Android rifiuta un nuovo avvio del foreground service, MoonTransfer indica di
mantenere visibile l'app e riprovare. Consulta la [documentazione ufficiale sui
timeout dei foreground
service](https://developer.android.com/develop/background-work/services/fgs/timeout).

Il servizio deriva il contenuto della notifica dallo stesso stato in memoria che
scrive nello snapshot privato della sessione. Gli aggiornamenti della notifica
guidati dall'avanzamento sono limitati a circa uno al secondo per evitare lavoro
di sistema inutile; i cambi di stato e i risultati terminali vengono comunicati
subito. La notifica dettagliata è marcata come privata e dispone di una versione
pubblica generica per la schermata bloccata. Nessuna delle due notifiche include
segreti di trasferimento, valori SHA-256, percorsi del filesystem, content URI,
indirizzi relay o errori grezzi dei processi. L'azione **Interrompi** usa un
`PendingIntent` esplicito e immutabile che contiene solamente l'identificatore
casuale della sessione. Il servizio lo accetta solo se corrisponde alla sessione
attiva, quindi scrive lo stesso comando di annullamento privato dell'app e con
permessi restrittivi usato dalla GUI.

Il mittente riutilizza quindi il protocollo desktop invece di inviare un payload
`croc` grezzo:

1. analizza il file o i file in staging e calcola uno SHA-256 per ciascuno;
2. crea una proposta del protocollo v2 contenente un codice separato per il
   payload principale;
3. avvia il processo `croc send` principale e attende che `croc` abbia raccolto
   e calcolato gli hash di tutti gli elementi da inviare e comunichi il codice;
4. avvia un mittente separato per i metadati e mostra l'unico codice destinato
   all'utente soltanto quando anche questo processo è preparato;
5. trasferisce il manifest JSON con limiti espliciti mentre il mittente
   principale rimane pronto;
6. lascia che il ricevitore desktop con prompt comunichi accettazione o rifiuto
   tramite la connessione `croc` principale.

Il ricevitore Android segue il flusso inverso:

1. riceve il manifest con limiti espliciti in una directory privata e isolata;
2. valida ogni campo del protocollo e rifiuta i payload che contengono directory;
3. prima del download mostra nome, dimensione e SHA-256 del singolo file oppure
   nomi principali, numero di file, dimensione totale e disponibilità degli hash
   per ciascun file;
4. avvia il ricevitore principale con prompt e scrive `y` oppure `n` a `croc`,
   così il mittente desktop riceve un'accettazione o un rifiuto a livello di
   protocollo;
5. per i trasferimenti accettati, controlla lo spazio privato disponibile e fa
   rispettare il limite di byte dichiarato durante la ricezione;
6. verifica albero ricevuto, dimensione e SHA-256 rispetto al manifest;
7. soltanto dopo la verifica avvia il selettore Android
   `ACTION_CREATE_DOCUMENT` per un file oppure `ACTION_OPEN_DOCUMENT_TREE` per
   più file; nel secondo caso crea una directory figlia dedicata `MoonTransfer`
   e vi copia ogni file verificato;
8. elimina manifest e payload privato dopo completamento, rifiuto, annullamento
   o errore.

Annullare il selettore di salvataggio non elimina la copia privata verificata:
l'utente può riaprirlo mentre il servizio resta attivo oppure annullare il
trasferimento per eliminarla. Questo ordine evita di modificare una destinazione
esistente prima del superamento dei controlli di integrità. Per un file il
provider di documenti di sistema rimane responsabile dei conflitti sul nome
finale e della conferma di sovrascrittura. Per un salvataggio multi-file,
MoonTransfer chiede al provider di creare contenitore e file e tenta di
rimuovere il nuovo contenitore se il salvataggio viene annullato o fallisce.

Entrambi i segreti vengono passati in `CROC_SECRET`, mai come argomenti della
riga di comando. Ogni processo attivo contemporaneamente riceve una directory
di configurazione `croc` distinta e isolata. L'output dei processi viene
consumato in parallelo da stdout e stderr, limitato per record e oscurato prima
di raggiungere le callback. Il completamento viene determinato dallo stato di
uscita; l'output testuale viene analizzato per il confine di preparazione
dell'invio, l'avanzamento e lo stato relativo al rifiuto. Non viene usato un
ritardo fisso per indovinare quando il mittente principale è pronto. Un timeout
di inattività di 15 minuti viene azzerato ogni volta che `croc` produce output,
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

La gerarchia dei widget della schermata principale Android e lo stile statico si trovano in
`app/moontransfer_android/moontransfer.kv`. `application.py` carica questo file,
valida ogni identificatore di widget richiesto e collega gli eventi in Python.
Il file KV rimane dichiarativo: stato del trasferimento, recupero del ciclo di
vita, comandi del servizio e azioni dell'utente restano in Python invece di
essere incorporati in espressioni di presentazione.

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
dichiarata dal progetto desktop. Scarica l'asset sorgente esplicito allegato a
quella release upstream, ne verifica il digest SHA-256 pubblicato e compila
usando i moduli Go vendorizzati inclusi invece di risolvere le dipendenze durante
la build. Crea quindi un eseguibile Android ARM64 position-independent con cgo
abilitato. In questo modo Go delega la risoluzione dei nomi dei relay al resolver
DNS nativo di Android, rispettando la rete, la VPN e il Private DNS attivi.
L'eseguibile viene incluso come `lib/arm64-v8a/libcroc.so`, mantenendolo
nell'area delle librerie native firmata dell'APK. Nel pacchetto dell'applicazione
viene inclusa anche la licenza MIT upstream. Il comando di build Android calcola
l'impronta di questa recipe; quando ne cambiano versione, checksum o logica di
compilazione, rimuove la cache nativa obsoleta di `croc` e ricrea la distribuzione
invece di riutilizzare silenziosamente un vecchio eseguibile.

## Limitazioni note

- su Android sono implementati invio e ricezione di file singoli o multipli,
  fino al limite di protocollo di 256 radici principali;
- payload con cartelle o misti file/cartelle non sono implementati su Android e
  vengono rifiutati prima di scaricare il payload principale;
- i file selezionati insieme devono avere nomi portabili distinti, perché
  vengono trasferiti come radici principali separate;
- la copia SAF finale non può essere atomica con ogni provider di documenti di
  terze parti; MoonTransfer tenta di eliminare un contenitore multi-file
  parziale, ma un errore o un'interruzione del provider può comunque lasciare
  una destinazione incompleta;
- l'esecuzione in background è protetta quando l'app viene coperta, l'utente
  passa a un'altra applicazione o il task viene rimosso dalla schermata delle
  app recenti, ma la terminazione forzata, il riavvio del dispositivo o un
  errore del servizio/processo terminano comunque il trasferimento;
- Android 15 e versioni successive impongono un limite condiviso di sei ore per
  i foreground service `dataSync` mentre l'app è in background; raggiungerlo
  annulla il trasferimento attivo e un nuovo avvio può essere rifiutato finché
  il tempo disponibile non viene ripristinato;
- i trasferimenti interrotti non possono ancora riprendere da un payload
  parziale;
- CI e packaging locale producono solamente un APK di debug `arm64-v8a`; non
  esistono una chiave di release del progetto, pubblicazione Android firmata o
  artefatti per architetture diverse da ARM64;
- le identità di firma debug possono variare tra gli host di build e rendere
  necessario disinstallare un prototipo esistente prima di installare un'altra
  build di test;
- la prontezza dell'invio e lo stato del trasferimento dipendono ancora in parte
  dall'output leggibile di `croc`, che non espone un'API strutturata per stato o
  avanzamento; MoonTransfer fissa quindi la versione di `croc` supportata e
  verifica tramite test il messaggio di preparazione atteso.
