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

## Indice

- [Da dove iniziare](#da-dove-iniziare)
- [Stato attuale](#stato-attuale)
- [Compatibilità del trasporto](#compatibilità-del-trasporto)
- [Guida rapida](#guida-rapida)
- [Scaricare un'alpha pre-buildata](#scaricare-unalpha-pre-buildata)
- [Usare MoonTransfer](#usare-moontransfer)
- [Sviluppo e documentazione](#sviluppo-e-documentazione)
- [Licenze](#licenze)

## Da dove iniziare

| Obiettivo | Guida |
| --- | --- |
| Usare l'app desktop | [Scaricare un'alpha](#scaricare-unalpha-pre-buildata) e [uso](#usare-moontransfer) |
| Usare o provare Android | [Installazione e guida Android](android/README.it.md#installazione-e-primo-avvio) |
| Compilare o contribuire | [Build desktop](docs/BUILD.it.md), [build Android](android/README.it.md#prerequisiti-del-sistema-host), [contribuzione](CONTRIBUTING.it.md) |
| Risolvere un problema | [Problemi comuni](docs/TROUBLESHOOTING.it.md) |

### Canali di distribuzione

- **Release pubblicate:** usa gli asset della pagina Releases. La release pubblica corrente `alpha.4` contiene quattro archivi desktop e un APK ARM64 firmato; le funzionalità descritte qui si riferiscono ai sorgenti correnti e possono essere più recenti.
- **Artefatti Actions:** build di prova con versione e commit identificabili. Android normalmente produce un APK debug; gli avvii manuali dedicati possono produrre APK firmati con la chiave del progetto, senza pubblicare release.
- **Nuovi tag di pre-release:** il workflow prepara una bozza con quattro archivi desktop e un APK ARM64 firmato. La pubblicazione rimane manuale; configurare la firma è un prerequisito.

Vedi [artefatti e release](docs/RELEASING.it.md) per selezionare il workflow corretto. Desktop usa Qt/PySide6; Android usa Kivy e l'integrazione nativa del sistema.

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
- identità della build incorporata con versione completa di MoonTransfer,
  commit sorgente, versione di `croc` inclusa e versione del protocollo di
  MoonTransfer;
- artefatti `onedir` automatizzati e testabili per Linux x86_64, Windows
  x86_64, macOS Intel e macOS Apple Silicon.

L'alpha pubblica attuale, `v0.1.0-alpha.4`, viene distribuita dalla
[pagina GitHub Releases](https://github.com/gaumeloth/MoonTransfer/releases)
come archivi `onedir` pre-buildati e un APK Android ARM64 firmato. Le build
desktop non sono firmate né notarizzate e tutti gli artefatti sono destinati ai
primi test, non all'uso in produzione. Non sono ancora disponibili installer
nativi.

Su Linux e Windows l'archivio contiene una cartella portabile `MoonTransfer`: va
mantenuta interamente, non soltanto il suo eseguibile. Su macOS contiene invece
il bundle applicazione `MoonTransfer.app`, che deve essere mantenuto integro
allo stesso modo.

Sul desktop, il titolo della finestra mostra la versione completa della build. Il pulsante
informativo nell'angolo in basso a destra apre un riepilogo diagnostico
copiabile con versione, commit, `croc` incluso, protocollo, runtime Python e
piattaforma. Non contiene intenzionalmente codici di trasferimento o percorsi
locali. Includi questo riepilogo quando segnali un problema specifico di una
build.

## Compatibilità del trasporto

> [!IMPORTANT]
> Le build prodotte dal sorgente attuale includono `croc 11.0.1`. Non possono
> trasferire dati da o verso build di MoonTransfer basate su `croc 10.x`.
> Aggiorna MoonTransfer su entrambi i dispositivi prima di iniziare un
> trasferimento; usare la stessa release di MoonTransfer da entrambe le parti è
> la scelta più sicura.

Il confine di compatibilità è il seguente:

| Build di MoonTransfer | `croc` incluso | Compatibile con il sorgente attuale |
| --- | --- | --- |
| `v0.1.0-alpha.1` | `10.4.13` | No |
| `v0.1.0-alpha.2` | `10.7.0` | No |
| `v0.1.0-alpha.3`, `v0.1.0-alpha.4` e sorgente attuale | `11.0.1` | Sì |

Gli archivi `alpha.1` e `alpha.2` restano utilizzabili soltanto con altre build
precedenti a `croc 11`. Usa `alpha.4` o una build successiva su entrambi i
dispositivi. Si tratta di un'incompatibilità del protocollo di trasporto, non
del sistema operativo: le build desktop e Android attuali restano compatibili
quando usano `croc 11` e la stessa versione del protocollo MoonTransfer.

`croc 11` ha introdotto la versione 2 del proprio protocollo PAKE sul canale e
rifiuta deliberatamente peer che usano l'handshake precedente. Il nuovo
handshake lega esplicitamente lo scambio di chiavi ai due peer, ai loro ruoli,
alla sessione, alla room e al transcript; rafforza inoltre la derivazione delle
chiavi e la gestione del salt e aggiunge la conferma reciproca della chiave. Un
fallback silenzioso eliminerebbe queste protezioni, quindi MoonTransfer non lo
tenta. Consulta le [note ufficiali della release `croc
11.0.0`](https://github.com/schollz/croc/releases/tag/v11.0.0) e
l'[aggiornamento di sicurezza
upstream](https://github.com/schollz/croc/pull/1212).

Con una coppia mista vecchia/nuova la connessione fallisce durante la messa in
sicurezza del canale, prima che MoonTransfer possa scambiare il manifest dei
metadati o avviare il payload principale. Nessun payload selezionato viene
scaricato o pubblicato. A seconda del lato che segnala l'errore, i dettagli
tecnici possono indicare una versione del protocollo PAKE non supportata e
chiedere di aggiornare entrambi i client, oppure mostrare il messaggio più
generico `could not secure channel`.

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
MoonTransfer-0.1.0-alpha.4-linux-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.4-windows-x86_64.zip
MoonTransfer-0.1.0-alpha.4-macos-x86_64.tar.gz
MoonTransfer-0.1.0-alpha.4-macos-arm64.tar.gz
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
file. Prima di mostrare il codice MoonTransfer ha già preparato un unico
mittente `croc` principale per l'intero payload. Attende accettazione o rifiuto
tramite il prompt nativo di `croc`: la preparazione non invia il payload
principale prima dell'accettazione.

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
salvata in una cartella contenitore (`MoonTransfer` per impostazione predefinita,
oppure il nome portabile scelto dal mittente). Le cartelle esistenti non
vengono mai unite o sovrascritte ricorsivamente: MoonTransfer propone invece un
nome univoco come `MoonTransfer (1)`.

### Codici, risultati e recupero

Su desktop e Android puoi incollare in **Ricevi** il codice oppure l'intero
messaggio MoonTransfer. Il parser condiviso estrae un unico codice esadecimale
di 32 caratteri, anche nel formato visualizzato con spazi. Un testo ambiguo
con codici differenti non viene accettato automaticamente. Importare il codice
non avvia mai un trasferimento.

Il desktop ricorda l'ultima destinazione e mostra il percorso effettivamente
salvato dopo la verifica. Android riapre il selettore di sistema nell'ultima
destinazione, quando il provider lo consente; serve comunque la conferma del
salvataggio. Nel risultato Android trovi **Apri** per il contenuto salvato e
**Condividi** per un singolo file. Aprire una cartella richiede un gestore
documenti compatibile. **Dettagli**, nella proposta, mostra percorsi, dimensioni
e hash dei file in pagine di dimensioni limitate.

Se il salvataggio finale fallisce, puoi scegliere un'altra destinazione senza
riscaricare il contenuto verificato. Il desktop conserva la copia per massimo
15 minuti dal primo errore di salvataggio; Android concede 15 minuti dalla
verifica per scegliere o riprovare una destinazione. Stop, scadenza o
terminazione del processo responsabile interrompono questa possibilità.
Un provider Android può lasciare un risultato parziale dopo un errore:
controlla la destinazione precedente prima di riprovare.

**Prepara nuovo invio** crea un nuovo trasferimento con nuovi codici, non una
ripresa parziale. Il desktop analizza nuovamente gli originali selezionati.
Android può riutilizzare le copie preparate per massimo 15 minuti dalla
visualizzazione del risultato, fino alla chiusura dell'app; per includere
modifiche agli originali occorre selezionarli di nuovo. Annullare esplicitamente
l'invio elimina le copie preparate Android. Quelle lasciate da un processo
terminato vengono pulite al successivo avvio, non riproposte come trasferimenti
riprendibili.

Il campo facoltativo `container_name` del manifest non modifica il protocollo 2
né la compatibilità del trasporto. I destinatari precedenti lo ignorano e usano
`MoonTransfer` per più radici. Un singolo file o una singola cartella mantengono
sempre il nome originale.

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

## Sviluppo e documentazione

- [Build desktop e avvio dai sorgenti](docs/BUILD.it.md)
- [Contribuire, eseguire test e mantenere la documentazione](CONTRIBUTING.it.md)
- [Architettura e responsabilità dei moduli](docs/ARCHITECTURE.it.md)
- [Workflow, artefatti di prova e release](docs/RELEASING.it.md)
- [Problemi comuni e verifica dei download](docs/TROUBLESHOOTING.it.md)
- [Guida Android](android/README.it.md) e [firma degli APK](android/SIGNING.it.md)

## Licenze

MoonTransfer è distribuito sotto la GNU General Public License versione 3.
Vedi il testo completo della licenza in [LICENSE](LICENSE).

I componenti di terze parti mantengono le rispettive licenze. Vedi
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) per i componenti di terze
parti, in particolare `croc`, PySide6/Qt for Python, Kivy, Buildozer e
python-for-android.
