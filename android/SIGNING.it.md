# Firma delle release Android

[English](SIGNING.md)

Le build debug non cambiano. Le build release usano la **stessa chiave privata
permanente** in locale e su GitHub Actions. Prima si compila un APK non firmato;
poi un passaggio separato lo controlla, allinea e firma. La compilazione non
riceve i segreti di firma. I tag di prerelease richiedono ora anche l'APK firmato:
un unico job allega tutti e cinque i pacchetti alla stessa **bozza** GitHub Release.
Nessuna chiave definitiva viene generata automaticamente e la pubblicazione finale
resta manuale.

## Indice

- [Configurazione iniziale](#configurazione-iniziale)
- [Build firmata locale](#build-firmata-locale)
- [Build firmata in CI](#build-firmata-in-ci)
- [Desktop e Android insieme](#desktop-e-android-insieme)
- [Passaggio sul dispositivo](#passaggio-sul-dispositivo)
- [Test senza chiave definitiva](#test-senza-chiave-definitiva)
- [Verificare la configurazione GitHub](#verificare-la-configurazione-github)

## Configurazione iniziale

Con Java 17 e Python 3.11+ (va bene anche l'ambiente Android), dalla root del progetto:

```sh
python3 -m tools.android_signing init --keystore "$HOME/.config/moontransfer/signing/release.p12"
```

Esegui personalmente il comando in un terminale interattivo: la password non
viene mostrata. Crea un keystore PKCS12 (RSA 4096, validità 10000 giorni, alias
`moontransfer`) con permessi 0600, rifiuta percorsi già esistenti e mostra solo
l'impronta pubblica del certificato. La password della chiave coincide con quella
del keystore. Fai un backup sicuro del file e conserva la password separatamente
in un password manager: perdere la chiave impedisce i normali aggiornamenti degli
APK distribuiti direttamente. Non inserirli nei commit, nei log, nelle release
o in chat. Base64 è una codifica, non una cifratura.

Su GitHub crea **Settings > Environments > android-signing**. Prima di inserire
i segreti, scegli **Selected branches and tags** e autorizza il branch `main` e
le regole tag `v*-alpha.*`, `v*-beta.*`, `v*-rc.*`, mai i riferimenti di PR.
Il workflow controlla anche la sintassi stretta del tag e che il commit appartenga
a `main`. Configura un revisore obbligatorio dove
disponibile. Mantieni `main` protetto tramite PR: le modifiche al workflow di firma
sono sensibili per la sicurezza. Creare l'environment non ne configura le protezioni.

Inserisci questi **Secrets dell'environment**, non della repository:

| Nome | Valore |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Il file locale `release.p12` codificato Base64 |
| `ANDROID_STORE_PASSWORD` | Password del keystore |
| `ANDROID_KEY_PASSWORD` | Password della chiave (identica con il comando sopra) |

Inserisci queste **Variables dell'environment**:

| Nome | Valore |
| --- | --- |
| `ANDROID_KEY_ALIAS` | `moontransfer` |
| `ANDROID_CERTIFICATE_SHA256` | Impronta pubblica SHA-256 mostrata alla creazione |

Con `gh` autenticato puoi caricare i segreti senza visualizzarli:

```sh
base64 < "$HOME/.config/moontransfer/signing/release.p12" | gh secret set ANDROID_KEYSTORE_BASE64 --env android-signing --repo gaumeloth/MoonTransfer
gh secret set ANDROID_STORE_PASSWORD --env android-signing --repo gaumeloth/MoonTransfer
gh secret set ANDROID_KEY_PASSWORD --env android-signing --repo gaumeloth/MoonTransfer
```

Gli ultimi due comandi richiedono le password interattivamente. Imposta le due
variabili pubbliche nell'interfaccia GitHub.

## Build firmata locale

La base numerica della versione deve coincidere con `pyproject.toml`. Scegli e
registra un `versionCode` maggiore di **tutti quelli già distribuiti, in locale
o dalla CI**. `android/release.toml` registra questo numero (inizialmente 2; debug 1).
Incrementalo tramite PR prima di ogni nuova release: i tag usano sempre il valore
committato. Il comando controlla l'intervallo 2..2100000000, non mantiene un contatore
globale: il maintainer deve coordinarlo anche con eventuali override manuali.
Stessa release locale/CI: stesso codice; nuovo aggiornamento: nuovo codice.

```sh
version=0.1.0-dev.signed.1
version_code=$(python3 -m tools.android release-version-code)
commit=$(git rev-parse HEAD)
./scripts/android.sh build --release-unsigned --version-code "$version_code" --version "$version" --commit "$commit"
./scripts/android.sh package --release-unsigned --version "$version" --commit "$commit"
python3 -m tools.android_signing sign \
  --apk "release/MoonTransfer-${version}-android-arm64-release-unsigned.apk" \
  --output "release/MoonTransfer-${version}-android-arm64.apk" \
  --keystore "$HOME/.config/moontransfer/signing/release.p12" \
  --expected-sha256 IMPRONTA_PUBBLICA_SHA256 \
  --version "$version" --commit "$commit" --version-code "$version_code"
```

Sostituisci il segnaposto dell'impronta. La firma chiede le password; Invio alla
seconda domanda riusa quella del keystore. In esecuzione non interattiva servono
`MOONTRANSFER_ANDROID_STORE_PASSWORD` e `MOONTRANSFER_ANDROID_KEY_PASSWORD`
nell'ambiente, mai password negli argomenti del comando. `ANDROID_HOME` o `PATH`
individuano `apkanalyzer`, `zipalign` e `apksigner`; viene riconosciuto anche l'SDK
locale predefinito di Buildozer. Un APK firmato già esistente non viene sovrascritto.

Vecchie installazioni SDK di Buildozer possono avere un `tools/bin/apkanalyzer`
non funzionante: in quel caso installa `cmdline-tools;latest` con `sdkmanager`.
Il firmatario preferisce `cmdline-tools/*/bin/apkanalyzer` nell'SDK selezionato.

Sono verificati identità incorporata della build, contenuti obbligatori, sola
architettura ARM64, identificativo dell'app, SDK, versionName/versionCode,
assenza di debug/testOnly, filtri di condivisione, allineamento e certificato
atteso. Firmare un APK debug non lo converte in una release: viene rifiutato.

## Build firmata in CI

Apri **Actions > Build Android artifact > Run workflow**,
seleziona `main`, abilita `signed_release` e lascia `version_code` vuoto per usare
`android/release.toml`, oppure inserisci un override concordato per il test manuale.
Il job di build esegue i test e compila la release senza ricevere segreti. Un
secondo job su runner separato usa l'environment protetto `android-signing`,
scarica solo l'APK di quella esecuzione, firma, verifica ed elimina il keystore
temporaneo. Non ripristina cache di build e non installa dipendenze.

L'APK `MoonTransfer-<version>-android-arm64.apk` e `SHA256SUMS` sono scaricabili
dall'esecuzione per 14 giorni. L'artefatto intermedio `android-release-unsigned`
scade dopo un giorno e **non è installabile**. La versione CI include numero
dell'esecuzione e commit; il versionCode è indipendente. Per ricompilare in
locale quella revisione usa gli stessi commit, versione visualizzata e versionCode.
La firma coincide; non viene garantita la riproducibilità byte per byte.
PR, push su `main` e avvii manuali Android normali restano debug e non accedono
all'environment di firma.

## Desktop e Android insieme

Per provare senza pubblicare, avvia **Build release artifacts** manualmente su
`main` abilitando `signed_android`. Desktop e Android vengono compilati nella
stessa esecuzione, con identiche versione e revisione: dagli artefatti scarichi
i quattro archivi desktop e l'APK firmato. Serve l'environment di firma reale,
ma non viene creato alcun tag o release. `android_version_code` permette un
override del file soltanto per questo test manuale.

Un nuovo tag `vX.Y.Z-alpha.N`, `-beta.N` o `-rc.N` avvia il workflow desktop,
che richiama quello Android riutilizzabile alla stessa revisione. Android non ha
più un trigger tag indipendente, evitando build e pubblicazioni duplicate.
Il job finale attende tutte le build desktop e la firma Android, richiede
esattamente i quattro archivi desktop e `MoonTransfer-<version>-android-arm64.apk`
e genera un unico `SHA256SUMS` per tutti e cinque. APK debug/non firmati e versioni
inattese sono rifiutati. Crea o aggiorna una bozza di prerelease; non sovrascrive
release già pubblicate. Una build/firma fallita o una chiave mancante blocca la
bozza, invece di generare una release incompleta con il solo desktop.

Prima del primo tag configura `android-signing`, prova l'avvio manuale congiunto,
aggiorna se necessario `android/release.toml` e integra il lavoro tramite PR.
Il commit del tag deve essere già incluso in `main` e la sua versione numerica
deve coincidere con `pyproject.toml`. I tag e le release esistenti non cambiano.

## Passaggio sul dispositivo

La nuova chiave non coincide con quella dei prototipi debug. Normalmente serve
disinstallare il prototipo una volta prima della prima release firmata: questo
elimina i dati privati dell'app. Le release successive con la stessa chiave,
identificativo e versionCode valido possono aggiornarsi senza questo reset.
Debug e release condividono ancora l'identificativo e non possono convivere.
Non distribuire come release gli APK di prova firmati con chiavi temporanee.

## Test senza chiave definitiva

Dopo la build non firmata, puoi eseguire il test SDK con la sua identità. Crea una
chiave temporanea, verifica la firma locale e dopo un passaggio Base64, rifiuta
un'impronta errata ed elimina tutte le chiavi e gli APK firmati di prova:

```sh
MOONTRANSFER_SIGNING_TEST_APK="release/MoonTransfer-${version}-android-arm64-release-unsigned.apk" \
MOONTRANSFER_SIGNING_TEST_VERSION="$version" MOONTRANSFER_SIGNING_TEST_COMMIT="$commit" \
MOONTRANSFER_SIGNING_TEST_VERSION_CODE="$version_code" \
python3 -m unittest tests.test_android_signing -v
```

Fonti: [firma Android](https://developer.android.com/studio/publish/app-signing),
[apksigner](https://developer.android.com/tools/apksigner),
[protezione degli environment GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

## Verificare la configurazione GitHub

Nomi e valori delle variabili non devono contenere spazi iniziali/finali:
`ANDROID_KEY_ALIAS` deve valere esattamente `moontransfer`, senza virgolette.
La fingerprint è pubblica; le password e il keystore no.

```sh
gh secret list --env android-signing --repo gaumeloth/MoonTransfer
gh variable list --env android-signing --repo gaumeloth/MoonTransfer
gh variable get ANDROID_KEY_ALIAS --env android-signing --repo gaumeloth/MoonTransfer
```

Questi comandi non mostrano i valori dei secret. Un secret elencato può comunque
contenere un valore errato: la verifica effettiva avviene durante la firma.
Se usi un solo manutentore come revisore, abilitare `Prevent self-review`
impedisce a quella persona di approvare le proprie run; scegli consapevolmente
tra revisione indipendente e approvazione personale. Disabilita il bypass degli
amministratori se vuoi rendere obbligatoria l'approvazione configurata.

Una run in attesa richiede l'approvazione dell'environment dal riepilogo Actions.
In caso di firma fallita leggi il primo errore del job, correggi alias/secret se
necessario e riesegui i job falliti. Se hai modificato il workflow o il codice,
avvia una nuova run sulla revisione corretta: rieseguire la vecchia non applica
automaticamente i nuovi commit.

Prima di distribuire, prova anche il ripristino del backup della chiave in una
posizione privata separata e verifica la fingerprint con gli strumenti locali.
Non caricare backup o password tra gli artefatti. Per verifica dell'APK e dei
checksum vedi [Problemi comuni](../docs/TROUBLESHOOTING.it.md#verificare-i-download);
per la sequenza completa usa la [procedura di release](../docs/RELEASING.it.md#procedura-di-pubblicazione).
