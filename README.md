# watchly-be

Backend API di Watchly (Flask/dflango, PostgreSQL, worker). Specifiche in [`docs/`](docs): [analisi funzionale](docs/watchly_analisi_funzionale.md) e [analisi tecnica](docs/watchly_be_analisi_tecnica.md).

## Sviluppo locale

```sh
cp .env.example .env
docker compose -f deploy/compose.dev.yaml up --build
```

La compose locale avvia PostgreSQL, applica automaticamente le migrazioni, quindi avvia API con hot reload e worker. L'API è su `http://localhost:8000`; l'owner iniziale è `dev@example.com` / `dev-password-change-me`. La sorgente locale ignorata `dflango/` non entra nell'immagine: Docker installa la stessa versione pubblicata e bloccata (`dflango==0.7.10`) usata da CI e produzione.

Per eseguire un comando nel container API:

```sh
docker compose -f deploy/compose.dev.yaml exec api flask --app app.main:app routes
docker compose -f deploy/compose.dev.yaml exec api python -m app.cli generate-vapid
```

L'esecuzione nativa con venv resta disponibile come alternativa:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt -e . --no-deps
alembic upgrade head
flask --app app.main:app run --debug --port 8000
python -m app.jobs.worker
```

Per sviluppo senza Postgres: `DATABASE_URL=sqlite:///./dev.db` e `SESSION_COOKIE_SECURE=false`.

Per attivare le news, inserire in `NEWS_FEED_URLS` uno o più URL RSS separati da virgola e
avviare anche il worker. Il worker aggiorna i feed ogni `NEWS_REFRESH_MINUTES` minuti, usa
ETag/Last-Modified per evitare download inutili, deduplica gli articoli per URL e collega una
notizia a una serie solo quando trova un alias non ambiguo. Il frontend legge il risultato da
`GET /api/v1/news`; non scarica direttamente gli RSS delle fonti.

Per abilitare Google Login, creare un client OAuth 2.0 di tipo **Applicazione web** in Google Cloud,
configurare tra le origini JavaScript autorizzate `http://localhost:3000` e il dominio frontend di
produzione, quindi impostare lo stesso client ID in `GOOGLE_CLIENT_ID` sul backend e in
`NEXT_PUBLIC_GOOGLE_CLIENT_ID` durante la build del frontend. Non serve un client secret: il backend
verifica firma, audience, scadenza ed email verificata dell'ID token Google.

Dipendenze: le versioni lockate sono in `requirements.txt` (runtime) e `requirements-dev.txt`, generate da `pyproject.toml` con `pip-compile --strip-extras pyproject.toml -o requirements.txt` e `pip-compile --strip-extras --extra dev pyproject.toml -o requirements-dev.txt`.

Qualità: `ruff check . && ruff format --check . && mypy app`.

## Architettura

- `app/views` contiene view class-based dflango, registrate centralmente da `app/routes.py`; gli endpoint REST restano sotto `/api/v1` (più `/health/live`, `/health/ready`).
- `app/schemas` usa Marshmallow tramite le basi `Schema`/`ModelSchema` di dflango; `app/models` usa il `db.Model` e la sessione Flask-SQLAlchemy inizializzati da dflango.
- `app/services` contiene la logica di dominio e riceve la sessione dflango; `app/providers` integra Kitsu/AniList/TMDB/RSS e `app/jobs/worker.py` esegue i job periodici dentro l'application context Flask.
- Autenticazione: sia `POST /auth/login` (email/password Argon2, mantenuto per compatibilità) sia `POST /auth/google` terminano nello stesso cookie di sessione opaco (hash SHA-256 a DB, HttpOnly, SameSite, Secure). Google viene usato solo per verificare l'identità: `user_identities` conserva il `sub` stabile e lo collega a `users`; al primo accesso viene creato un utente oppure collegato quello con la stessa email quando Google ne è autoritativo (Gmail o Workspace). L'owner classico resta creabile da `OWNER_EMAIL`/`OWNER_PASSWORD` o CLI. Ogni risorsa personale è filtrata per l'utente della sessione; le mutazioni verificano `Origin`.
- CORS: `ALLOWED_ORIGINS` contiene le origini frontend senza percorsi (es. `https://watchly.example`, non `/login`). Sono ammessi gli header `Content-Type`, `X-Request-ID`, `X-Requested-With` e `DNT`; una preflight `OPTIONS` rifiutata non raggiunge il controllo credenziali.
- Errori uniformi `{code, message, details, request_id}`; rate limit su login, ricerca, sync e refresh.
- `/me/sync` e `/series/{id}/refresh` accodano un job (`sync_runs`) eseguito dal worker, con cooldown; `/jobs/{id}` ne espone lo stato. Il calendario non interroga mai i provider.
- `GET /catalog/search` salva i risultati come serie canoniche (dedupe prudente: stesso tipo, anno e titolo normalizzato, candidato unico) e restituisce gli ID da usare per follow e dettaglio.
- `GET /me/dashboard?weeks=12` aggrega lato server KPI personali, attività, progresso, generi e tempo di visione stimato. Le durate, i generi e le valutazioni pubbliche vengono normalizzati da AniList, Kitsu e TMDB; i voti sono esposti su scala 0–100.

## Date degli episodi

`episodes.air_date/air_at` contiene esclusivamente la data pubblicata dal provider selezionato durante la sincronizzazione. Se più provider sono collegati alla stessa serie, viene scelto il dataset con il maggior numero di episodi datati e, a parità, quello più completo. Calendario, notifiche e API usano direttamente questa data senza introdurre disponibilità territoriali o stime locali.

## Note di scope

- Redis non è introdotto: coda e lock usano PostgreSQL (`sync_runs`, claim atomico). Il rate limit è in memoria per processo (una replica API).
- I test unitari si eseguono con `python -m unittest discover -s tests`; la CI continua a validare lint, mypy, audit, `alembic check`, route Flask/dflango e build immagine.
- Pipeline: [CI](.github/workflows/ci.yml) valida PR e push su `main`; [deploy](.github/workflows/deploy.yml) parte solo dopo una CI riuscita su `main` dello stesso repository, mai da una PR. Checkout, tag immagine e deploy usano lo SHA esatto validato. Per un avvio manuale eseguire `backend-ci` su `main`: il deploy segue solo se la validazione passa.
- La migrazione nel deploy SSH viene eseguita senza stdin interattivo, per non consumare il resto dello script remoto. Nei log di un deploy riuscito deve comparire `deploy ok: <SHA>` dopo l'avvio di API e worker e il controllo readiness.
- Import dei dati dell'app mobile non implementato (P2): il database parte vuoto.
- Deploy: [`deploy/compose.yaml`](deploy/compose.yaml) (da copiare in `/opt/watchly-be`) e [workflow CD](.github/workflows/deploy.yml) (secret `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `WATCHLY_API_DOMAIN`). Provisionare prima l'edge condiviso come descritto sotto.

## Deploy con edge condiviso

L'edge e gli stack applicativi sono progetti Compose **indipendenti**, da avviare separatamente (non unirli con piu opzioni `-f`):

| Progetto | Compose | Reti | Porte host |
| --- | --- | --- | --- |
| `edge` | [`deploy/compose.edge.yaml`](deploy/compose.edge.yaml) | `proxy_shared` | 80 e 443, solo Traefik |
| `watchly-be` | [`deploy/compose.yaml`](deploy/compose.yaml), copia di riferimento in [`resources/watchly-be/compose.yaml`](resources/watchly-be/compose.yaml) | `watchly_private`; API e Adminer anche su `proxy_shared` | nessuna |

Ogni stack mantiene il proprio servizio `postgres`, credenziali e volume. Il nome del servizio puo essere identico: il DNS `postgres` si risolve nella rete privata del rispettivo progetto. Non cambiare i nomi dei progetti esistenti (ne usare un diverso `-p`/`COMPOSE_PROJECT_NAME`): cambierebbero anche i nomi dei volumi, facendo apparire i database vuoti.

Traefik inoltra `https://<WATCHLY_API_DOMAIN>` a Watchly sulla **443 dello stesso IP** usato dagli altri domini ospitati. Servono domini distinti con DNS A (ed eventuale AAAA corretto) verso il server. La porta 80 serve per redirect HTTPS e challenge Let's Encrypt. Le porte interne 8000 possono coincidere perche non vengono pubblicate sull'host. Router, servizi e middleware devono avere nomi univoci tra tutti gli stack.

### Preparazione sul server

1. Copiare il compose edge in `/opt/platform/compose.edge.yaml` e [`deploy/edge.env.example`](deploy/edge.env.example) in `/opt/platform/.env`; impostare email ACME reale e proteggere il file con `chmod 600`.
2. Individuare il volume **effettivamente montato** dal Traefik precedente. Se il container esiste ancora, anche fermo:

   ```sh
   cd /percorso/stack-esistente
   docker inspect "$(docker compose ps -aq traefik)" --format '{{json .Mounts}}'
   ```

   Se e stato rimosso con `docker compose down`, usare `docker volume ls` e il compose precedente per identificare il volume ACME, poi verificarlo con `docker volume inspect NOME_VOLUME_EFFETTIVO`. Inserire quel nome in `TRAEFIK_ACME_VOLUME`, senza copiare alla cieca il valore di esempio. Il compose edge lo dichiara esterno, quindi fallisce se manca invece di creare silenziosamente un nuovo archivio certificati. Salvare un backup del volume prima del riavvio.
3. Controllare con `docker network ls` se `proxy_shared` esiste; se assente, eseguire `docker network create proxy_shared`.
4. Per ogni stack gia ospitato, conservare il vecchio compose come `compose.before-edge.yaml` **nella stessa directory**. Rimuovere il servizio Traefik locale e il suo riferimento al volume ACME, aggiungere la rete esterna `proxy_shared` ai soli servizi HTTP e mantenere anche le loro reti private originali. Impostare `traefik.docker.network=proxy_shared`, nomi di router/service/middleware univoci e resolver `letsencrypt`. Conservare nomi di progetto, volumi dati, build e mount originali.
5. Copiare il compose Watchly in `/opt/watchly-be/compose.yaml` e configurare `.env` da [`deploy/env.example`](deploy/env.example), con credenziali DB proprie. `DATABASE_URL` deve puntare a `postgres:5432` e corrispondere a utente, password e database di Watchly. Adminer sarà disponibile su `https://<WATCHLY_API_DOMAIN>/admin/` (lo slash finale è normalizzato automaticamente), con server precompilato `postgres`; l'accesso richiede le credenziali PostgreSQL.

I file possono essere trasferiti direttamente dalla macchina locale con `scp`, senza attendere un push. La pipeline CD non copia il compose sul server e non provisiona l'edge: questi passaggi sono manuali.

Per una **nuova installazione**, senza certificati preesistenti, creare una volta un volume con `docker volume create edge_letsencrypt_data` e impostare `TRAEFIK_ACME_VOLUME=edge_letsencrypt_data`. Non farlo per sostituire il volume di un'installazione esistente.

### Cutover del Traefik esistente

Eseguire in una finestra di manutenzione: ci sara una breve interruzione HTTP/HTTPS. I database non vengono rimossi.

```sh
cd /opt/platform
docker compose --env-file .env -f compose.edge.yaml config -q

cd /percorso/stack-esistente
docker compose -f compose.yaml config -q
# Stop del solo vecchio proxy, prima di avviare quello condiviso.
docker compose -f compose.before-edge.yaml stop traefik
# Se il container esiste ancora, backup di acme.json (chiavi private).
# Se e stato rimosso, fare il backup del volume prima di proseguire.
umask 077
docker cp "$(docker compose -f compose.before-edge.yaml ps -aq traefik):/letsencrypt/acme.json" ./acme.before-edge.json
# Riavvia lo stack con la rete condivisa; NON usare --remove-orphans qui.
docker compose -f compose.yaml up -d

cd /opt/platform
docker compose --env-file .env -f compose.edge.yaml up -d

cd /opt/watchly-be
docker compose -f compose.yaml config -q
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d postgres
docker compose -f compose.yaml --profile release run --rm migrate
docker compose -f compose.yaml up -d api worker adminer
```

Se gli stack sono gia fermi e il vecchio container Traefik e stato rimosso, saltare lo stop e la copia dal container: restano obbligatori identificazione e backup del volume ACME. Ricreare `proxy_shared` se eliminata. Interrompere la procedura se un comando fallisce. Non avviare mai contemporaneamente i due Traefik, ne farli scrivere sullo stesso archivio ACME. Non usare `down -v`: i volumi dati e certificati devono essere conservati.

Verificare dai client esterni tutti i domini, redirect da HTTP a HTTPS, certificati validi, health Watchly (`/health/ready`) e funzionalita degli altri servizi ospitati. Controllare anche worker, accesso DB e `docker compose -f /opt/platform/compose.edge.yaml logs --tail=100 traefik`. Il deploy CD Watchly rimane indipendente e non riavvia edge o altri stack.

Dopo gli smoke check, rimuovere **solo** il vecchio container fermo:

```sh
cd /percorso/stack-esistente
docker compose -f compose.before-edge.yaml rm -f traefik
```

Rollback del cutover: fermare prima il nuovo proxy con `docker compose -f /opt/platform/compose.edge.yaml stop traefik`, ripristinare il vecchio compose dello stack esistente da `compose.before-edge.yaml` e avviarlo con `docker compose -f compose.yaml up -d`. Il vecchio Traefik ritrovera lo stesso volume ACME; Watchly non sara esposto finche non si ripristina l'edge condiviso. Conservare backup e vecchio compose fuori da Git fino alla verifica completa.

I compose sono validabili con `docker compose config`; la verifica statica non sostituisce gli smoke check sul server con domini, immagini e segreti reali.
