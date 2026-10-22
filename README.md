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
- Errori uniformi `{code, message, details, request_id}`; rate limit su login, ricerca, sync e refresh.
- `/me/sync` e `/series/{id}/refresh` accodano un job (`sync_runs`) eseguito dal worker, con cooldown; `/jobs/{id}` ne espone lo stato. Il calendario non interroga mai i provider.
- `GET /catalog/search` salva i risultati come serie canoniche (dedupe prudente: stesso tipo, anno e titolo normalizzato, candidato unico) e restituisce gli ID da usare per follow e dettaglio.

## Disponibilità italiana (vincolo di correttezza)

`episodes.original_air_date/at` è la prima uscita da provider; la disponibilità IT vive solo in `episode_availability`. Una riga `confirmed` conta **solo** se la fonte è marcata validata (`python -m app.cli validate-source <id>`) e ha evidenza, precisione e piattaforma; altrimenti degrada a `unknown`. Nessun provider attuale è validato: il calendario mostra `date_kind="original"` (uscita originale) e `mode=italy` restituisce solo le conferme. Le notifiche push partono solo per episodi confermati IT. Il gate di fattibilità (analisi tecnica §5) resta da completare prima di dichiarare il calendario «disponibile in Italia».

## Note di scope

- Redis non è introdotto: coda e lock usano PostgreSQL (`sync_runs`, claim atomico). Il rate limit è in memoria per processo (una replica API).
- Test automatici esclusi in questa fase (analisi tecnica §11); CI = lint, mypy, audit, `alembic check`, OpenAPI, build immagine.
- Import dei dati dell'app mobile non implementato (P2): il database parte vuoto.
- Deploy: `deploy/compose.yaml` (da copiare in `/opt/watchly-be`) e `.github/workflows/deploy.yml` (secret `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `WATCHLY_API_DOMAIN`). Traefik e rete `proxy_shared` sono quelli di edge esistenti; il compose non è stato validato con Docker (daemon non disponibile in questo ambiente).
