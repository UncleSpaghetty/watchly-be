# Watchly Web — Analisi funzionale

**Versione:** 1.0 · **Data:** 22 ottobre 2026 · **Repository prevista:** `watchly-web`  
**Ambito:** migrazione dell'app mobile Watchly a un'applicazione web responsive, installabile come PWA ove supportato.

## 1. Scopo e principi

Watchly consente di cercare anime e serie TV, seguirli senza inserire manualmente ogni episodio, visualizzare un calendario, segnare gli episodi visti, consultare notizie collegate ai titoli e ricevere promemoria opzionali. Il prodotto web deve privilegiare iPhone/mobile, pur funzionando su desktop. Lingua iniziale: italiano; calendario e notifiche nel fuso `Europe/Rome`.

**Requisito cardine di prodotto:** le uscite mostrate come **disponibili in Italia** devono essere sostenute da evidenze relative alla disponibilità italiana del singolo episodio. Le date di prima trasmissione originale non diventano automaticamente date italiane. Se l'informazione è mancante, mostrarlo chiaramente; non inventare uscite settimanali confermate.

Il sistema ha due applicazioni distinte: `watchly-web` (interfaccia, PWA e interazioni) e `watchly-be` (API, utenti, dati normalizzati, acquisizione da provider, sincronizzazione e notifiche web). Il frontend sarà ospitato su Vercel, il backend su DigitalOcean.

## 2. Situazione verificata dell'app mobile sorgente

Analisi basata su `watchly-main.zip` (67 voci ZIP; codice applicativo Expo SDK 57 / React Native 0.86.3 / React 19.2.3):

| Area | Stato riscontrato nel sorgente | Destinazione web |
|---|---|---|
| Navigazione | 5 tab: Calendario, Cerca, News, Le mie serie, Impostazioni; pagina dettaglio `/serie` | Preservare IA e denominazioni, adattare a mobile e desktop |
| Calendario | Vista settimana predefinita e mese; navigazione periodi; selezione giorno | Migrare con accessibilità web e responsive |
| Episodi visti | `episodes.watched_at`, modificabile su episodi passati | Preservare comportamento, dati sul backend |
| Ricerca | Anime tramite Kitsu/AniList, scelta fonte; TV tramite TMDB; debounce 400 ms | Ricerca unificata API backend, mantenere filtri/fonte ove utile |
| Follow | Segui/non seguire, lista con filtro categoria e ricerca | Persistenza account backend |
| Episodi | Kitsu e AniList per anime; TMDB non fornisce ancora episodi in questo codice | Completare TV; separare date originali e date italiane |
| Sync | All'avvio se ultimo successo oltre 12 ore; refresh manuale in Impostazioni | Refresh server-side + azione manuale e indicatore aggiornamento |
| Notifiche | Locali iOS, pianificazione prossimi 30 giorni, alle 12:00 Europe/Rome | Web Push **opt-in**, limitazioni Safari/iOS; fallback nell'app |
| News | Schermata vuota: «Nessun feed configurato» | Implementare feed e associazione ai titoli, senza inventare notizie |
| Persistenza | SQLite locale, migrazioni fino a versione 4 | Backend PostgreSQL; cache client eventuale |
| Disponibilità in Italia | Schema `italy_availability` esiste ma calendario/notifiche interrogano `original_air_date` | Correggere semantica e UX prima di dichiarare date italiane |

**Non presumere** che le funzioni dichiarate nel README siano tutte operative: prevale il codice. Le news sono placeholder e le notifiche locali non equivalgono alle web push.

## 3. Utenti, accesso e ownership

### 3.1 Profilo iniziale

MVP orientato all'utilizzo personale, con possibile evoluzione multiutente. Poiché il web distribuito su Vercel è raggiungibile pubblicamente, la privacy della watchlist richiede autenticazione e autorizzazione server-side; non usare un `user_id` fornito dal browser come criterio di accesso.

- **MVP:** un utente proprietario autenticato, eventualmente accesso mediante invito/registrazione disabilitata.
- **Preparazione all'espansione:** entità utente e watchlist separate; mai mescolare dati personali fra utenti.
- Sessione persistente sicura, logout, stato di login e gestione errori.
- Non inserire token di servizi esterni o segreti in variabili client pubbliche.

### 3.2 Visitatori non autenticati

Decisione proposta: visualizzazione opzionale di catalogo e news pubbliche; calendario personale, follow, visti, preferenze e push richiedono login. Se si sceglie una beta interamente privata, proteggere tutte le pagine applicative.

## 4. Mappa delle pagine

| Rotta proposta | Scopo | Funzioni principali |
|---|---|---|
| `/` | Calendario | Oggi, vista settimana/mese, episodi, stati |
| `/search` | Cerca | Anime/TV, risultati, filtri, sorgenti |
| `/series/[id]` | Dettaglio | Metadati, stagioni, episodi, Segui, Aggiorna |
| `/my-series` | Le mie serie | Follow, filtro anime/TV, cerca nella lista |
| `/news` | News | Feed, filtro e collegamento serie |
| `/news/[id]` (opz.) | Dettaglio editoriale | Estratto consentito, link alla fonte, titoli correlati |
| `/settings` | Impostazioni | Push, sync, fuso/lingua, account |
| `/login` | Accesso | Autenticazione proprietario |

**Mobile:** bottom navigation analoga all'app originale. **Desktop:** sidebar o top navigation adattiva, stesso modello informativo. Il tema scuro originale è il default; supporto accessibile per contrasti e focus.

## 5. Requisiti funzionali

### RF-01 — Calendario

- Vista **settimana come default** e commutazione **mese**; lunedì come primo giorno.
- Navigazione avanti/indietro, ritorno a oggi, evidenziazione giorno corrente, selezione giorno con episodi.
- Elenco ordinato per data e titolo, con poster se disponibile, titolo serie, stagione, numero, titolo episodio e piattaforma quando nota.
- Distinguere: `disponibile in Italia (confermato)`, `previsto/non verificato`, `uscita originale`, `data non disponibile`, `data ritirata/contestata`. Solo i dati realmente confermati per IT possono portare il primo badge.
- Filtri per anime/TV, seguite, visti/non visti, stato e piattaforma (se copertura sufficiente).
- Date già trascorse: marcatura come visto/non visto; preservare comportamento sorgente senza vincolarlo per sempre ai soli episodi passati (scelta estendibile).
- Nessun evento «confermato» sintetizzato da periodicità; eventuali previsioni devono essere esplicitamente indicate come tali e disabilitate inizialmente nell'agenda Italia.
- Stati vuoto, caricamento, errore, staleness dei dati ed assenza connessione ben distinguibili.

### RF-02 — Ricerca e dettaglio

- Ricercare titoli con input debounce, minimo 2 caratteri e risultati annullabili.
- Filtri Anime / Serie TV; catalogo normalizzato; conservare ID di sorgente e alias dei titoli.
- Dettaglio: copertina, titoli alternativi, descrizione, formato/anno, stagioni, stato, episodi conosciuti, eventuali evidenze di disponibilità IT.
- `Segui` / `Non seguire` idempotenti; conferma stato; nessun inserimento manuale di singoli episodi.
- `Aggiorna informazioni`: operazione manuale non bloccante con feedback sullo stato e sull'ultimo aggiornamento; eventuale rate limiting.
- Mancanza di episodi per una serie non impedisce di seguirla.

### RF-03 — Le mie serie

- Elenco persistente delle serie seguite, ricerca locale o server-side, filtri Tutte/Anime/Serie TV.
- Aprire dettaglio e rimuovere dalla watchlist.
- Indicare la prossima disponibilità italiana *solo se verificata*; diversamente mostrare «Data italiana non ancora disponibile».
- Non duplicare una stessa opera semplicemente perché proviene da provider differenti; nelle ambiguità usare selezione esplicita dell'utente.

### RF-04 — Aggiornamenti

- Il backend aggiorna metadati/episodi e disponibilità con job controllati; il frontend mostra aggiornamento e provenienza senza dover rimanere aperto.
- L'utente può richiedere un refresh della serie o della watchlist.
- «Ultimo aggiornamento riuscito» non deve apparire tale in caso di refresh parziale o con errore.
- Cambiamenti e rinvii rettificano il calendario; non mantenere «confermata» una data che il provider ritira.

### RF-05 — Notifiche web

- Opt-in esplicito, impostazione globale ON/OFF; permesso browser richiesto soltanto dopo azione dell'utente.
- **Alle 12:00 Europe/Rome**, una sola notifica aggregata se ci sono episodi con disponibilità italiana confermata per la giornata, e soltanto per titoli seguiti con notifiche attive.
- Click sulla notifica apre il calendario/giorno relativo.
- Se il browser/dispositivo non supporta web push, il toggle è disabilitato con spiegazione e le novità restano visibili nell'app.
- **iPhone:** le web push richiedono generalmente l'installazione del sito sulla schermata Home e il consenso alle notifiche; non promettere push in una normale scheda Safari.
- Notificare «in programma oggi» se l'orario di disponibilità è ignoto, non «già online».
- Disattivazione: cessare invii e revocare registrazione associata se possibile; evitare duplicati.

### RF-06 — News

- Lista cronologica con fonte, titolo, data, breve estratto nei limiti consentiti, immagine solo se utilizzabile, collegamento all'articolo originale.
- Distinguere news anime/TV e, ove possibile, titoli seguiti.
- Collegamento a schede serie tramite matching affidabile; non associare automaticamente notizie ambigue.
- Da una news, aprire la serie correlata e poterla seguire con un'azione.
- Fallback «Nessun feed configurato» o «Nessuna notizia disponibile» quando appropriato.

### RF-07 — PWA, caching e disconnessione

- Installabile su iPhone attraverso Safari → Condividi → Aggiungi alla schermata Home, quando le condizioni/browser lo consentono.
- UI navigabile e risorse statiche disponibili dopo installazione e prima visita riuscita, nei limiti della cache.
- Ultimi dati già consultati visibili offline come **copia locale non aggiornata**, mai come verità live; mutazioni offline solo se viene realizzata una coda di sincronizzazione affidabile (non obbligatoria nel MVP).
- Ricerca remota, nuovi dati e news richiedono connettività; mostrare indicazione chiara.
- Accesso autenticato offline: comportamento da definire rispetto alla durata della sessione; non promettere accesso persistente indefinito.

### RF-08 — Impostazioni e privacy

- Gestire notifiche e stato permessi, ultimo sync, gestione account/logout e reset cache locale.
- Zona oraria applicativa fissata a Europe/Rome per la programmazione italiana; display delle date coerente anche da altri fusi.
- Conservare solo dati personali necessari; richiesta di rimozione account/dati prevista per futuro multiutente.

## 6. Flussi utente

**Aggiunta serie:** Cerca → filtra categoria → scegli risultato → dettaglio → Segui → conferma → «Le mie serie» → calendario quando esistono date IT convalidate.

**Aggiornamento:** Impostazioni/Dettaglio → Aggiorna → caricamento → esito completo/parziale/errore → calendario aggiornato.

**News:** News → articolo → eventuale serie correlata → dettaglio → Segui → calendario (anche se non esistono ancora date).

**Notifiche:** Installa PWA su iPhone → Impostazioni → Abilita notifiche → concedi permesso → sottoscrizione → avviso aggregato nelle giornate con episodi verificati; disattivazione annulla gli invii futuri.

**Segna visto:** Calendario → episodio → Visto/Non visto → conferma visiva immediata con rollback in caso di errore API.

## 7. Distinzione dei dati: vincolo di correttezza

- `original_air_date`: prima trasmissione; **mai reinterpretarla implicitamente come `available_in_it_date`**.
- `italy_availability`: episodio, piattaforma, stato, precisione, fonte, evidenza, osservazione e verifica.
- `confirmed`: obbligo di evidenza valida per episodio e Italia; `estimated`: previsione distinta; `unknown`: assente; `disputed` e `withdrawn`: non mostrare come uscita certa.
- Catalogo anime e TV può esistere anche senza calendario IT.
- **Release gate:** prima della pubblicazione verificare fonti realmente idonee alle date italiane. In caso di copertura insufficiente, attivare una modalità esplicitamente denominata «Programmazione originale», non falsare l'etichetta Italia.

## 8. Migrazione dati dall'app attuale

I dati dell'app risiedono nel database SQLite locale sul telefono, non nel repository ZIP. Di conseguenza lo ZIP **non contiene watchlist personale, episodi visti o preferenze dell'utente**. La migrazione automatica di questi dati non è possibile dal solo sorgente.

Percorso proposto: nuova versione Expo di esportazione JSON (serie seguite con `source + external_id`, ID episodio, `watched_at`, preferenze) → import autenticato nel backend con anteprima, deduplicazione e report → controllo utente. Non caricare file SQLite grezzi al server senza validazione. In alternativa, avvio pulito della web app.

## 9. MVP e priorità

**P0 — parità core:** login privato; catalogo; dettaglio; follow/unfollow; calendario settimana/mese; visti; impostazioni e aggiornamento; gestione fonti/dati italiani onesta; layout iPhone/desktop; Vercel.

**P1 — esperienza prevista:** episodi serie TV, disponibilità IT verificata per i titoli coperti, news reali, associazioni news-titoli, web push alle 12, installabilità PWA.

**P2 — evoluzioni:** import Watchly mobile, filtri avanzati piattaforma, import MyAnimeList/AniList, preferenze multiple utenti, sincronizzazione offline mutabile.

L'eventuale rinvio delle news/push deve risultare esplicitamente nelle release notes, non nascondere funzionalità inesistenti dietro interfacce operative.

## 10. Criteri di accettazione

1. Un utente autenticato aggiunge una serie una sola volta anche ripetendo l'azione.
2. Una serie TV senza date disponibili può essere seguita senza errori.
3. Il calendario mostra correttamente settimane ISO lunedì-domenica e cambio mese/anno nel fuso Rome.
4. I dati originali Kitsu/AniList/TMDB non appaiono con l'etichetta «Disponibile in Italia» senza evidenza specifica.
5. La marcatura visto resta salvata dopo logout/login e da due browser diversi.
6. Dopo refresh con fallimento della fonte, restano visibili i dati precedenti contrassegnati come potenzialmente non aggiornati.
7. News senza associazione certa non propongono titoli arbitrari.
8. Le notifiche sono facoltative, non duplicate, aggregate per giorno e limitate agli episodi IT confermati; modalità incompatibile segnala la limitazione.
9. La PWA installata avvia l'interfaccia e mostra contenuti precedentemente cached senza connettività, indicando lo stato offline.
10. La piattaforma distribuita su Vercel comunica via HTTPS al backend e non espone segreti/provider token nel bundle client.
11. Test end-to-end da iPhone Safari/Home Screen e da desktop (Chrome/Firefox) coprono i flussi principali.

## 11. Questioni aperte e decisioni già assunte

**Assunte:** nome Watchly; UI italiana; calendario riferimento Italia; FE Vercel; BE DigitalOcean; repository separate; VS Code; mobile-first; nessun obbligo di app nativa.

**Da validare prima della messa in produzione:** dominio definitivo; scelta dell'autenticazione (singolo utente/registrazione); fonti legalmente/tecnicamente idonee alla disponibilità IT per episodio; frequenza effettiva sincronizzazione; feed utilizzabili e condizioni editoriali; budget web push e limiti iOS; strategia import dati locali.

## 12. Origine della specifica

- Codice nello ZIP: `app/(tabs)/*`, `app/serie.tsx`, `src/data/db/schema.ts`, `src/data/providers/*`, `src/data/sync.ts`, `src/shared/notifications/*`, `src/shared/date/italy.ts`.
- Il comportamento futuro del prodotto è marcato come **requisito proposto**, non come funzionalità già implementata.
