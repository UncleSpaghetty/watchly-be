# Guida allo Sviluppo Gestione File — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare la gestione file (upload, download, campi file nei model) in un microservizio. Il file management non usa mai placeholder — va implementato completamente seguendo `file-management-spec-kit.md`.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **`input.json`** — File JSON contenente la lista delle funzionalità file da implementare
2. **`file-management-spec-kit.md`** — Standard completo per client, model, schema, view, test

---

## Struttura del JSON File Management

| Campo | Significato |
| --- | --- |
| `id` | Identificativo univoco |
| `entity` | Entità che gestisce il file |
| `domain` | Dominio logico |
| `microservice` | Microservizio di appartenenza |
| `field_name` | Nome logico del campo file (es. `profile_picture`, `document`) |
| `file_type` | Etichetta semantica in `UPPER_SNAKE_CASE` (es. `PROFILE_PICTURE`) |
| `is_public` | Se il file è pubblico (default: `false`) |
| `required` | Se il file è obbligatorio in creazione |
| `allowed_extensions` | Estensioni permesse (es. `[".jpg", ".png"]`) |
| `allowed_content_types` | MIME types permessi |
| `max_file_size_mb` | Dimensione massima in MB |
| `has_presigned_upload_endpoint` | Se esporre un endpoint dedicato per la presigned URL |
| `has_download_endpoint` | Se esporre un endpoint dedicato per il download |
| `upload_side` | `client` (frontend carica direttamente) o `server` (backend genera e carica) |
| `implemented` | `false` se da implementare |
| `notes` | Note aggiuntive |

---

## Prerequisiti

Prima di iniziare, l'agent DEVE verificare:

1. Che `app/services/internal/uploads.py` esista con la classe `UploadsInternalClient` — se non esiste, crearlo seguendo `file-management-spec-kit.md` sezione 3
2. Che `UPLOADS_INTERNAL_API_URL` e `INTERNAL_API_SECRET` siano nelle variabili d'ambiente e nella config Flask
3. Che `requests>=2.31` sia in `requirements.txt`

---

## Flusso di Sviluppo per Singolo Campo File

### Step 1 — Model

Aggiungere i campi `<nome>_file_id` e `<nome>_file_path` al model esistente (sezione 4 di `file-management-spec-kit.md`). Generare e applicare la migration.

### Step 2 — Schema di lettura

Aggiornare il `ReadSchema` per esporre l'URL di download tramite `fields.Method()` (sezione 5.1).

### Step 3 — Schema di scrittura

Aggiornare il `WriteSchema`/`UpdateSchema` per accettare l'UUID del file, validarlo con `@validates` e mapparlo ai campi tecnici con `@post_load` (sezione 5.2 e 5.3).

### Step 4 — View presigned URL (se `has_presigned_upload_endpoint: true`)

Creare una sottoclasse di `BasePresignedUploadView` con la configurazione specifica (sezione 6.1). Registrare l'URL e i permessi.

### Step 5 — View download (se `has_download_endpoint: true`)

Creare la view di download con redirect alla presigned URL (sezione 6.2). Registrare l'URL e i permessi.

### Step 6 — Upload lato server (se `upload_side: server`)

Implementare la funzione di upload nel modulo di competenza seguendo il pattern della sezione 6.3.

### Step 7 — Test

Scrivere test mockando `UploadsInternalClient` seguendo le fixture della sezione 8:
- Upload valido con file esistente
- Rimozione file (`null`)
- File ID non valido → `400`
- Servizio uploads irraggiungibile → `400`
- Download con redirect
- Download senza file allegato → `404`

### Step 8 — Esecuzione e Iterazione

```
make test
```

Se i test falliscono → analizzare, correggere, rieseguire.

### Step 9 — Marcatura

Aggiungere `"managed": true` nel JSON per il campo file completato.

---

## Condizioni di BLOCCO

- `UploadsInternalClient` non esiste o non è accessibile
- Il client viene istanziato fuori dal request context
- Lo schema espone `<nome>_file_id` invece dell'URL di download nel ReadSchema
- Il `@post_load` non mappa correttamente l'UUID ai campi tecnici
- I test non mockano `UploadsInternalClient`
- I test falliscono

---

## Checklist per Campo File Completato

- [ ] `UploadsInternalClient` presente in `app/services/internal/uploads.py`
- [ ] Campi `<nome>_file_id` e `<nome>_file_path` nel model
- [ ] Migration generata e applicata
- [ ] `ReadSchema` espone URL di download tramite `fields.Method()`
- [ ] `WriteSchema` accetta UUID, valida con `@validates`, mappa con `@post_load`
- [ ] View presigned URL (se necessaria) con configurazione estensioni, content types, dimensione
- [ ] View download (se necessaria) con redirect a presigned URL
- [ ] Test scritti con mock del client
- [ ] Tutti i test PASSANO
- [ ] Campo `managed: true` nel JSON
