# watchly-be

Backend API di Watchly (FastAPI, PostgreSQL, worker). Specifiche in [`docs/`](docs): [analisi funzionale](docs/watchly_analisi_funzionale.md) e [analisi tecnica](docs/watchly_be_analisi_tecnica.md).

## Sviluppo locale

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements-dev.txt -e . --no-deps
copy .env.example .env            # default locale: SQLite; deploy\env.example è solo per produzione
alembic upgrade head
uvicorn app.main:app --reload     # OpenAPI: http://localhost:8000/api/v1/docs
python -m app.jobs.worker         # job di sync, news, notifiche (processo separato)
```

Con Docker: `docker compose -f deploy/compose.dev.yaml up --build` (API su :8000, owner `dev@example.com`; eseguire prima `docker compose -f deploy/compose.dev.yaml run --rm api alembic upgrade head`).

Per sviluppo senza Postgres: `DATABASE_URL=sqlite:///./dev.db` e `SESSION_COOKIE_SECURE=false`.

Dipendenze: le versioni lockate sono in `requirements.txt` (runtime) e `requirements-dev.txt`, generate da `pyproject.toml` con `pip-compile --strip-extras pyproject.toml -o requirements.txt` e `pip-compile --strip-extras --extra dev pyproject.toml -o requirements-dev.txt`.

Qualità: `ruff check . && ruff format --check . && mypy app`.

## Architettura

- `app/views` endpoint REST sotto `/api/v1` (più `/health/live`, `/health/ready`), `app/schemas` DTO, `app/models` SQLAlchemy 2 (un file per entità), `app/services` logica, `app/providers` Kitsu/AniList/TMDB/RSS, `app/jobs/worker.py` job periodici.
- Autenticazione: cookie di sessione opaco (hash SHA-256 a DB, HttpOnly, SameSite, Secure) con password Argon2. Nessuna registrazione pubblica: l'owner è creato da `OWNER_EMAIL`/`OWNER_PASSWORD` o `python -m app.cli create-owner --email ...`. Ogni risorsa personale è filtrata per l'utente della sessione; le mutazioni verificano `Origin`.
- CORS: `ALLOWED_ORIGINS` contiene le origini frontend senza percorsi (es. `https://watchly.example`, non `/login`). Sono ammessi gli header `Content-Type`, `X-Request-ID`, `X-Requested-With` e `DNT`; una preflight `OPTIONS` rifiutata non raggiunge il controllo credenziali.
- Errori uniformi `{code, message, details, request_id}`; rate limit su login, ricerca, sync e refresh.
- `/me/sync` e `/series/{id}/refresh` accodano un job (`sync_runs`) eseguito dal worker, con cooldown; `/jobs/{id}` ne espone lo stato. Il calendario non interroga mai i provider.
- `GET /catalog/search` salva i risultati come serie canoniche (dedupe prudente: stesso tipo, anno e titolo normalizzato, candidato unico) e restituisce gli ID da usare per follow e dettaglio.

## Disponibilità italiana (vincolo di correttezza)

`episodes.original_air_date/at` è la prima uscita da provider; la disponibilità IT vive solo in `episode_availability`. Una riga `confirmed` conta **solo** se la fonte è marcata validata (`python -m app.cli validate-source <id>`) e ha evidenza, precisione e piattaforma; altrimenti degrada a `unknown`. Nessun provider attuale è validato: il calendario mostra `date_kind="original"` (uscita originale) e `mode=italy` restituisce solo le conferme. Le notifiche push partono solo per episodi confermati IT. Il gate di fattibilità (analisi tecnica §5) resta da completare prima di dichiarare il calendario «disponibile in Italia».

## Note di scope

- Redis non è introdotto: coda e lock usano PostgreSQL (`sync_runs`, claim atomico). Il rate limit è in memoria per processo (una replica API).
- Test automatici esclusi in questa fase (analisi tecnica §11); CI = lint, mypy, audit, `alembic check`, OpenAPI, build immagine.
- Pipeline: [CI](.github/workflows/ci.yml) valida PR e push su `main`; [deploy](.github/workflows/deploy.yml) parte solo dopo una CI riuscita su `main` dello stesso repository, mai da una PR. Checkout, tag immagine e deploy usano lo SHA esatto validato. Per un avvio manuale eseguire `backend-ci` su `main`: il deploy segue solo se la validazione passa.
- La migrazione nel deploy SSH viene eseguita senza stdin interattivo, per non consumare il resto dello script remoto. Nei log di un deploy riuscito deve comparire `deploy ok: <SHA>` dopo l'avvio di API e worker e il controllo readiness.
- Import dei dati dell'app mobile non implementato (P2): il database parte vuoto.
- Deploy: [`deploy/compose.yaml`](deploy/compose.yaml) (da copiare in `/opt/watchly-be`) e [workflow CD](.github/workflows/deploy.yml) (secret `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `WATCHLY_API_DOMAIN`). Provisionare prima l'edge condiviso come descritto sotto.

## Deploy con edge condiviso

L'edge e gli stack applicativi sono progetti Compose **indipendenti**, da avviare separatamente (non unirli con piu opzioni `-f`):

| Progetto | Compose | Reti | Porte host |
| --- | --- | --- | --- |
| `edge` | [`deploy/compose.edge.yaml`](deploy/compose.edge.yaml) | `proxy_shared` | 80 e 443, solo Traefik |
| `watchly-be` | [`deploy/compose.yaml`](deploy/compose.yaml), copia di riferimento in [`resources/watchly-be/compose.yaml`](resources/watchly-be/compose.yaml) | `watchly_private`; API anche su `proxy_shared` | nessuna |

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
5. Copiare il compose Watchly in `/opt/watchly-be/compose.yaml` e configurare `.env` da [`deploy/env.example`](deploy/env.example), con credenziali DB proprie. `DATABASE_URL` deve puntare a `postgres:5432` e corrispondere a utente, password e database di Watchly.

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
docker compose -f compose.yaml up -d api worker
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
