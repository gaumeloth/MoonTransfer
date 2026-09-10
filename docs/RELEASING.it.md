# Artefatti e release

[English](RELEASING.md) | [MoonTransfer](../README.it.md)

## Indice

- [Artefatti release desktop](#artefatti-release-desktop)
- [Artefatti Android di test](#artefatti-android-di-test)
- [Pubblicazione delle release desktop e Android](#pubblicazione-delle-release-desktop-e-android)
- [Procedura di pubblicazione](#procedura-di-pubblicazione)
- [Protezioni e diagnosi](#protezioni-e-diagnosi)

## Artefatti release desktop

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

Su Linux il runner installa l'insieme completo delle dipendenze XCB/XKB di Qt
prima della build. La validazione rifiuta un runtime nativo incompleto e uno
smoke test X11 avvia l'eseguibile già impacchettato e genera input da tastiera.
Questo evita che gli artefatti mescolino senza segnalarlo librerie Qt per la
tastiera incluse nel bundle con versioni incompatibili del sistema di
destinazione.

Gli artefatti Linux e macOS usano `tar.gz` per conservare permessi eseguibili e
link simbolici. Windows usa ZIP. L'archivio macOS contiene un bundle
`MoonTransfer.app`, mentre le altre piattaforme mantengono la normale struttura
`onedir` di PyInstaller. Ogni archivio contiene anche `LICENSE`,
`THIRD_PARTY_NOTICES.md`, entrambi i README, le guide per contributori e quelle
tecniche, le guide Android, i testi di licenza e il logo collegati. I percorsi
relativi vengono conservati per mantenere funzionanti i link dopo l'estrazione.
La lista esplicita in `tools/package_release.py` esclude sorgenti estranei e file
privati.

Le pull request, i push su `main` e le esecuzioni manuali del workflow creano
artefatti di prova senza pubblicare una release. Le build senza tag usano una
versione `dev` contenente il numero dell'esecuzione e il prefisso del commit.
Gli artefatti sono disponibili nel riepilogo dell'esecuzione del workflow per
14 giorni e possono essere scaricati per i test manuali sui sistemi
destinazione. La stessa versione completa e lo stesso commit sono incorporati
nel riepilogo diagnostico dell'applicazione.

## Artefatti Android di test

`.github/workflows/android-build.yml` fornisce una build Linux nativa separata
per il prototipo Android. Il percorso debug viene eseguito per pull request,
push su `main` e normali avvii manuali. Sui tag di prerelease il workflow principale
delle release richiama invece il percorso firmato. Il job usa versioni fissate di `uv`, Python 3.13.14,
Java 17, Go 1.25.12 e Rust 1.97.1; controlla il lock file Android; installa
l'ambiente di build Android bloccato; esegue i test specifici Android e la
diagnostica dell'host; quindi crea l'APK ARM64 di debug. I download di Android
SDK/NDK e Gradle vengono memorizzati nella cache, mentre la grande build nativa
di python-for-android resta intenzionalmente fuori dalla cache finché il
workflow non avrà prodotto dati reali sufficienti su tempi e affidabilità. Un
profilo Buildozer `ci` dedicato accetta in modo non interattivo le licenze SDK
configurate; le normali build locali mantengono la richiesta interattiva.

Prima del caricamento, MoonTransfer controlla che l'archivio APK non contenga
percorsi non sicuri o duplicati, verifica le librerie native ARM64 e i file
dell'applicazione generati attesi, rifiuta asset riservati ai sorgenti e
confronta versione di build, commit, versione di `croc` e versione del protocollo
MoonTransfer incorporati con la build CI corrente. Il workflow usa inoltre
`aapt` di Android per verificare ID dell'applicazione, nome e codice versione,
limiti SDK, stato debug e architettura nativa dichiarata. L'APK grezzo e
versionato è disponibile nel riepilogo dell'esecuzione del workflow per 14
giorni, senza un ulteriore contenitore ZIP.

Questo APK è un artefatto di test, non una release Android: non viene allegato
alla pagina GitHub Releases e non è firmato con una chiave di release controllata
dal progetto. Buildozer usa un'identità di firma debug che può essere diversa
tra una build locale e i runner GitHub. Android può quindi rifiutare
l'installazione di una sopra l'altra; disinstallare prima il prototipo esistente
risolve la mancata corrispondenza della firma, ma elimina anche i dati privati
dell'applicazione.

## Pubblicazione delle release desktop e Android

La pubblicazione è intenzionalmente più restrittiva:

- solo tag come `v0.1.0-alpha.1`, `v0.1.0-beta.1` o `v0.1.0-rc.1` avviano il
  job di release;
- la base numerica del tag deve corrispondere a `[project].version` in
  `pyproject.toml`;
- il commit del tag deve essere già incluso in `main`;
- tutte le build desktop e la build Android firmata devono terminare prima del
  job di release; una configurazione di firma mancante blocca la bozza;
- il workflow richiede i quattro archivi desktop e l'APK ARM64 firmato, quindi
  genera un unico `SHA256SUMS` per tutti e cinque;
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

## Procedura di pubblicazione

1. Configura la [firma Android](../android/SIGNING.it.md) e verifica un avvio manuale combinato su `main` con **Build release artifacts > signed_android**. Non crea tag o release.
2. Su un branch dedicato incrementa `android/release.toml` oltre ogni versionCode già distribuito, anche manualmente. Se cambia la base numerica, aggiorna `[project].version` e `uv.lock`. Aggiorna note e documentazione.
3. Esegui i controlli, apri una PR verso `main` e attendi il merge. Le modifiche non committate non entrano nel tag.
4. Esegui `git fetch origin`, torna su `main` con `git switch main`, poi esegui `git merge --ff-only origin/main`. Controlla branch, commit e `git status --short`: non devono restare modifiche alla release da integrare.
5. Scegli un tag annotato **nuovo**, nel formato `vX.Y.Z-alpha.N`, `vX.Y.Z-beta.N` o `vX.Y.Z-rc.N`; la base numerica deve coincidere con `pyproject.toml`. Controlla con `git tag --list` e `git ls-remote --tags origin` che non esista già.
6. Dopo aver sostituito `TAG_NUOVO` con il valore scelto, esegui `git tag -a TAG_NUOVO -m "MoonTransfer TAG_NUOVO"` e `git push origin TAG_NUOVO`. Non usare i segnaposto letteralmente.
7. Attendi le quattro build desktop e la firma Android. Approva i job negli environment protetti quando richiesto, poi verifica la bozza.
8. Scarica tutti e cinque i pacchetti e `SHA256SUMS`; [verifica i download](TROUBLESHOOTING.it.md#verificare-i-download), controlla versione/commit, documenti e trasferimenti sui dispositivi reali.
9. Pubblica manualmente la bozza solo dopo i test. Non spostare tag già distribuiti né sovrascrivere release pubblicate: correggi tramite PR e usa il tag successivo.

## Protezioni e diagnosi

Il job di firma usa `android-signing`; il job che crea la bozza usa un environment
distinto, `release`. Configura quest'ultimo prima del primo tag, con regole per i
tag di pre-release e revisori secondo la policy del progetto. Non copiarvi le
chiavi Android: la pubblicazione usa il `GITHUB_TOKEN` con permesso
`contents: write`, la firma resta nel proprio job.

Un job in attesa di approvazione non è una build fallita. Controlla gli environment
richiesti nel riepilogo della run. Il test manuale combinato verifica build e firma,
ma non esegue il job di creazione della bozza riservato ai tag.
Una run fallita non va sostituita con una release desktop-only.

Le regole degli environment si configurano nelle [impostazioni GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
