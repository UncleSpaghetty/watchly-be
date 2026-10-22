# Watchly Backend — Analisi tecnica

**Versione:** 1.0 · **Data:** 22 ottobre 2026 · **Repository:** `watchly-be` · **Target:** Docker Compose su DigitalOcean, con Traefik e PostgreSQL condivisi come infrastruttura, ma dati isolati.

## 1. Obiettivo e confini

Costruire l'API applicativa per `watchly-web`, trasferendo fuori dal dispositivo le responsabilità oggi distribuite fra `src/data/db/schema.ts`, `src/data/providers/*`, `src/data/sync.ts` e i servizi notifiche. Non spostare automaticamente le API native Expo né presumere che i dati locali SQLite dell'app mobile siano già sul server.

Nel sorgente allegato: Expo SDK 57, Kitsu/AniList per catalogo/episodi anime, TMDB per metadati TV, SQLite versione 4, sync all'avvio con soglia di 12 ore e notifiche locali. News ancora placeholder. Lo schema storico contiene `italy_availability`, ma la rimozione di trigger di validazione e l'uso di `original_air_date` rendono **non verificata** la semantica italiana. Il backend dovrà introdurre una separazione netta tra prima uscita e disponibilità italiana accertata.

## 2. Stack e struttura

**Proposta:** Python 3.12+ compatibile, **FastAPI** con Pydantic 2 e SQLAlchemy 2/Alembic; PostgreSQL 17; Redis opzionale nella fase iniziale; scheduler/worker in container separato quando servono acquisizione periodica, refresh e Web Push. Questa è una scelta progettuale nuova, non una dipendenza già presente nel progetto mobile. Valida anche Flask + REST con identici contratti, se si vuole allineare altri backend; non mescolare i due framework.

```text
watchly-be/
  app/
    main.py
    api/v1/{auth,catalog,series,following,calendar,episodes,news,settings,push,sync}.py
    core/{config,security,logging}.py
    db/{base,session,models}.py
    schemas/
    services/{catalog,matching,availability,calendar,sync,news,notifications}.py
    providers/{anilist,kitsu,tmdb,rss}.py
    jobs/
  alembic/versions/
  tests/{unit,integration,contract}/
  deploy/{Dockerfile,compose.yaml,compose.dev.yaml,env.example}/
  .github/workflows/{ci.yml,deploy.yml}
  pyproject.toml
```

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

**Gate di fattibilità:** prima di dichiarare il calendario «uscite disponibili in Italia», identificare una o più fonti autorizzate che forniscano realmente disponibilità del singolo episodio in Italia, con prova e condizioni d'uso; creare set di test su anime simulcast, serie Netflix whole-season, rinvii e timezone. Se non disponibile, la UI mostra «Disponibilità italiana non verificata» e può separatamente mostrare l'uscita originale senza falsi positivi.

Job idempotenti con lock, rate limiting e retry/backoff; ETag quando previsto; intervallo base periodico configurabile e refresh manuale per utente soggetto a cooldown. Non affidare la raccolta ai request thread né bloccare `GET /calendar` su provider remoti. Conservare stato successo/fallimento per fonte e serie.

## 6. Web Push e notifiche

Il worker cerca gli episodi **confermati in IT** per giornata locale in `Europe/Rome` e gli utenti opt-in; genera una notifica riepilogativa intorno alle 12:00 con deduplica idempotente (`user_id`, `local_date`, `channel`), coda retry e registrazione errori. Se l'episodio non è verificato, nessun avviso «disponibile»; eventuali promemoria previsionali devono essere una preferenza diversa e dichiarata.

Web Push API con VAPID; le chiavi private sono esclusivamente backend. L'utente deve installare il sito nella Home di iPhone e concedere permesso tramite gesto utente dove richiesto; Safari/OS possono ritardare l'arrivo: nessuna garanzia hard real-time. Eliminare subscriptions scadute/invalide; consentire revoke e check preferenze. Possibile fallback «oggi» nel calendario web.

## 7. Infrastruttura esistente: lettura del compose allegato

Il `compose.yaml` fornito è del progetto **la-bastarda-cinese** e include:

- `traefik:v3.6.16` con mapping host `80:80`, `443:443`, challenge HTTP Let's Encrypt e volume persistente `letsencrypt_data`.
- `postgres:17-alpine` con DB/user `bastarda` e volume `postgres_data`.
- `redis:7.4-alpine` con AOF, `web-asgi` su porta container 8000, `worker` Celery, `release` migration e `media` Nginx.
- Router Traefik generici `backend`, `media`, `backend-metrics` e middleware `internal-only`; nessuna `networks:` esplicita nel file allegato.

**Problema multi-progetto:** una seconda istanza Traefik non può bindare nuovamente 80/443; inoltre, il Traefik nel compose corrente non vede automaticamente container in reti Docker isolate di altri Compose. PostgreSQL separato per stack aumenterebbe consumo di RAM, backup e manutenzione. Non cambiare il volume Postgres esistente senza backup e test di ripristino.

### 7.1 Percorso immediato (migrazione conservativa)

1. Inventariare altri Compose sul Droplet, reti, hostname, versioni, volumi, backup, firewall e container correnti.
2. Creare una rete Docker esterna condivisa, ad es. `proxy_shared`, e collegarvi l'**unico** Traefik esistente e soltanto i container HTTP da pubblicare. Le reti DB rimangono private.
3. Aggiungere al compose bastarda `networks:` esplicite, mantenendo connettività di `web-asgi`, `worker`, `postgres`, `redis`, `media`. **Attenzione:** l'introduzione di reti personalizzate sostituisce il default automatico; assegnare rete `backend_private` ai servizi che oggi comunicano e `proxy_shared` a Traefik/servizi web; verificare nessuna interruzione. Eseguire in finestra di manutenzione e testare rollback.
4. Nel `watchly-be` Compose: API collegata a `proxy_shared` e a rete privata Watchly; DB/worker senza rete pubblica. Impostare `traefik.docker.network=proxy_shared` sull'API e su ogni altro servizio pubblicato; router/service nomi univoci, es. `watchly-api` (mai `backend`).
5. Usare inizialmente **un PostgreSQL dedicato al progetto Watchly** oppure la condivisione dell'istanza esistente solo dopo configurazione sicura dell'accesso di rete. Non esporre mai PostgreSQL verso Internet. L'istanza unica è obiettivo preferito ma richiede una migrazione gestita dell'infrastruttura comune.

### 7.2 Assetto consigliato a regime — infrastruttura condivisa

```text
/opt/platform/
  compose.yaml             # unico traefik, postgres, eventuale redis condiviso
  .env                      # segreti infrastruttura, chmod adeguato
/opt/la-bastarda-cinese/backend/
  compose.yaml             # soltanto web-asgi, worker, release, media
/opt/watchly-be/
  compose.yaml             # api, worker/scheduler, release
Docker networks:
  proxy_shared             # traefik e servizi HTTP
  db_shared                # postgres + soli client DB autorizzati
  bastarda_private         # redis e processi di bastarda
  watchly_private          # componenti interni Watchly
```

Separazione logica nello stesso Postgres: database `bastarda` utente `bastarda`, database `watchly` utente `watchly_app`, password e privilegi diversi, nessun superuser applicativo, `REVOKE`/privilegi minimi; schema/migrazioni isolati; backup per DB e prova restore. Un `POSTGRES_DB`/`POSTGRES_USER` configurato all'avvio crea solo la base iniziale: per aggiungere Watchly a un volume esistente usare script SQL/migrazione amministrativa **una tantum**, non aspettarsi che nuove env ricreino database.

**Importantissimo:** non spostare automaticamente `postgres_data`, `redis_data` o `letsencrypt_data` in un nuovo progetto Compose: nomi dei volumi potrebbero essere prefissati (`la-bastarda-cinese_...`). Se si trasferisce ownership ai servizi `/opt/platform`, dichiarare volumi `external: true` con `name:` effettivo; pianificare stop controllato e verifica `docker volume inspect`, dump/restore e certificati ACME. Evitare due processi Postgres sul medesimo data directory e due Traefik che scrivono sullo stesso `acme.json`.

### 7.3 Esempi Compose concettuali (da adattare dopo inventario)

Infrastruttura comune **solo a migrazione pianificata**:

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
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    networks: [db_shared]
    volumes: [postgres_data:/var/lib/postgresql/data]
    # Credenziali, healthcheck, restore e manutenzione secondo inventory.
networks:
  proxy_shared: {external: true}
  db_shared: {external: true}
volumes:
  letsencrypt_data:
    external: true
    name: la-bastarda-cinese_letsencrypt_data  # ESEMPIO; verificare con docker volume ls
  postgres_data:
    external: true
    name: la-bastarda-cinese_postgres_data     # ESEMPIO; verificare con docker volume ls
```

Watchly app **senza esporre direttamente porte sull'host**:

```yaml
name: watchly-be
services:
  api:
    image: ghcr.io/OWNER/watchly-be:${WATCHLY_IMAGE_TAG:?required}
    restart: unless-stopped
    env_file: .env
    networks: [proxy_shared, db_shared, watchly_private]
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
    networks: [db_shared, watchly_private]
    restart: unless-stopped
  migrate:
    image: ghcr.io/OWNER/watchly-be:${WATCHLY_IMAGE_TAG:?required}
    command: ["alembic", "upgrade", "head"]
    env_file: .env
    networks: [db_shared]
    profiles: [release]
networks:
  proxy_shared: {external: true}
  db_shared: {external: true}
  watchly_private: {}
```

Questo frammento è uno **schema architetturale**, non un Compose pronto al deploy senza variabili, provisioning e validazione Docker. Se la rete `proxy_shared` dà accesso al container HTTP da più servizi, limitare autorizzazione a livello API; rete Docker non equivale ad autenticazione. Rete `db_shared` è una barriera debole fra workload condivisi: usare credenziali minime, non affidarsi alla sola separazione di rete.

### 7.4 Hardening Traefik e Postgres

- `providers.docker.exposedbydefault=false`, router host specifici e prefissi univoci. Esplicitare la rete provider (`traefik.docker.network`) per evitare selection non deterministica; disabilitare dashboard pubblica.
- Proteggere Docker socket: mount `:ro` non limita l'autorità delle API Docker esposte dal socket; valutare socket proxy a endpoint limitati e isolamento dei privilegi.
- Firewall: solo 22 (limitato), 80, 443 dall'esterno; DB 5432 e Redis 6379 **mai pubblicati**; SSH key e aggiornamenti del sistema.
- Se il PostgreSQL è condiviso, valutare pool (per es. PgBouncer solo se serve) e `max_connections`; limiti memoria/CPU per workload; monitorare connessioni/disk.
- Backup `pg_dump` per singolo DB + volumi/ACME con retention e test restore regolari; snapshot Droplet non sostituisce backup DB consistente.
- Secret `.env` esclusi da Git; secret GitHub/Vercel separati; log strutturati e senza payload sensibili.

## 8. Pipeline CI — `.github/workflows/ci.yml`

Trigger pull request e push su `main`. Stage proposti:

1. Checkout, setup Python versione pin, install lock dipendenze.
2. Lint/format (`ruff check`, `ruff format --check`), type check (`mypy` o `pyright`, configurato), security/dependency audit.
3. Test unit e integrazione API; ephemeral PostgreSQL 17 service per migrazioni e isolamento dati.
4. `alembic upgrade head` su DB di test + smoke schema; controllare downgrade/compatibilità come strategia esplicita.
5. `docker build` del container in CI con Dockerfile multi-stage non-root e healthcheck; eventuale scansione immagine.
6. Output OpenAPI versionata: contratto consumato da `watchly-web` (CI del frontend con test contract).

Esempio schematico:

```yaml
name: backend-ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_USER: watchly_test
          POSTGRES_PASSWORD: watchly_test
          POSTGRES_DB: watchly_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U watchly_test" --health-interval 5s
          --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: python -m pip install -e '.[dev]'
      - run: ruff check . && ruff format --check .
      - run: pytest -q
      - run: docker build -t watchly-be:ci .
```

Nota: esempio da completare con env DB test, migration step, lockfile e policy di Actions SHA pin.

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
2. Provisioning reti esterne e connessione controllata del Traefik esistente: aggiungere `proxy_shared` senza rimuovere la rete originaria finché i router bastarda non sono verificati; poi normalizzare Compose.
3. Per MVP, è accettabile un Postgres Watchly separato e privato per ridurre rischio della prima migrazione. Per condivisione, creare `watchly` database + role separati nell'istanza attuale e predisporre rete sicura; misurare impatto.
4. Deploy Watchly API/worker senza porta host; aggiungere DNS dominio API verso Droplet; certificato TLS emesso dall'unico Traefik.
5. Eseguire smoke con domini bastarda pre-esistenti + Watchly; non eliminare servizi vecchi.
6. Solo dopo stabilizzazione, estrarre Traefik/Postgres dal Compose bastarda a `/opt/platform`, riutilizzando **gli stessi volumi esistenti**; procedura di cutover con piano di ritorno.

## 11. Test / criteri di completamento

- API con OpenAPI e error handling consistente; auth e ownership verificati da test di accesso incrociato.
- Catalog/search/serie/follow/calendar/watched/sync/news funzionanti e idempotenti.
- Date italiane confermate sempre corredate di fonte/evidenza; i casi privi di fonte non compaiono come confermati.
- Worker non manda duplicati e gestisce orario estivo/solare, retry e push revocate.
- Postgres con DB e ruoli separati, backups/ripristino collaudati.
- CI verde, immagine versionata, CD operativa, rollback release dimostrato senza toccare dati di `la-bastarda-cinese`.
- HTTPS via Traefik unico, endpoint health e nessuna porta DB accessibile da Internet.

## 12. Decisioni da congelare prima della realizzazione

- Scelta FastAPI vs Flask; tipo login e dominio/cookie; retention dati; licenze provider IT, RSS e TMDB; cadenzamento refresh; deployment Redis/worker; dominio API e CORS; soglie notif.
- Valutazione capacità Droplet (RAM, CPU, storage, backup e headroom) prima di ospitare ulteriore backend/worker.
- Necessità di cookie same-site tramite proxy/BFF sul frontend oppure strategia cross-origin sicura.

## 13. Riferimenti tecnici

- Expo sorgente: `watchly-main.zip` (`src/data/*`, `app/(tabs)/*`, `src/shared/notifications/*`).
- Docker Compose allegato: `Markdown incollato.md`, servizi `traefik`, `postgres`, `redis`, `web-asgi`, `worker`, `release`, `media`.
- Traefik Docker provider: https://doc.traefik.io/traefik/routing/providers/docker/
- Docker Compose networking: https://docs.docker.com/compose/how-tos/networking/
- PostgreSQL role management: https://www.postgresql.org/docs/17/user-manag.html
- GitHub Actions docker publish: https://docs.github.com/en/actions/how-tos/secure-your-work/publishing-packages/publishing-docker-images
