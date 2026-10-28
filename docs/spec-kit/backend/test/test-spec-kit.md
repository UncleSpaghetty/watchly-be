# Guida pratica: Test API nei microservizi

## Obiettivo

Questa guida definisce lo standard per implementare, strutturare e lanciare i test delle API in un'architettura a microservizi Python/Flask containerizzata con Docker.

---

## 1) Stack tecnologico

| Componente | Tecnologia | Scopo |
| --- | --- | --- |
| Linguaggio | Python 3.12 | Runtime dei microservizi |
| Framework | Flask + dFlango | Framework web e layer CRUD |
| Test runner | pytest | Esecuzione test e assertion |
| Coverage | pytest-cov | Report copertura codice |
| Database | PostgreSQL 17.2 | Database di test (effimero, via `tmpfs`) |
| Containerizzazione | Docker + Docker Compose | Isolamento ambiente di test |

---

## 2) Struttura file di progetto per i test

```text
project-root/
├── Makefile
├── docker-compose.test.yml
├── scripts/
│   ├── db/
│   │   ├── create-multiple-postgresql-databases.sh
│   │   └── healthcheck.sh
│   └── test/
│       ├── run-auth-test-service.sh      # bootstrap del servizio auth live
│       └── seed-test-user.py             # seed utente di test noto
├── apps/
│   ├── <microservice-a>/
│   │   ├── Dockerfile                    # immagine di produzione
│   │   ├── Dockerfile.test               # immagine esclusiva per i test
│   │   ├── requirements.txt
│   │   ├── pytest.ini
│   │   ├── app/                          # codice applicativo
│   │   └── tests/                        # test suite
│   │       ├── conftest.py
│   │       ├── test_<feature_a>.py
│   │       └── test_<feature_b>.py
│   └── <microservice-b>/
│       ├── Dockerfile
│       ├── Dockerfile.test
│       ├── requirements.txt
│       ├── pytest.ini
│       ├── app/
│       └── tests/
│           ├── conftest.py
│           └── ...
```

---

## 3) `Dockerfile.test` — Immagine esclusiva per i test

Ogni microservizio deve avere un `Dockerfile.test` separato dal `Dockerfile` di produzione. Questo file installa le dipendenze di test e definisce `pytest` come comando di default.

```dockerfile
FROM python:3.12-slim

WORKDIR /

# Dipendenze di produzione
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dipendenze di test
RUN pip install --no-cache-dir pytest pytest-cov

# Il codice sorgente e i test vengono montati come volume
# dal docker-compose.test.yml, NON copiati nell'immagine.
# Questo permette di eseguire i test sul codice locale senza rebuild.

CMD ["pytest", "-v"]
```

**Principi chiave:**

- L'immagine NON contiene codice sorgente né test: questi vengono montati come volumi dal `docker-compose.test.yml`
- Il `CMD` di default è `pytest -v`, ma può essere sovrascritto da riga di comando (es. per coverage)
- Non serve un utente non-root: è un container effimero di test

---

## 4) `docker-compose.test.yml` — Orchestrazione ambiente di test

Il file `docker-compose.test.yml` è separato dal `docker-compose.yml` di sviluppo e definisce l'intero ambiente di test.

### 4.1 Componenti

#### Database di test condiviso

Un singolo container PostgreSQL condiviso da tutti i microservizi, con dati effimeri via `tmpfs`:

```yaml
services:
  test-db:
    image: postgres:17.2
    environment:
      - POSTGRES_USER=test_user
      - POSTGRES_PASSWORD=test_password
      - POSTGRES_MULTIPLE_DATABASES=service_a_test,service_b_test,auth_service
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user"]
      interval: 3s
      timeout: 2s
      retries: 10
    tmpfs:
      - /var/lib/postgresql/data
    volumes:
      - ./scripts/db/create-multiple-postgresql-databases.sh:/docker-entrypoint-initdb.d/create-multiple-postgresql-databases.sh
```

**Note:**

- `tmpfs` garantisce che il database sia completamente effimero (nessun dato su disco)
- Lo script `create-multiple-postgresql-databases.sh` crea automaticamente N database dalla variabile `POSTGRES_MULTIPLE_DATABASES`
- L'healthcheck assicura che il DB sia pronto prima di avviare i test runner

#### Servizio auth live (per test inter-service)

Se un microservizio dipende da un altro (es. chiamate API interne per autenticazione), il servizio dipendenza deve essere avviato come istanza live:

```yaml
  auth-test-service:
    build: ./apps/auth
    depends_on:
      test-db:
        condition: service_healthy
    environment:
      - FLASK_ENV=testing
      - SECRET_KEY=test-secret-key-minimum-32-chars!!
      - DATABASE_URI=postgresql://test_user:test_password@test-db:5432/auth_service
      - INTERNAL_API_SECRET=test-internal-secret-token
      # ... altre variabili d'ambiente di test
    volumes:
      - ./apps/auth/app:/app
      - ./apps/auth/migrations:/migrations
      - ./scripts/test/seed-test-user.py:/seed-test-user.py
      - ./scripts/test/run-auth-test-service.sh:/run-auth-test-service.sh
    command: ["/bin/bash", "/run-auth-test-service.sh"]
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/auth/health/')\""]
      interval: 5s
      timeout: 3s
      retries: 15
      start_period: 10s
```

Lo script di bootstrap (`run-auth-test-service.sh`) esegue in sequenza:

1. Applicazione delle migrazioni (`flask db upgrade`)
2. Seed di un utente di test noto (ID deterministico)
3. Avvio del server

#### Test runner per ogni microservizio

Ogni microservizio ha un servizio test runner che usa `Dockerfile.test`:

```yaml
  <service>-test:
    build:
      context: ./apps/<service>
      dockerfile: Dockerfile.test
    depends_on:
      test-db:
        condition: service_healthy
      # aggiungere qui altri servizi dipendenti se necessario (es. auth-test-service)
    environment:
      - FLASK_ENV=testing
      - SECRET_KEY=test-secret-key-minimum-32-chars!!
      - DATABASE_URI=postgresql://test_user:test_password@test-db:5432/<service>_test
      - INTERNAL_API_SECRET=test-internal-secret-token
      - COVERAGE_FILE=/tmp/.coverage
      # ... altre variabili d'ambiente specifiche del microservizio
    volumes:
      - ./apps/<service>/app:/app
      - ./apps/<service>/tests:/tests
      - ./apps/<service>/pytest.ini:/pytest.ini
```

**Note:**

- I volumi montano il codice sorgente e i test dal filesystem locale
- `COVERAGE_FILE=/tmp/.coverage` evita conflitti di permessi
- Ogni test runner ha il proprio database dedicato

---

## 5) Comandi Makefile

### 5.1 Lancio test di TUTTI i microservizi

```makefile
test-all:
    @echo "Running ALL tests..."
    docker compose -f docker-compose.test.yml up --build -d test-db auth-test-service
    docker compose -f docker-compose.test.yml run --rm <service-a>-test && \
    docker compose -f docker-compose.test.yml run --rm <service-b>-test; \
    result=$$?; \
    docker compose -f docker-compose.test.yml down; \
    exit $$result
```

**Flusso:**

1. Avvia l'infrastruttura (DB + servizi dipendenti) in background con `--build -d`
2. Esegue i test runner in sequenza con `--rm` (rimuove il container al termine)
3. Cattura l'exit code dell'ultimo comando
4. Distrugge l'intero ambiente con `down`
5. Restituisce l'exit code catturato (per CI/CD)

### 5.2 Lancio test di un SINGOLO microservizio (con selezione interattiva)

Un unico comando `make test` che chiede all'utente quale microservizio testare:

```makefile
test:
    @echo "Available microservices:"; \
    echo ""; \
    i=1; \
    for dir in apps/*/; do \
        ms=$$(basename $$dir); \
        echo "  $$i) $$ms"; \
        i=$$((i + 1)); \
    done; \
    echo ""; \
    read -p "Enter microservice name: " ms; \
    if [ ! -d "apps/$$ms" ]; then \
        echo "Error: microservice '$$ms' not found in apps/"; \
        exit 1; \
    fi; \
    echo "Running tests for $$ms..."; \
    docker compose -f docker-compose.test.yml up --build -d test-db auth-test-service; \
    docker compose -f docker-compose.test.yml run --rm $$ms-test; \
    result=$$?; \
    docker compose -f docker-compose.test.yml down; \
    exit $$result
```

**Note:**

- Il comando elenca automaticamente tutti i microservizi presenti nella directory `apps/`
- L'utente inserisce il nome del microservizio (es. `auth`, `logs`)
- Il nome viene validato verificando l'esistenza della directory
- Il nome del servizio test nel `docker-compose.test.yml` deve seguire la convenzione `<nome-ms>-test`

### 5.3 Coverage di un singolo microservizio (con selezione interattiva)

```makefile
coverage:
    @echo "Available microservices:"; \
    echo ""; \
    i=1; \
    for dir in apps/*/; do \
        ms=$$(basename $$dir); \
        echo "  $$i) $$ms"; \
        i=$$((i + 1)); \
    done; \
    echo ""; \
    read -p "Enter microservice name: " ms; \
    if [ ! -d "apps/$$ms" ]; then \
        echo "Error: microservice '$$ms' not found in apps/"; \
        exit 1; \
    fi; \
    echo "Running tests with coverage for $$ms..."; \
    docker compose -f docker-compose.test.yml up --build -d test-db auth-test-service; \
    docker compose -f docker-compose.test.yml run --build --rm $$ms-test pytest --cov=app --cov-report=html:/tmp/htmlcov --cov-report=term-missing; \
    result=$$?; \
    docker compose -f docker-compose.test.yml down; \
    exit $$result
```

### 5.4 Coverage di TUTTI i microservizi

```makefile
coverage-all:
    @echo "Running ALL tests with coverage..."
    docker compose -f docker-compose.test.yml up --build -d test-db auth-test-service
    docker compose -f docker-compose.test.yml run --build --rm <service-a>-test pytest --cov=app --cov-report=html:/tmp/htmlcov --cov-report=term-missing && \
    docker compose -f docker-compose.test.yml run --build --rm <service-b>-test pytest --cov=app --cov-report=html:/tmp/htmlcov --cov-report=term-missing; \
    result=$$?; \
    docker compose -f docker-compose.test.yml down; \
    exit $$result
```

### 5.5 Sezione help

```makefile
help:
    @echo "Available commands:"
    @echo "  make test          - Run tests for a single microservice (interactive)"
    @echo "  make test-all      - Run ALL tests across all microservices"
    @echo "  make coverage      - Run tests with coverage for a single microservice (interactive)"
    @echo "  make coverage-all  - Run ALL tests with coverage report"
```

---

## 6) Configurazione `pytest.ini`

Ogni microservizio deve avere un file `pytest.ini` alla propria radice:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

---

## 7) Struttura `conftest.py`

Ogni microservizio deve avere un `conftest.py` nella directory `tests/` che configura:

### 7.1 App e client di test

```python
import pytest
from app import create_app
from dflango.db import db as _db


@pytest.fixture(scope="session")
def app():
    """Crea l'app Flask in modalità testing."""
    app = create_app()
    app.config["TESTING"] = True
    yield app


@pytest.fixture(scope="session")
def database(app):
    """Crea tutte le tabelle all'inizio della sessione e le distrugge alla fine."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=True)
def session(app, database):
    """
    Wrappa ogni test in una transazione che viene rollbackata al termine.
    Garantisce isolamento totale tra i test.
    """
    with app.app_context():
        connection = database.engine.connect()
        transaction = connection.begin()

        options = dict(bind=connection, binds={})
        session = database.create_scoped_session(options=options)
        database.session = session

        yield session

        transaction.rollback()
        connection.close()
        session.remove()


@pytest.fixture
def client(app):
    """Client HTTP di test Flask."""
    return app.test_client()
```

### 7.2 Helper per autenticazione

```python
import jwt
import uuid
from datetime import datetime, timezone, timedelta


# ID utente di test deterministico (deve corrispondere al seed)
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def generate_test_token(app, user_id=None, expires_in=3600):
    """Genera un JWT valido per i test."""
    user_id = user_id or TEST_USER_ID
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")


@pytest.fixture
def auth_headers(app):
    """Header Authorization con JWT valido."""
    token = generate_test_token(app)
    return {"Authorization": f"Bearer {token}"}
```

---

## 8) Pattern per i test API

### 8.1 Naming convention

- File: `test_<risorsa>.py` (es. `test_products.py`, `test_invoices.py`)
- Classi: `Test<Risorsa><Azione>` (es. `TestProductList`, `TestProductCreate`)
- Funzioni: `test_<scenario>` (es. `test_create_product_success`, `test_create_product_missing_field`)

### 8.2 Struttura di un test

```python
class TestProductList:
    """Test per GET /api/<service>/products/"""

    def test_list_empty(self, client, auth_headers):
        response = client.get("/api/<service>/products/", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data["results"] == []

    def test_list_returns_items(self, client, auth_headers, session):
        # ARRANGE - crea dati di test
        product = Product(name="Test", price=100)
        session.add(product)
        session.commit()

        # ACT
        response = client.get("/api/<service>/products/", headers=auth_headers)

        # ASSERT
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Test"

    def test_list_unauthenticated(self, client):
        response = client.get("/api/<service>/products/")
        assert response.status_code == 401
```

### 8.3 Scenari da testare per ogni endpoint

Per ogni endpoint API, coprire come minimo:

| Tipo endpoint | Scenari obbligatori |
| --- | --- |
| **GET list** | lista vuota, lista con risultati, non autenticato, paginazione |
| **GET detail** | risorsa esistente, risorsa inesistente (404), non autenticato |
| **POST create** | creazione valida, campo mancante (400), errore di validazione (422), dato duplicato (409), non autenticato |
| **PUT update** | aggiornamento valido, risorsa inesistente (404), campo invalido (400), errore di validazione (422), non autenticato |
| **DELETE** | cancellazione valida, risorsa inesistente (404), non autenticato |

### 8.4 Test su risorse soft-deleted

```python
def test_list_excludes_deleted(self, client, auth_headers, session):
    active = Product(name="Active", price=100)
    deleted = Product(name="Deleted", price=200, deleted_at=datetime.now(tz=timezone.utc))
    session.add_all([active, deleted])
    session.commit()

    response = client.get("/api/<service>/products/", headers=auth_headers)
    data = response.get_json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Active"
```

---

## 9) Script di supporto

### 9.1 `create-multiple-postgresql-databases.sh`

Script montato come init script del container PostgreSQL. Crea automaticamente N database dalla variabile d'ambiente `POSTGRES_MULTIPLE_DATABASES`:

```bash
#!/bin/bash
set -e
set -u

function create_user_and_database() {
    local database=$1
    echo "  Creating user and database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE USER $database;
        CREATE DATABASE $database;
        GRANT ALL PRIVILEGES ON DATABASE $database TO $database;
EOSQL
}

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
        create_user_and_database $db
    done
fi
```

### 9.2 `seed-test-user.py`

Script Python che crea un utente di test con ID deterministico nel database auth. L'ID è noto e condiviso con i `conftest.py` degli altri microservizi per generare JWT validi.

### 9.3 `run-auth-test-service.sh`

Script di bootstrap per il servizio auth live usato durante i test inter-service:

```bash
#!/bin/bash
set -e

echo ">>> Applying migrations..."
flask db upgrade

echo ">>> Seeding test user..."
python /seed-test-user.py

echo ">>> Starting server on port 8000..."
python run.py
```

---

## 10) Riepilogo convenzioni

| Aspetto | Convenzione |
| --- | --- |
| File di test | `apps/<ms>/tests/test_<risorsa>.py` |
| Dockerfile test | `apps/<ms>/Dockerfile.test` |
| Config pytest | `apps/<ms>/pytest.ini` |
| Fixtures | `apps/<ms>/tests/conftest.py` |
| DB test | PostgreSQL su `tmpfs`, database separato per MS |
| Isolamento | Transazione con rollback per ogni test |
| Naming servizio test | `<nome-ms>-test` nel `docker-compose.test.yml` |
| Comando test singolo MS | `make test` (selezione interattiva) |
| Comando test tutti i MS | `make test-all` |
| Coverage singolo MS | `make coverage` (selezione interattiva) |
| Coverage tutti i MS | `make coverage-all` |
