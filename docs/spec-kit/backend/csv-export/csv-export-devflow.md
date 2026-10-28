# Guida allo Sviluppo Export CSV — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare un nuovo tipo di export CSV asincrono. Il flusso copre la creazione dello schema CSV, della view di richiesta e della logica del worker.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **`input.json`** — File JSON contenente la lista degli export CSV da implementare con le specifiche (entità, filtri, colonne, permessi)
2. **`csv-export-spec-kit.md`** — Standard tecnici per Model, Schema CSV, View, Worker
3. **`../schema-api/schema-api-spec-kit.md`** — Convenzioni View, URLs, Permessi
4. **`../file-management/file-management-spec-kit.md`** — Upload file su storage

---

## Struttura del JSON Export CSV

| Campo | Significato |
| --- | --- |
| `id` | Identificativo univoco |
| `export_type` | Identificatore stringa dell'export (es. `orders_csv`) — usato come `export_type` nel model e nel registry |
| `entity` | Entità principale esportata |
| `domain` | Dominio logico |
| `microservice` | Microservizio di appartenenza |
| `filename_prefix` | Prefisso del nome file generato |
| `batch_size` | Dimensione batch per la query (default 2000) |
| `columns` | Array di colonne con `key`, `header`, `getter` (opzionale), `formatter` (opzionale) |
| `filters` | Filtri disponibili nella richiesta (nome, tipo, validazione) |
| `roles` | Ruoli autorizzati a richiedere l'export |
| `query_base` | Descrizione della query base (entità, filtri applicati, ordinamento) |
| `implemented` | `false` se da implementare |
| `notes` | Note aggiuntive |

---

## Prerequisiti

Prima di iniziare, l'agent DEVE verificare:

1. Che la struttura `app/exports/csv/` esista con `fields.py`, `schemas.py`, `registry.py` — se non esiste, crearla seguendo `csv-export-spec-kit.md` sezione 4
2. Che `BaseExportRequestView` esista in `app/views/export/base_export_request.py` — se non esiste, crearla estendendo `dflango.views.BaseExportRequestView` come descritto in `csv-export-spec-kit.md` sezione 5
3. Che il client HTTP `app/services/internal/export_downloads.py` esista con `ExportDownloadsInternalClient` — se non esiste, crearlo seguendo `csv-export-spec-kit.md` sezione 5.3

> **Nota**: Il model `ExportDownload` è centralizzato nel microservizio `uploads`. I microservizi richiedenti (auth, crm) non devono avere il model localmente.

---

## Flusso di Sviluppo per Singolo Export CSV

### Step 1 — Schema CSV

Creare il file `app/exports/csv/<entity>_export.py`:

1. Importare `CSVField`, `CSVExportSchema` e i formatters necessari (`format_datetime`, ecc.)
2. Definire la classe con `export_type`, `filename_prefix`, `batch_size`, `fields`
3. Implementare `get_queryset()` con la query specificata nel JSON
4. Implementare `validate_filters()` se il JSON ha filtri
5. Registrare nello schema con `@CSVExportRegistry.register`
6. Importare la classe in `app/exports/csv/__init__.py` per attivare la registrazione

### Step 2 — View di richiesta

Creare il file `app/views/export/<entity>_export.py`:

1. Importare `BaseExportRequestView` da `app.views.export.base_export_request`
2. Creare una sottoclasse che imposta `export_type` con il valore dello schema

### Step 3 — URL e Permessi

Registrare in `urls.py` la route specifica per l'entità:
- `POST /<entity>/@export/` → `<Entity>ExportView`

> **Nota**: Le route generiche `GET /export-downloads/` e `GET /export-downloads/<uuid>/download/` sono nel microservizio `uploads` e non vanno aggiunte nel microservizio richiedente.

Aggiungere il permesso per il nuovo endpoint in `permissions.py` con il nome dell'endpoint Flask.

### Step 4 — Test

Scrivere test per:
- `POST /<entity>/@export/` con filtri validi → `202`, risposta con `id`, `export_type`, `status: QUEUED`
- `POST /<entity>/@export/` con ruolo non autorizzato → `403`
- `POST /<entity>/@export/` senza autenticazione → `401`
- Mockare la chiamata HTTP a uploads con `unittest.mock.patch` su `app.services.internal.export_downloads.create_export_download`

### Step 5 — Esecuzione e Iterazione

```
make test
```

Se i test falliscono → analizzare, correggere, rieseguire.

### Step 6 — Marcatura

Aggiungere `"managed": true` nel JSON per l'export completato.

---

## Condizioni di BLOCCO

- `CSVExportRegistry` non ha lo schema registrato (manca l'import in `__init__.py`)
- La chiamata HTTP a uploads non è mockata nei test
- I test falliscono

---

## Checklist per Export CSV Completato

- [ ] `fields.py`, `schemas.py`, `registry.py` presenti in `app/exports/csv/`
- [ ] Client HTTP `export_downloads.py` presente in `app/services/internal/`
- [ ] Schema CSV specifico creato e registrato nel registry
- [ ] Import dello schema in `app/exports/csv/__init__.py`
- [ ] `get_queryset()` implementato con i filtri corretti
- [ ] View specifica creata (estende `BaseExportRequestView` con `export_type`)
- [ ] URL e permessi configurati
- [ ] Test scritti (richiesta 202, 403, 401)
- [ ] Chiamata HTTP a uploads mockata nei test
- [ ] Tutti i test PASSANO
- [ ] Campo `managed: true` nel JSON
