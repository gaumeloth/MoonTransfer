# Problemi comuni

[English](TROUBLESHOOTING.md) | [MoonTransfer](../README.it.md)

## Indice

- [Warning Qt sulle icone SVG in Linux](#warning-qt-sulle-icone-svg-in-linux)
- [Verificare i download](#verificare-i-download)
- [Installazione e aggiornamenti Android](#installazione-e-aggiornamenti-android)
- [Trasporto non disponibile o trasferimento interrotto](#trasporto-non-disponibile-o-trasferimento-interrotto)
- [Contenuti ricevuti e spazio disponibile](#contenuti-ricevuti-e-spazio-disponibile)
- [Segnalazioni sicure](#segnalazioni-sicure)

## Warning Qt sulle icone SVG in Linux

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

## Verificare i download

Scarica pacchetti e `SHA256SUMS` dalla stessa release ufficiale o run Actions.
Dalla cartella dei download calcola lo SHA-256 di ogni pacchetto da usare e
confrontalo con il nome esatto del file in `SHA256SUMS`.
Sostituisci `PACCHETTO` con il nome effettivo.

```sh
# Linux
sha256sum "PACCHETTO"
# macOS
shasum -a 256 "PACCHETTO"
```

```powershell
# Windows
Get-FileHash -Algorithm SHA256 -LiteralPath "PACCHETTO"
```

Se tutti i file elencati sono presenti, verifica l'intero insieme con
`sha256sum -c SHA256SUMS` su Linux o `shasum -a 256 -c SHA256SUMS` su macOS.
Un file non scaricato non va confuso con un download corrotto.
Il checksum rileva byte modificati; non garantisce fiducia se file e checksum
provengono entrambi da una sorgente non affidabile.

Con Android SDK Build Tools nel PATH, verifica l'APK firmato e stampa il
certificato pubblico con `apksigner verify --verbose --print-certs "PACCHETTO.apk"`.
Confronta lo SHA-256 del certificato con la fingerprint di firma attendibile del
progetto, non con il checksum del file APK: identificano cose diverse.
Vedi il [riferimento ufficiale di apksigner](https://developer.android.com/tools/apksigner)
e la [guida alla firma](../android/SIGNING.it.md).

## Installazione e aggiornamenti Android

- Usa l'APK ARM64 su un dispositivo compatibile (minimo dichiarato Android 7.0/API 24).
  Gli emulatori x86_64 con traduzione ARM non sono target nativi validati.
- Non installare l'APK unsigned intermedio. Un APK debug e uno con la chiave del
  progetto normalmente non possono aggiornarsi reciprocamente; anche le chiavi
  debug locali e CI possono differire.
- Prima di disinstallare per cambiare firma, salva i contenuti necessari fuori
  dallo storage privato: la disinstallazione elimina i dati privati. Non cancellare
  i dati dell'app come primo tentativo abituale di diagnosi.
- Un aggiornamento richiede lo stesso application ID, una firma compatibile e un
  versionCode appropriato. La sola versione testuale non determina l'aggiornabilità.

## Trasporto non disponibile o trasferimento interrotto

Apri le informazioni sui due dispositivi e confronta build, protocollo e croc.
Leggi la [compatibilità del trasporto](../README.it.md#compatibilità-del-trasporto)
prima di attribuire un errore alla rete.
Se croc termina durante `--version`, fallisce prima di qualsiasi trasferimento:
registra exit code e architettura. Un crash sotto traduzione ARM non dimostra
che lo stesso APK sia difettoso su un dispositivo fisico ARM64.

Se la verifica della versione riesce, annota la fase fallita e prova un piccolo
file non sensibile con entrambe le app in primo piano. Controlla cambi di rete,
VPN/firewall e permessi delle notifiche Android. Non disabilitare le protezioni
del dispositivo o SELinux per aggirare un crash. Le sessioni di rete interrotte
non vengono riprese: avvia un nuovo trasferimento e comunica il nuovo codice.

## Contenuti ricevuti e spazio disponibile

Su Android completamento del trasferimento e pubblicazione finale sono fasi
separate. Dopo la verifica salva con il selettore di sistema; se lo chiudi,
usa **Scegli destinazione** mentre il risultato verificato rimane disponibile.
Controlla il provider e la cartella effettivamente scelti, non solo Download.
I provider cloud possono richiedere connessione e permessi propri.

**Apri** e **Condividi** dipendono dall'accesso agli URI e dalle app compatibili
installate; l'apertura di cartelle non è uniforme tra provider. Un errore di
apertura non implica da solo un salvataggio fallito: controlla la destinazione.
Prevedi spazio per staging privato e copia finale: lo spazio richiesto può
superare la dimensione del payload. Vedi [Risultati e recupero Android](../android/README.it.md#risultati-e-recupero).

## Segnalazioni sicure

Includi diagnostica dei due dispositivi, fase fallita, passaggi ed errori ripuliti.
Escludi codici di trasferimento, percorsi privati, keystore e password.
La verifica dei file controlla l'integrità rispetto al manifest, non la sicurezza
del contenuto da aprire. Accetta solo trasferimenti attesi e comunica i codici
privatamente. Vedi [come segnalare problemi](../CONTRIBUTING.it.md#segnalazioni-bug-e-log-tecnici).
