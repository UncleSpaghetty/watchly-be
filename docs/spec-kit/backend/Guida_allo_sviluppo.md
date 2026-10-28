# Guida allo Sviluppo Endpoint Backend — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare endpoint API CRUD completi, testati e validati. Il flusso è sequenziale, bloccante e iterativo: ogni endpoint deve essere completato prima di passare al successivo.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **File JSON API** — File JSON fornito dall'utente al momento del lancio del prompt, contenente la lista completa degli endpoint da implementare con tutte le specifiche (ruoli, filtri, schema, custom logic, side effects, ecc.). Il nome del file può variare (es. `api_v1.json`, `api_leads.json`, ecc.): l'agent deve identificarlo dal contesto del prompt.
2. **`DEVELOPMENT_STANDARDS.md`** — Standard tecnici per Model, Schema, View, URLs, Permessi
3. **`TEST_STANDARDS.md`** — Standard tecnici per la struttura e l'esecuzione dei test
4. **`FILE_MANAGEMENT_STANDARDS.md`** — Standard per la gestione dei file (upload, download, presigned URL) tramite il microservizio uploads

L'agent DEVE leggere e rispettare integralmente i documenti `DEVELOPMENT_STANDARDS.md`, `TEST_STANDARDS.md` e `FILE_MANAGEMENT_STANDARDS.md` per ogni aspetto implementativo.

---

## Struttura del JSON API

Ogni oggetto nel file JSON rappresenta un singolo metodo HTTP su un endpoint. I campi rilevanti sono:

| Campo | Significato |
| --- | --- |
| `endpoint` | URL dell'endpoint |
| `method` | Metodo HTTP (GET, POST, PUT, DELETE) |
| `entity` | Entità di dominio |
| `domain` | Dominio logico (usato come sotto-directory in schemas/ e views/) |
| `roles` | Ruoli autorizzati ad accedere |
| `filters` | Filtri da implementare nella list view |
| `custom_logic` | Logica custom da implementare nel metodo |
| `side_effects` | Effetti collaterali (creazione record collegati, aggiornamento status, ecc.) |
| `view_name` | Nome della classe view |
| `view_class` | Tipo di view (ListView, DetailView, BaseView) |
| `schema_read` | Nome dello schema di lettura |
| `schema_write` | Nome dello schema di scrittura |
| `soft_delete_filter` | Se filtrare i record soft-deleted |
| `pagination` | Se abilitare la paginazione |
| `sort_default` | Ordinamento di default |
| `implemented` | Se l'endpoint è già implementato |
| `managed` | Se l'endpoint è stato implementato e testato dall'agent (aggiunto dall'agent) |
| `notes` / `dev_notes` | Note aggiuntive per lo sviluppo |

---

## Flusso di Sviluppo per Singolo Endpoint

Per OGNI endpoint nel JSON con `implemented: false` e senza `managed: true`, eseguire i seguenti step in ordine:

### Step 1 — Schema

Creare uno schema dedicato per ogni metodo dell'endpoint. Ogni schema deve essere il più completo possibile, esponendo tutti i campi dell'entità **tranne quelli sensibili** (password, secret, token), salvo diversa indicazione esplicita nelle `notes`.

- `schema_read` → schema di output con tutti i campi `dump_only=True`
- `schema_write` → schema di input con validazioni appropriate
- Se il JSON specifica schema diversi per metodi diversi (es. `LeadReadSchema` vs `LeadDetailReadSchema`), creare schema separati
- Seguire le convenzioni di `DEVELOPMENT_STANDARDS.md` sezione 4 (Schema)

### Step 2 — View

Implementare la view seguendo **esattamente** le specifiche del JSON:

- **Nome classe**: usare il `view_name` indicato nel JSON
- **Tipo view**: usare la `view_class` indicata (ListView, DetailView, BaseView)
- **Ruoli**: configurare in `permissions.py` i ruoli esatti dal campo `roles`
- **Filtri**: implementare tutti i filtri dal campo `filters` con i lookup indicati
- **Custom logic**: implementare tutta la logica dal campo `custom_logic`
- **Side effects**: implementare tutti gli effetti collaterali dal campo `side_effects`
- **URL**: registrare l'endpoint con il path esatto dal campo `endpoint` — vedi regola critica qui sotto
- **Soft delete**: se `soft_delete_filter: true`, filtrare i record con `deleted_at=None` in `get_query()`
- **Paginazione**: se `pagination: true`, la ListView la gestisce di default
- **Ordinamento**: impostare `sort_default` dal campo `sort_default`
- Seguire le convenzioni di `DEVELOPMENT_STANDARDS.md` sezione 5 (View)

#### Regola critica — Coerenza URL endpoint

> Il path registrato in `urls.py` deve corrispondere **esattamente** all'URL nel campo `endpoint` del JSON (escluso il prefisso `/api/<service>` già coperto dal blueprint). L'agent NON deve mai modificare, abbreviare o ristrutturare il path.
>
> **Esempio corretto:** se il JSON specifica `"endpoint": "/api/crm/sources/@minimal"`, il path registrato deve essere `/sources/@minimal`. Il nome dell'endpoint `as_view("...")` deve essere descrittivo (es. `"source_minimal_list"`).
>
> **Esempio errato:** registrare `/sources/` omettendo `/@minimal` è un errore — l'endpoint risultante sarebbe `/api/crm/sources/` invece di `/api/crm/sources/@minimal`.
>
> Questa regola vale per **ogni segmento** del path: azioni custom (`/archive/`), suffissi semantici (`/@minimal`), prefisso interno (`/internal/`), sotto-risorse (`/resources/<id>/items/`). Nessun segmento può essere omesso o alterato.

### Step 3 — Test

Creare test automatizzati per ogni casistica dell'endpoint:

- **Casi di successo**: operazione completata correttamente
- **Casi di errore**: 400 (input invalido), 401 (non autenticato), 403 (ruolo non autorizzato), 404 (non trovato), 409 (conflitti/duplicati)
- **Edge cases**: filtri, paginazione, ordinamento, soft delete, custom logic, side effects
- **Permessi**: verificare che ogni ruolo abbia accesso corretto e che i ruoli non autorizzati ricevano 403
- Seguire le convenzioni di `TEST_STANDARDS.md` sezione 8 (Pattern per i test API)

### Step 4 — Esecuzione e Iterazione

Eseguire i test:

```
make test  # selezionare il microservizio corretto
```

Se i test **falliscono**:
→ Analizzare l'errore, correggere il codice, rieseguire i test.
→ Ripetere fino a che TUTTI i test passano.

**Il flusso NON può proseguire al prossimo endpoint finché tutti i test non passano.**

### Step 5 — Marcatura Completamento

Quando tutti i test passano con successo, aggiornare il file JSON fornito aggiungendo `"managed": true` nell'oggetto dell'endpoint appena completato.

---

## Regole sugli Import

### Posizione degli import

Tutti gli import devono essere **dichiarati in cima al file**, raggruppati per categoria secondo l'ordine definito in `DEVELOPMENT_STANDARDS.md` sezione 3.2.

L'unica eccezione ammessa è l'import **all'interno di una funzione o metodo** quando è strettamente necessario per evitare **import circolari**. In questo caso l'import locale deve essere accompagnato da un commento esplicativo:

```python
def some_method(self):
    # Import locale per evitare import circolare con app.models.resource
    from app.models.resource import Resource
    ...
```

### Rimozione import non utilizzati

Prima di concludere la scrittura di qualsiasi file, l'agent **DEVE verificare** che tutti gli import dichiarati siano effettivamente utilizzati nel codice. Gli import non utilizzati vanno rimossi.

Controllo obbligatorio:
- Ogni `import X` o `from X import Y` deve essere referenziato almeno una volta nel corpo del file
- Gli import condizionali (dentro `if`, `try/except`) contano come utilizzati
- Gli import nei `__init__.py` per re-export sono sempre validi

---

## Condizioni di BLOCCO

Il flusso NON può passare all'endpoint successivo se:

- Un test fallisce
- Mancano test per casistiche note (permessi, filtri, edge cases)
- La custom_logic o i side_effects non sono implementati
- I ruoli non corrispondono a quelli specificati nel JSON
- Il path registrato in `urls.py` non corrisponde esattamente al campo `endpoint` del JSON

---

## Raggruppamento Endpoint

Endpoint che condividono la stessa `view_name` (es. GET e POST su `SourceListCreateView`) appartengono alla stessa view. Implementarli insieme nella stessa classe, poi testare tutti i metodi della view prima di procedere.

---

## Ordine di Implementazione

Seguire l'ordine degli endpoint nel JSON (`id` crescente). Se un'entità ha dipendenze (es. Lead dipende da Source), implementare prima le dipendenze.

---

## Checklist per Endpoint Completato

- [ ] Schema creati (read + write per ogni metodo)
- [ ] View implementata con ruoli, filtri, custom logic, side effects
- [ ] Permessi configurati in `permissions.py`
- [ ] URL registrata in `urls.py`
- [ ] Campi file gestiti con `UploadsInternalClient` (se presenti, vedi `FILE_MANAGEMENT_STANDARDS.md`)
- [ ] Test scritti per tutti gli scenari
- [ ] Tutti i test PASSANO
- [ ] Campo `managed: true` aggiunto nel JSON
- [ ] Tutti i file hanno import in cima, senza import inutilizzati

---

## Placeholder per Endpoint con Logica Non Ancora Implementata

Quando un endpoint richiede logiche che non sono ancora disponibili (generazione CSV, generazione PDF, caricamento file), l'agent **DEVE** implementare un placeholder funzionante che:

1. Risponde con lo stesso status code e struttura che avrà la versione definitiva
2. Restituisce dati mock coerenti con la realtà del dominio
3. Contiene un commento `# TODO: implementare logica reale` nel punto esatto da completare in seguito

Poiché queste funzionalità vengono utilizzate in più punti dell'applicazione, la logica placeholder **non va scritta direttamente nella view**. Va invece isolata in un file dedicato in `app/utils/`, e la view si limita a chiamare la funzione esposta da quel file. Questo garantisce che quando la logica reale sarà disponibile, basterà aggiornare un unico file.

### Generazione CSV

Creare `app/utils/csv_exporter.py`:

```python
# Built-in
import io
import csv

# Flask
from flask import Response


def generate_csv_response(headers: list, rows: list, filename: str = "export.csv") -> Response:
    # TODO: implementare generazione CSV reale con dati effettivi
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return Response(
        output.getvalue(),
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

Nella view:

```python
# Utils
from app.utils.csv_exporter import generate_csv_response


def get(self):
    mock_rows = [["00000000-0000-0000-0000-000000000001", "Example Row", "2026-01-01T00:00:00"]]
    return generate_csv_response(["id", "name", "created_at"], mock_rows, filename="resources.csv")
```

### Generazione PDF

Creare `app/utils/pdf_generator.py`:

```python
# Flask
from flask import Response


def generate_pdf_response(filename: str = "document.pdf") -> Response:
    # TODO: implementare generazione PDF reale
    placeholder_pdf = b"%PDF-1.4 mock placeholder"
    return Response(
        placeholder_pdf,
        status=200,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

Nella view:

```python
# Utils
from app.utils.pdf_generator import generate_pdf_response


def get(self):
    return generate_pdf_response(filename="report.pdf")
```

### Gestione File (upload, download, campi file)

Quando un endpoint deve gestire campi che rappresentano file (immagine profilo, documenti allegati, export CSV, ecc.), l'agent **NON deve usare placeholder** ma deve implementare il flusso completo seguendo `FILE_MANAGEMENT_STANDARDS.md`.

**L'agent DEVE:**

1. Leggere `FILE_MANAGEMENT_STANDARDS.md` per comprendere il flusso completo
2. Creare il client interno `app/services/internal/uploads.py` (classe `UploadsInternalClient`) se non già presente
3. Nel model, aggiungere i campi `<nome>_file_id` (UUID) e `<nome>_file_path` (String)
4. Nello schema di lettura, esporre l'URL firmato tramite `fields.Method()` che chiama `UploadsInternalClient().get_upload_info()`
5. Nello schema di scrittura, accettare l'UUID del file, validarlo con `@validates` e mapparlo ai campi model con `@post_load`
6. Se richiesto un endpoint di download dedicato, implementare il redirect alla presigned URL
7. Se richiesto un endpoint di presigned URL per upload frontend, implementarlo come `BaseView`
8. Nei test, mockare `UploadsInternalClient` con `unittest.mock.patch`

**Esempio rapido — Schema write con campo file:**

```python
# Services
from app.services.internal.uploads import UploadsInternalClient


class ResourceUpdateSchema(ModelSchema):
    profile_picture = fields.UUID(required=False, allow_none=True, load_only=True)
    profile_picture_file_id = fields.UUID(required=False, allow_none=True, load_only=True)
    profile_picture_file_path = fields.String(required=False, allow_none=True, load_only=True)

    @validates("profile_picture")
    def validate_profile_picture(self, value, **kwargs):
        if value is None:
            return value
        result = UploadsInternalClient().get_upload_info(str(value))
        if result is None:
            raise ValidationError("File not found or the uploads service is unavailable.")
        self.context["_pending_profile_picture_file_path"] = result.get("file_path")
        return value

    @post_load
    def map_file_fields(self, data, **kwargs):
        if "profile_picture" in data:
            file_id = data.pop("profile_picture")
            if file_id is not None:
                data["profile_picture_file_id"] = file_id
                data["profile_picture_file_path"] = self.context.pop("_pending_profile_picture_file_path", None)
            else:
                data["profile_picture_file_id"] = None
                data["profile_picture_file_path"] = None
        return data
```

**Esempio rapido — Schema read con campo file:**

```python
class ResourceReadSchema(ModelSchema):
    profile_picture = fields.Method("get_profile_picture_url", dump_only=True)

    def get_profile_picture_url(self, obj):
        file_id = obj.profile_picture_file_id if hasattr(obj, "profile_picture_file_id") else None
        if not file_id:
            return None
        try:
            client = UploadsInternalClient()
            upload_info = client.get_upload_info(str(file_id))
            return upload_info.get("url") if upload_info else None
        except Exception:
            return None
```

### Regole per i Placeholder

- La logica placeholder va **sempre** in `app/utils/`, mai inline nella view
- Un file utils per tipologia funzionale (es. `csv_exporter.py`, `pdf_generator.py`): se più endpoint generano CSV, usano tutti lo stesso file utils
- Il placeholder **deve passare i test**: i test per endpoint con placeholder devono verificare la struttura della response e lo status code attesi, non il contenuto reale
- Nei test, aggiungere un commento `# TODO: aggiornare test quando la logica reale sarà implementata`
- Il campo `managed: true` viene comunque aggiunto nel JSON: il placeholder è considerato implementazione valida in attesa della logica definitiva

**Nota:** la gestione file (upload, download) NON usa placeholder. Seguire `FILE_MANAGEMENT_STANDARDS.md` per l'implementazione completa.

---

## Comportamento Atteso dell'Agent AI

1. Identificare il file JSON API fornito nel prompt e leggerne il contenuto
2. Identificare il prossimo endpoint con `implemented: false` e senza `managed: true`
3. Leggere `DEVELOPMENT_STANDARDS.md` e `TEST_STANDARDS.md` per le convenzioni tecniche
4. Implementare schema → view → test seguendo il flusso descritto
5. Verificare che tutti i file scritti abbiano gli import in cima e senza import inutilizzati
6. Eseguire i test e iterare fino al successo
7. Marcare l'endpoint come `managed: true` nel file JSON fornito
8. Proseguire con l'endpoint successivo
9. Ripetere fino al completamento di tutti gli endpoint

Se un errore persiste dopo 3 iterazioni:
→ Segnalare il problema all'utente con dettagli sull'errore e attendere istruzioni.