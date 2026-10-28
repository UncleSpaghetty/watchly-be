# Guida allo Sviluppo Schema e API — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare endpoint API CRUD completi, testati e validati. Il flusso è sequenziale, bloccante e iterativo: ogni endpoint deve essere completato prima di passare al successivo.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **File JSON API** — File JSON fornito dall'utente al momento del lancio del prompt, contenente la lista completa degli endpoint da implementare con tutte le specifiche (ruoli, filtri, schema, custom logic, side effects, ecc.). Il nome del file può variare (es. `api_v1.json`, `api_leads.json`, ecc.): l'agent deve identificarlo dal contesto del prompt.
2. **`schema-api-spec-kit.md`** — Standard tecnici per Schema, View, URLs, Permessi
3. **`../test/test-spec-kit.md`** — Standard tecnici per la struttura e l'esecuzione dei test
4. **`../file-management/file-management-spec-kit.md`** — Standard per la gestione dei file (upload, download, presigned URL) tramite il microservizio uploads

L'agent DEVE leggere e rispettare integralmente questi documenti per ogni aspetto implementativo.

---

## Struttura del JSON API

Ogni oggetto nel file JSON rappresenta un singolo metodo HTTP su un endpoint. I campi rilevanti sono:

| Campo | Significato |
| --- | --- |
| `endpoint` | URL dell'endpoint (path completo incluso il prefisso `/api/<service>`) |
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
- Se il JSON specifica schema diversi per metodi diversi, creare schema separati
- Seguire le convenzioni di `schema-api-spec-kit.md` sezione 3 (Schema)

### Step 2 — View

Implementare la view seguendo **esattamente** le specifiche del JSON:

- **Nome classe**: usare il `view_name` indicato nel JSON
- **Tipo view**: usare la `view_class` indicata (ListView, DetailView, BaseView)
- **Ruoli**: configurare in `permissions.py` i ruoli esatti dal campo `roles`
- **Filtri**: implementare tutti i filtri dal campo `filters` con i lookup indicati
- **Custom logic**: implementare tutta la logica dal campo `custom_logic`
- **Side effects**: implementare tutti gli effetti collaterali dal campo `side_effects`
- **Soft delete**: se `soft_delete_filter: true`, filtrare i record con `deleted_at=None` in `get_query()`
- **Paginazione**: se `pagination: true`, la ListView la gestisce di default
- **Ordinamento**: impostare `sort_default` dal campo `sort_default`
- Seguire le convenzioni di `schema-api-spec-kit.md` sezioni 4 e 5 (View e URLs)

#### Regola critica — Coerenza URL endpoint

> Il path registrato in `urls.py` deve corrispondere **esattamente** all'URL nel campo `endpoint` del JSON (escluso il prefisso `/api/<service>` già coperto dal blueprint). L'agent NON deve mai modificare, abbreviare o ristrutturare il path.
>
> **Esempio corretto:** se il JSON specifica `"endpoint": "/api/crm/sources/@minimal"`, il path registrato deve essere `/sources/@minimal`. Il nome dell'endpoint `as_view("...")` deve essere descrittivo (es. `"source_minimal_list"`).
>
> **Esempio errato:** registrare `/sources/` omettendo `/@minimal` è un errore — l'endpoint risultante sarebbe `/api/crm/sources/` invece di `/api/crm/sources/@minimal`.
>
> Questa regola vale per **ogni segmento** del path: azioni custom (`/archive/`), suffissi semantici (`/@minimal`), prefisso interno (`/internal/`), sotto-risorse (`/resources/<id>/items/`). Nessun segmento può essere omesso.

- **URL**: registrare l'endpoint con il path esatto derivato dal campo `endpoint`

### Step 3 — Permessi

Aggiornare `app/config/permissions.py`:
- Aggiungere la entry con il nome dell'endpoint (identico a quello passato a `as_view("...")`)
- Configurare i metodi HTTP con i ruoli esatti dal campo `roles` del JSON

### Step 4 — Test

Creare test automatizzati per ogni casistica dell'endpoint:

- **Casi di successo**: operazione completata correttamente
- **Casi di errore**: 400 (input invalido), 401 (non autenticato), 403 (ruolo non autorizzato), 404 (non trovato), 409 (conflitti/duplicati)
- **Edge cases**: filtri, paginazione, ordinamento, soft delete, custom logic, side effects
- **Permessi**: verificare che ogni ruolo abbia accesso corretto e che i ruoli non autorizzati ricevano 403
- Seguire le convenzioni di `../test/test-spec-kit.md`

### Step 5 — Esecuzione e Iterazione

```
make test  # selezionare il microservizio corretto
```

Se i test **falliscono**:
→ Analizzare l'errore, correggere il codice, rieseguire i test.
→ Ripetere fino a che TUTTI i test passano.

**Il flusso NON può proseguire al prossimo endpoint finché tutti i test non passano.**

### Step 6 — Marcatura Completamento

Quando tutti i test passano, aggiornare il file JSON aggiungendo `"managed": true` nell'oggetto dell'endpoint appena completato.

### Step 7 — Vendor Client (solo per endpoint InternalView)

Se l'endpoint implementato è un `InternalView`:

1. Verificare se esiste già `app/vendors/internal/` nel microservizio
2. Se non esiste, creare la cartella con `__init__.py`
3. Creare o aggiornare `app/vendors/internal/{service}.py` aggiungendo il metodo corrispondente al nuovo endpoint
4. Il file deve includere l'header con istruzioni per la copia (config richieste, env vars)
5. Seguire il pattern documentato in `schema-api-spec-kit.md` sezione 9 (Vendors)

---

## Regole sugli Import

### Posizione degli import

Tutti gli import devono essere **dichiarati in cima al file**, raggruppati per categoria secondo l'ordine definito in `schema-api-spec-kit.md`.

L'unica eccezione ammessa è l'import **all'interno di una funzione o metodo** per evitare **import circolari**, accompagnato da un commento esplicativo:

```python
def some_method(self):
    # Import locale per evitare import circolare con app.models.resource
    from app.models.resource import Resource
    ...
```

### Rimozione import non utilizzati

Prima di concludere qualsiasi file, l'agent **DEVE verificare** che tutti gli import dichiarati siano effettivamente utilizzati. Gli import non utilizzati vanno rimossi.

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

Endpoint che condividono la stessa `view_name` (es. GET e POST su `SourceListCreateView`) appartengono alla stessa view. Implementarli insieme nella stessa classe, poi testare tutti i metodi prima di procedere.

---

## Ordine di Implementazione

Seguire l'ordine degli endpoint nel JSON (`id` crescente). Se un'entità ha dipendenze (es. Lead dipende da Source), implementare prima le dipendenze.

---

## Placeholder per Endpoint con Logica Non Ancora Implementata

Quando un endpoint richiede logiche non ancora disponibili (generazione CSV, generazione PDF, caricamento file), implementare un **placeholder funzionante** che:

1. Risponde con lo stesso status code e struttura della versione definitiva
2. Restituisce dati mock coerenti con il dominio
3. Contiene un commento `# TODO: implementare logica reale` nel punto esatto

La logica placeholder va **sempre** in `app/utils/`, mai inline nella view. Questo garantisce che basterà aggiornare un unico file quando la logica reale sarà disponibile.

### Generazione CSV (placeholder)

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

### Generazione PDF (placeholder)

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

### Regole per i Placeholder

- Un file utils per tipologia funzionale: se più endpoint generano CSV, usano tutti lo stesso file
- Il placeholder **deve passare i test**: i test verificano struttura della response e status code, non il contenuto reale
- Nei test aggiungere un commento `# TODO: aggiornare test quando la logica reale sarà implementata`
- Il campo `managed: true` viene comunque aggiunto: il placeholder è implementazione valida
- La gestione file (upload, download) NON usa placeholder — seguire `file-management-spec-kit.md`

---

## Checklist per Endpoint Completato

- [ ] Schema creati (read + write per ogni metodo)
- [ ] View implementata con ruoli, filtri, custom logic, side effects
- [ ] Permessi configurati in `permissions.py` con nome endpoint identico a `as_view("...")`
- [ ] URL registrata in `urls.py` con path identico al campo `endpoint` del JSON
- [ ] Campi file gestiti con `UploadsInternalClient` (se presenti)
- [ ] Vendor client aggiornato in `app/vendors/internal/` (se endpoint `InternalView`)
- [ ] Test scritti per tutti gli scenari
- [ ] Tutti i test PASSANO
- [ ] Campo `managed: true` aggiunto nel JSON
- [ ] Tutti i file hanno import in cima, senza import inutilizzati
