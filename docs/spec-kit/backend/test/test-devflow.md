# Guida allo Sviluppo Test — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare test automatizzati per le API di un microservizio. I test devono essere eseguiti prima di marcare un endpoint come completato.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **`input.json`** — File JSON contenente la lista degli endpoint/funzionalità da testare
2. **`test-spec-kit.md`** — Standard tecnici per struttura test, conftest, Docker, Makefile

---

## Struttura del JSON Test

| Campo | Significato |
| --- | --- |
| `id` | Identificativo univoco |
| `microservice` | Microservizio di appartenenza |
| `resource` | Risorsa/entità da testare |
| `endpoint` | URL dell'endpoint |
| `method` | Metodo HTTP |
| `test_file` | Path del file di test (es. `tests/test_resource.py`) |
| `scenarios` | Array di scenari da testare (tipo, descrizione, status_code atteso) |
| `requires_auth` | Se i test richiedono autenticazione JWT |
| `roles_to_test` | Ruoli da testare per i controlli permessi |
| `mock_uploads` | Se mockare `UploadsInternalClient` |
| `implemented` | `false` se i test non sono ancora scritti |
| `notes` | Note aggiuntive |

---

## Prerequisiti

Prima di iniziare, l'agent DEVE verificare:

1. Che `tests/conftest.py` esista con le fixture standard (`app`, `database`, `session`, `client`, `auth_headers`) — se non esiste, crearlo seguendo `test-spec-kit.md` sezione 7
2. Che `Dockerfile.test` esista — se non esiste, crearlo seguendo sezione 3
3. Che `docker-compose.test.yml` esista — se non esiste, crearlo seguendo sezione 4
4. Che `pytest.ini` esista alla radice del microservizio — se non esiste, crearlo seguendo sezione 6

---

## Flusso di Sviluppo per Singolo Set di Test

### Step 1 — Analisi endpoint

Leggere le specifiche dell'endpoint: view, schema, permessi, filtri, custom logic, side effects. I test devono coprire TUTTE le casistiche reali.

### Step 2 — Scrittura test

Creare o aggiornare il file `tests/test_<risorsa>.py` seguendo:

- **Naming**: classi `Test<Risorsa><Azione>`, funzioni `test_<scenario>` (sezione 8.1)
- **Struttura**: pattern ARRANGE → ACT → ASSERT (sezione 8.2)
- **Scenari obbligatori** per tipo endpoint (sezione 8.3):
  - GET list: lista vuota, lista con risultati, non autenticato, paginazione
  - GET detail: esistente, inesistente (404), non autenticato
  - POST create: valido, campo mancante (400), validazione (422), duplicato (409), non autenticato
  - PUT update: valido, inesistente (404), campo invalido (400), non autenticato
  - DELETE / azioni custom: successo, inesistente (404), non autenticato
- **Permessi**: un test `test_<metodo>_forbidden` per ogni ruolo non autorizzato
- **Soft delete**: un test `test_list_excludes_deleted` (sezione 8.4)
- **Filtri**: un test per ogni filtro specificato nel JSON
- **Mock uploads**: se `mock_uploads: true`, usare le fixture della sezione 8 di `file-management-spec-kit.md`

### Step 3 — Esecuzione

```
make test
```

Il comando lancia il docker-compose.test.yml, avvia l'infrastruttura e esegue i test.

### Step 4 — Iterazione

Se i test **falliscono**:
1. Analizzare l'errore (output pytest)
2. Correggere il codice applicativo **o** il test (se il test è sbagliato)
3. Rieseguire
4. Ripetere fino a che TUTTI i test passano

### Step 5 — Marcatura

Aggiornare `implemented: true` nel JSON per il set di test completato.

---

## Errori comuni e soluzioni

| Errore | Causa | Soluzione |
| --- | --- | --- |
| `401` invece di `403` | Il token JWT non è valido nel test | Verificare `generate_test_token()` e la `SECRET_KEY` del test |
| `AssertionError` su UUID | UUID serializzato come stringa vs oggetto | Confrontare `str(uuid)` o usare `uuid.UUID(data["id"])` |
| `IntegrityError` nel test | Dati creati in un test influenzano un altro | Verificare che il rollback transazionale funzioni nel `conftest.py` |
| Test passa ma il codice è sbagliato | Mock troppo permissivo | Verificare che il mock rispecchi il comportamento reale |

---

## Condizioni di BLOCCO

- Manca `conftest.py` con le fixture base
- I test usano dati condivisi tra test (assenza di isolamento)
- I test non coprono i permessi
- Un test fallisce

---

## Checklist per Test Completati

- [ ] `conftest.py` con fixture `app`, `database`, `session`, `client`, `auth_headers`
- [ ] File test creato in `tests/test_<risorsa>.py`
- [ ] Tutti gli scenari obbligatori coperti (lista, dettaglio, create, update, delete/archivio)
- [ ] Test permessi per ogni metodo e ruolo
- [ ] Test soft delete (exclusione record eliminati)
- [ ] Test filtri (se presenti)
- [ ] Mock `UploadsInternalClient` (se presenti campi file)
- [ ] Tutti i test PASSANO con `make test`
- [ ] Campo `implemented: true` nel JSON
