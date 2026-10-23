# Watchly Backend — Analisi tecnica

**Versione:** 1.1 · **Data:** 22 ottobre 2026 · **Repository:** `watchly-be` · **Target:** Docker Compose su DigitalOcean, con container applicativi e dati dedicati a Watchly; il solo Traefik di edge rimane condiviso per l'ingresso HTTP/HTTPS.

## 1. Obiettivo e confini

Costruire l'API applicativa per `watchly-web`, trasferendo fuori dal dispositivo le responsabilità oggi distribuite fra `src/data/db/schema.ts`, `src/data/providers/*`, `src/data/sync.ts` e i servizi notifiche. Non spostare automaticamente le API native Expo né presumere che i dati locali SQLite dell'app mobile siano già sul server.

Nel sorgente allegato: Expo SDK 57, Kitsu/AniList per catalogo/episodi anime, TMDB per metadati TV, SQLite versione 4, sync all'avvio con soglia di 12 ore e notifiche locali. News ancora placeholder. Lo schema storico contiene `italy_availability`, ma la rimozione di trigger di validazione e l'uso di `original_air_date` rendono **non verificata** la semantica italiana. Il backend dovrà introdurre una separazione netta tra prima uscita e disponibilità italiana accertata.

## 2. Stack e struttura

**Proposta:** Python 3.12+ compatibile, **FastAPI** con Pydantic 2 e SQLAlchemy 2/Alembic; PostgreSQL 17; Redis opzionale nella fase iniziale; scheduler/worker in container separato quando servono acquisizione periodica, refresh e Web Push. Questa è una scelta progettuale nuova, non una dipendenza già presente nel progetto mobile. Valida anche Flask + REST con identici contratti, se si vuole allineare altri backend; non mescolare i due framework.

```text
watchly-be/
  app/
    main.py
    views/
      {auth,catalog,series,following,calendar,episode,news,user_settings,push,sync}.py
    settings/
      {config,security,logging}.py
    models/
      base.py
      session.py
      {user,auth_session,series,episode,following,watched_episode,service,data_source,
       episode_availability,news_article,push_subscription,sync_run,
       provider_cache,notification_delivery}.py
    schemas/
      {auth,catalog,series,following,calendar,episode,news,user_settings,
       push,sync}.py
    services/{catalog,matching,availability,calendar,sync,news,notifications}.py
    providers/{anilist,kitsu,tmdb,rss}.py
    jobs/
  alembic/versions/
  deploy/{Dockerfile,compose.yaml,compose.dev.yaml,env.example}/
  .github/workflows/{ci.yml,deploy.yml}
  pyproject.toml
```

`models/base.py` contiene esclusivamente la base dichiarativa SQLAlchemy e le convenzioni comuni; `models/session.py` configura engine, session factory e dipendenza transazionale. La loro collocazione in `models/` mantiene un unico package di persistenza senza fingere che siano entità di dominio. Ogni modello ha il proprio file. La stessa regola vale per `schemas/` e `views/`: un file per risorsa/modello, nel quale possono convivere più classi strettamente correlate (per esempio `SeriesCreate`, `SeriesRead`, `SeriesUpdate`, oppure più view della risorsa `series`). Evitare file contenitore generici come `models.py`, `schemas.py` o `views.py`.

I provider devono implementare interfacce di raccolta e normalizzazione; mai legare la logica business a un particolare schema esterno. Le chiavi TMDB sono server-side.

## 3. API REST e contratto di risorse

Versione `/api/v1`, OpenAPI pubblicata dal servizio. DTO tipizzati con date RFC3339/ISO 8601, UTC nei timestamp e campo `local_date` riferito a `Europe/Rome`. Stato errori uniforme `{code,message,details,request_id}`; paginazione cursor per liste grandi; rate limit catalog/search/sync.

| Metodo | Endpoint | Autorizzazione / comportamento |
|---|---|---|
| `GET` | `/health/live` | probe processo, pubblico ma minimale |
| `GET` | `/health/ready` | probe DB ed eventuali dipendenze essenziali |
| `POST` | `/auth/login` | login proprietario; strategia sessione da finalizzare |
| `POST` | `/auth/logout` | revoca sessione |
| `GET` | `/me` | utente corrente |
| `GET` | `/catalog/search?q=&kind=` | ricerca aggregata provider, dedupe |
| `GET` | `/series/{id}` | dettaglio canonico |
| `GET` | `/series/{id}/episodes` | episodi, date originali e disponibilità IT distinta |
| `GET` | `/me/following` | watchlist personale |
| `PUT/DELETE` | `/me/following/{seriesId}` | follow/unfollow idempotente |
| `GET` | `/me/calendar?start=&end=` | occorrenze secondo criteri IT, filtrate per utente |
| `PUT` | `/me/episodes/{episodeId}/watched` | set visto; `DELETE` per annullare |
| `GET/PATCH` | `/me/settings` | preferenze, push opt-in, timezone |
| `POST` | `/me/sync` | richiede refresh controllato/asinc., ritorna job id |
| `GET` | `/jobs/{id}` | stato e errori del refresh personale |
| `GET` | `/news` | feed deduplicato, con opere correlate |
| `POST/DELETE` | `/me/push-subscriptions` | registrazione/rimozione subscription browser |

Non accettare ownership da input client. Se il prodotto parte per un singolo proprietario, bloccare la registrazione pubblica, ma strutturare tutte le relazioni per utente. Segreti sessione e VAPID privata in env/secret manager; hashing credenziali forte o provider auth affidabile.

## 4. Schema dati PostgreSQL proposto

Entità: `users`, `sessions` o equivalente auth, `series`, `series_external_ids` (`source`, `external_id` univoci), `episodes` (chiave canonica e identificativi di provider), `following` (`user_id`,`series_id` univoci; impostazioni per titolo), `watched_episodes` (`user_id`,`episode_id` univoci), `services`, `data_sources`, `episode_availability`, `news_articles`, `news_series_links`, `push_subscriptions`, `sync_runs`, `provider_cache`/etags e `notification_deliveries`.

`episode_availability` distingue `country_code=IT`, piattaforma, `available_at_utc` oppure `available_local_date`, `precision`, `status` (`confirmed|estimated|unknown|disputed|withdrawn`), `source_id`, `source_url`, `evidence_type`, `observed_at`, `last_verified_at`, `invalidated_at`. La sola presenza di watch provider TMDB per una serie **non prova** la data italiana di un episodio. `original_air_at`/`original_air_date` rimangono campi separati.

Vincoli: FK, unique, check coerenti, indici per `user_id`, date IT, `series_id`, provider ID e status. Audit di cambi data; versionamento delle migrazioni con Alembic; UTC a riposo, rendering per Europe/Rome. Progettare eliminazione account e pulizia subscriptions.

### Dati dell'app mobile

Nessuna migrazione automatica del database SQLite dallo ZIP: i file ignorati non includono i database utente. Definire import futuro con export JSON sul dispositivo, validazione schema, deduplicazione di ID esterni e riconciliazione di visti/follow. Per MVP web iniziare con database vuoto o import esplicito, senza fingere continuità dati.

## 5. Provider, disponibilità italiana e sincronizzazione

Pipeline: acquisizione AniList/Kitsu/TMDB → normalizzazione titoli/alias/ID e episodi → deduplica → raccolta evidenze di piattaforma/data IT → classificazione → snapshot per API calendario. RSS/news è pipeline separata con attribution e link alla fonte; collegamento news-serie tramite alias e confidenza, revisione se ambiguo.

**Gate di fattibilità:** prima di dichiarare il calendario «uscite disponibili in Italia», identificare una o più fonti autorizzate che forniscano realmente disponibilità del singolo episodio in Italia, con prova e condizioni d'uso; validare manualmente una matrice di casi su anime simulcast, serie Netflix whole-season, rinvii e timezone. Se non disponibile, la UI mostra «Disponibilità italiana non verificata» e può separatamente mostrare l'uscita originale senza falsi positivi.

Job idempotenti con lock, rate limiting e retry/backoff; ETag quando previsto; intervallo base periodico configurabile e refresh manuale per utente soggetto a cooldown. Non affidare la raccolta ai request thread né bloccare `GET /calendar` su provider remoti. Conservare stato successo/fallimento per fonte e serie.

## 6. Web Push e notifiche

Il worker cerca gli episodi **confermati in IT** per giornata locale in `Europe/Rome` e gli utenti opt-in; genera una notifica riepilogativa intorno alle 12:00 con deduplica idempotente (`user_id`, `local_date`, `channel`), coda retry e registrazione errori. Se l'episodio non è verificato, nessun avviso «disponibile»; eventuali promemoria previsionali devono essere una preferenza diversa e dichiarata.

Web Push API con VAPID; le chiavi private sono esclusivamente backend. L'utente deve installare il sito nella Home di iPhone e concedere permesso tramite gesto utente dove richiesto; Safari/OS possono ritardare l'arrivo: nessuna garanzia hard real-time. Eliminare subscriptions scadute/invalide; consentire revoke e check preferenze. Possibile fallback «oggi» nel calendario web.

## 7. Infrastruttura: edge condiviso e stack isolati

**Configurazione implementata:** [edge condiviso](../deploy/compose.edge.yaml) e [stack Watchly](../deploy/compose.yaml). La [procedura operativa](../README.md#deploy-con-edge-condiviso) descrive provisioning, cutover, conservazione ACME e rollback. I frammenti della sezione 7.3 restano esempi progettuali, non file da usare al posto dei compose implementati; Watchly attualmente non usa Redis.

L'edge condiviso usa `traefik:v3.6.16`, mapping host `80:80` e `443:443`, challenge HTTP Let's Encrypt e volume persistente `letsencrypt_data`. I servizi HTTP si collegano alla rete esterna `proxy_shared`; database e worker rimangono sulle reti private dei rispettivi progetti.

**Vincolo multi-progetto:** una seconda istanza Traefik non può bindare nuovamente 80/443 sullo stesso IP; inoltre, il proxy non raggiunge automaticamente container in reti Docker isolate di altri Compose. PostgreSQL separato per stack aumenta consumo di RAM, backup e manutenzione, ma garantisce l'isolamento richiesto. I volumi degli altri stack non vengono modificati né riutilizzati.

### 7.1 Percorso immediato (isolamento dei container Watchly)

1. Inventariare altri Compose sul Droplet, reti, hostname, versioni, volumi, backup, firewall e container correnti.
2. Creare una rete Docker esterna condivisa, ad es. `proxy_shared`, e collegarvi l'**unico** Traefik esistente e soltanto il container API Watchly da pubblicare. Le reti e i container dati rimangono privati e dedicati al relativo progetto.
3. Conservare le reti private degli stack gia ospitati; aggiungere `proxy_shared` soltanto ai servizi HTTP. Estrarre Traefik nello stack edge, connesso a `proxy_shared`. Eseguire in finestra di manutenzione e testare rollback.
4. Nel `watchly-be` Compose: API collegata a `proxy_shared` e a rete privata Watchly; PostgreSQL e worker soltanto sulla rete privata. Impostare `traefik.docker.network=proxy_shared` sui servizi HTTP; router/service/middleware con prefissi univoci per progetto.
5. Creare **PostgreSQL dedicato a Watchly**, con volume, credenziali, healthcheck, limiti di risorse e backup propri. Non collegarlo alle reti degli altri stack e non esporlo verso Internet. Redis non è necessario nell'implementazione attuale.

### 7.2 Assetto consigliato a regime — stack Watchly dedicato

```text
/opt/platform/
  compose.edge.yaml        # unico Traefik di edge per le porte host 80/443
  .env                      # segreti infrastruttura, chmod adeguato
/opt/watchly-be/
  compose.yaml             # api, worker, migrate, postgres
Docker networks:
  proxy_shared             # traefik e servizi HTTP
  watchly_private          # componenti interni Watchly
```

Watchly usa una propria istanza PostgreSQL, database `watchly`, utente applicativo `watchly_app`, volume nominato Watchly e backup/restore indipendenti. Anche Redis, se introdotto, ha container e volume Watchly. Questo evita condivisione di processo, credenziali, rete dati, ciclo di rilascio e failure domain con altri progetti.

Il solo componente comune è Traefik: non è un container applicativo di uno dei due progetti, ma l'edge del Droplet. Due istanze non possono occupare contemporaneamente le stesse porte host 80/443 sul medesimo IP. Un Traefik interamente dedicato richiederebbe un secondo IP/Droplet oppure un edge comune che gli inoltri il traffico, senza migliorare l'isolamento dei dati.

**Importantissimo:** i volumi dati esistenti restano nei rispettivi stack e non vengono riutilizzati da Watchly. Se si trasferisce l'ownership del solo Traefik a `/opt/platform`, dichiarare `letsencrypt_data` come volume `external: true` con il `name:` effettivo; pianificare stop controllato, verifica con `docker volume inspect`, backup dei certificati ACME e rollback. Evitare due Traefik che scrivono sullo stesso `acme.json`.

### 7.3 Esempi Compose concettuali (da adattare dopo inventario)

Edge comune **solo a migrazione pianificata**:

```yaml
name: platform
services:
  traefik:
    image: traefik:v3.6.16
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    networks: [proxy_shared]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt_data:/letsencrypt
    # Riportare tutte le opzioni di entrypoint, ACME, logs del compose corrente.
networks:
  proxy_shared: {external: true}
volumes:
  letsencrypt_data:
    external: true
    name: ${TRAEFIK_ACME_VOLUME:?required}  # Nome effettivo verificato sul server
```

Watchly app **senza esporre direttamente porte sull'host**:

```yaml
name: watchly-be
services:
  api:
    image: ghcr.io/OWNER/watchly-be:${WATCHLY_IMAGE_TAG:?required}
    restart: unless-stopped
    env_file: .env
    networks: [proxy_shared, watchly_private]
    labels:
      - traefik.enable=true
      - traefik.docker.network=proxy_shared
      - traefik.http.routers.watchly-api.rule=Host(`${WATCHLY_API_DOMAIN}`)
      - traefik.http.routers.watchly-api.entrypoints=websecure
      - traefik.http.routers.watchly-api.tls=true
      - traefik.http.routers.watchly-api.tls.certresolver=letsencrypt
      - traefik.http.services.watchly-api.loadbalancer.server.port=8000
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live',timeout=3)"]
      interval: 15s
      timeout: 5s
      retries: 4
  worker:
    image: ghcr.io/OWNER/watchly-be:${WATCHLY_IMAGE_TAG:?required}
    command: ["python", "-m", "app.jobs.worker"]  # comando da implementare
    env_file: .env
    networks: [watchly_private]
    restart: unless-stopped
  postgres:
    image: postgres:17-alpine
    env_file: .env
    networks: [watchly_private]
    volumes: [watchly_postgres_data:/var/lib/postgresql/data]
    restart: unless-stopped
  redis:
    image: redis:7.4-alpine
    command: ["redis-server", "--appendonly", "yes"]
    networks: [watchly_private]
    volumes: [watchly_redis_data:/data]
    restart: unless-stopped
  migrate:
    image: ghcr.io/OWNER/watchly-be:${WATCHLY_IMAGE_TAG:?required}
    command: ["alembic", "upgrade", "head"]
    env_file: .env
    networks: [watchly_private]
    profiles: [release]
networks:
  proxy_shared: {external: true}
  watchly_private: {}
volumes:
  watchly_postgres_data: {}
  watchly_redis_data: {}
```

Questo frammento è uno **schema architetturale**, non un Compose pronto al deploy senza variabili, provisioning e validazione Docker. Se la rete `proxy_shared` dà accesso al container HTTP da più servizi, limitare autorizzazione a livello API; rete Docker non equivale ad autenticazione. PostgreSQL e Redis non appartengono a `proxy_shared` e non pubblicano porte host.

### 7.4 Hardening Traefik e Postgres

- `providers.docker.exposedbydefault=false`, router host specifici e prefissi univoci. Esplicitare la rete provider (`traefik.docker.network`) per evitare selection non deterministica; disabilitare dashboard pubblica.
- Proteggere Docker socket: mount `:ro` non limita l'autorità delle API Docker esposte dal socket; valutare socket proxy a endpoint limitati e isolamento dei privilegi.
- Firewall: solo 22 (limitato), 80, 443 dall'esterno; DB 5432 e Redis 6379 **mai pubblicati**; SSH key e aggiornamenti del sistema.
- Per il PostgreSQL Watchly dedicato, configurare `max_connections`, limiti memoria/CPU e monitoraggio di connessioni e disco; introdurre PgBouncer solo se misure reali ne mostrano la necessità.
- Backup `pg_dump` per singolo DB + volumi/ACME con retention e test restore regolari; snapshot Droplet non sostituisce backup DB consistente.
- Secret `.env` esclusi da Git; secret GitHub/Vercel separati; log strutturati e senza payload sensibili.

## 8. Pipeline CI — `.github/workflows/ci.yml`

Trigger pull request e push su `main`. Stage proposti:

1. Checkout, setup Python versione pin, install lock dipendenze.
2. Lint/format (`ruff check`, `ruff format --check`), type check (`mypy` o `pyright`, configurato), security/dependency audit.
3. Verifica statica delle migrazioni Alembic e generazione dell'OpenAPI, senza introdurre una suite di test in questa fase.
4. `docker build` del container in CI con Dockerfile multi-stage non-root e healthcheck; eventuale scansione immagine.
5. Pubblicazione dell'OpenAPI versionata come contratto consumabile da `watchly-web`.

Esempio schematico:

```yaml
name: backend-ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: python -m pip install -e '.[dev]'
      - run: ruff check . && ruff format --check .
      - run: docker build -t watchly-be:ci .
```

Nota: esempio da completare con validazione Alembic/OpenAPI, lockfile e policy di Actions SHA pin. I test automatici sono esplicitamente fuori dallo scope di questa fase e potranno essere introdotti in una fase successiva.

## 9. Pipeline CD — DigitalOcean esistente

**Approccio consigliato:** GitHub Actions builda una sola immagine Docker per commit con tag SHA, la pubblica su GHCR e attiva deploy SSH al Droplet usando credenziali tecniche con privilegi minimi. Assenza di build sul server; i segreti di runtime vivono sul Droplet.

1. Trigger `main` o release/tag dopo esito CI; evitare doppio deploy concorrente.
2. Login GHCR con token `packages:write`, build/push `ghcr.io/<owner>/watchly-be:<git-sha>`.
3. Via SSH autenticato, aggiornare `WATCHLY_IMAGE_TAG` **solo** in `/opt/watchly-be/.env` o file di release, non il compose degli altri servizi.
4. `docker compose -f /opt/watchly-be/compose.yaml --profile release run --rm migrate` prima dello switch se le migration sono backward-compatible; poi `docker compose pull && docker compose up -d --no-deps api worker`.
5. Health/smoke `https://<api-domain>/health/ready` e controlli su calendar/catalog/auth; verificare certificato Traefik.
6. Se health fallisce, ripristinare tag immagine precedente e `up -d`; **non** promettere rollback automatico di migrazioni DB distruttive. Strategia expand/contract, backup pre-migrazione, feature flag.
7. Retention immagini, log deploy e alert (spazio disco/memoria, DB errors, 5xx e worker backlog).

Esempio **indicativo** di job deploy:

```yaml
name: backend-deploy
on:
  workflow_dispatch:
  push:
    branches: [main]
concurrency:
  group: watchly-be-production
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/OWNER/watchly-be:${{ github.sha }}
      # Aggiungere SSH deploy verificato, migrazioni, health gate e rollback.
```

Per repository privata GHCR, gestire credenziali server in modo sicuro; non rendere pubblico il repository per semplificare impropriamente l'installazione. Considerare deploy via runner self-hosted solo dopo valutazione di sicurezza.

## 10. Sequenza operativa, senza downtime imposto agli altri servizi

1. Inventario e backup di tutti i servizi/volumi attuali (`docker compose config`, `docker network ls`, `docker volume ls`, `docker ps`, `pg_dump`, backup ACME); test restore in ambiente isolato.
2. Provisioning reti esterne e connessione controllata del Traefik esistente: aggiungere `proxy_shared` senza rimuovere le reti private originarie; verificare tutti i router.
3. Provisioning di PostgreSQL Watchly separato e privato, con volume e backup dedicati; verificare l'headroom del Droplet prima dell'avvio.
4. Deploy Watchly API/worker senza porta host; aggiungere DNS dominio API verso Droplet; certificato TLS emesso dall'unico Traefik.
5. Eseguire smoke con tutti i domini preesistenti e Watchly; non eliminare servizi vecchi.
6. Se necessario estrarre il solo Traefik da uno stack esistente a `/opt/platform`, riutilizzare **lo stesso volume ACME esistente**; seguire la procedura di cutover con piano di ritorno. I database restano nei rispettivi stack.

## 11. Criteri di completamento della fase

- API con OpenAPI e error handling consistente; auth e ownership verificate durante smoke check manuali.
- Catalog/search/serie/follow/calendar/watched/sync/news funzionanti e idempotenti.
- Date italiane confermate sempre corredate di fonte/evidenza; i casi privi di fonte non compaiono come confermati.
- Worker non manda duplicati e gestisce orario estivo/solare, retry e push revocate.
- Postgres con DB e ruoli separati, backups/ripristino collaudati.
- CI statica verde, immagine versionata, CD operativa, rollback release dimostrato senza toccare container o dati di altri progetti.
- HTTPS via Traefik unico, endpoint health e nessuna porta DB accessibile da Internet.

La progettazione e implementazione di test automatici unitari, di integrazione e contract è esclusa da questa fase.

## 12. Decisioni da congelare prima della realizzazione

- Scelta FastAPI vs Flask; tipo login e dominio/cookie; retention dati; licenze provider IT, RSS e TMDB; cadenzamento refresh; deployment Redis/worker; dominio API e CORS; soglie notif.
- Valutazione capacità Droplet (RAM, CPU, storage, backup e headroom) prima di ospitare ulteriore backend/worker.
- Necessità di cookie same-site tramite proxy/BFF sul frontend oppure strategia cross-origin sicura.

## 13. Riferimenti tecnici

- Expo sorgente: `watchly-main.zip` (`src/data/*`, `app/(tabs)/*`, `src/shared/notifications/*`).
- Docker Compose implementati: [edge](../deploy/compose.edge.yaml) e [Watchly](../deploy/compose.yaml).
- Traefik Docker provider: https://doc.traefik.io/traefik/routing/providers/docker/
- Docker Compose networking: https://docs.docker.com/compose/how-tos/networking/
- PostgreSQL role management: https://www.postgresql.org/docs/17/user-manag.html
- GitHub Actions docker publish: https://docs.github.com/en/actions/how-tos/secure-your-work/publishing-packages/publishing-docker-images
