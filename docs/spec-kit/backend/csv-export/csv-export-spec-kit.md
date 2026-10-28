# Guida pratica: Export CSV asincroni nei microservizi

## Obiettivo

Questa guida definisce lo standard completo per implementare export CSV asincroni in un microservizio Python/Flask con dFlango, coprendo l'intero flusso: **Schema CSV → View → API interna uploads → Pub/Sub → Worker → Storage GCS → Notifica**.

---

## Riepilogo convenzioni

| Aspetto | Convenzione |
| --- | --- |
| **Nessun CSV nella request** | La view delega al servizio `uploads` tramite HTTP interno; mai generare il CSV nella request HTTP |
| **Messaggio Pub/Sub** | Piccolo: contiene solo `export_download_id` e `export_type`; pubblicato da `uploads` |
| **Schema CSV** | Una classe schema per ogni tipo di export (`CSVExportSchema`), con `fields`, `get_queryset`, `batch_size` |
| **Model ExportDownload** | Centralizzato nel microservizio `uploads` con stati: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED` |
| **Storage** | Object storage (GCS/MinIO) tramite microservizio `uploads` con presigned URL |
| **Notifica** | Email al termine della generazione tramite topic `notifications` |
| **CSV Injection** | Tutti i valori CSV sanitizzati con `sanitize_csv_value` (OWASP) |

---

## Architettura cross-service

Il flusso di export coinvolge tre ruoli:

1. **Microservizio richiedente** (es. `auth`, `crm`): espone l'endpoint `POST /<entity>/@export/`, valida filtri e permessi, delega la creazione del record `ExportDownload` al servizio `uploads` tramite API HTTP interna.
2. **Microservizio `uploads`**: possiede il model `ExportDownload`, crea il record, pubblica su Pub/Sub, espone gli endpoint di lista e download.
3. **Worker CSV**: processo in-process nel microservizio che possiede i dati (es. `auth`), consuma da Pub/Sub, genera il CSV, carica su GCS tramite uploads.

```text
[auth/crm]                          [uploads]                         [worker in auth]
POST /<entity>/@export/  ──HTTP──▶  POST /internal/export-downloads/
                                    ├─ crea ExportDownload (QUEUED)
                                    └─ pubblica su csv-export topic
                                                                    ◀── consuma da csv-export-sub
                                                                        ├─ GET /internal/export-downloads/<id>/
                                                                        ├─ PUT (status=RUNNING)
                                                                        ├─ genera CSV locale
                                                                        ├─ POST /internal/presigned-url/
                                                                        ├─ PUT/POST file su GCS
                                                                        ├─ POST /internal/<upload_id>/ (conferma)
                                                                        ├─ PUT (status=COMPLETED, upload_id)
                                                                        └─ pubblica notifica email
```

---

## 1) Principi architetturali

### 1.1 Nessun CSV generato nella request HTTP

La request HTTP non deve mai generare direttamente il file CSV.

La view deve:
1. Validare input, filtri e permessi
2. Chiamare l'API interna di `uploads` per creare un record `ExportDownload` in stato `QUEUED` e pubblicare su Pub/Sub
3. Restituire una risposta immediata al client con i dati ricevuti da `uploads`

Se la chiamata HTTP a `uploads` fallisce, l'API restituisce errore. In questo caso l'utente dovrà richiedere nuovamente il download.

### 1.2 Il messaggio Pub/Sub deve essere piccolo

```json
{
  "event_type": "csv_export_requested",
  "export_download_id": "uuid",
  "export_type": "orders_csv"
}
```

Il messaggio è pubblicato dal servizio `uploads` (non dal microservizio richiedente). Tutti i dettagli persistenti stanno nel database di `uploads`, nel record `ExportDownload`.

### 1.3 Ogni export ha uno schema dedicato

```python
class OrdersCSVExportSchema(CSVExportSchema):
    export_type = "orders_csv"
    filename_prefix = "orders"
    batch_size = 2000

    fields = [
        CSVField("id", "ID ordine"),
        CSVField("created_at", "Data creazione", formatter=format_datetime),
        CSVField("customer_email", "Email cliente", getter=lambda obj: obj.customer.email),
    ]

    def get_queryset(self, context: ExportContext):
        return Order.query.filter_by(deleted_at=None).order_by(Order.id)
```

---

## 2) Model dati

Il model `ExportDownload` è **centralizzato nel microservizio `uploads`**. I microservizi richiedenti (auth, crm) non possiedono una copia locale di questo model — interagiscono con esso esclusivamente tramite API HTTP interne.

### 2.1 Tabella `export_download` (in uploads)

```python
# app/models/export_download.py  (nel microservizio uploads)

# Built-in
import uuid

# dFlango
from dflango.db import db

# Third-party
from sqlalchemy.dialects.postgresql import UUID

# Constants
from app.constants.export_status import ExportStatus


class ExportDownload(db.Model):
    __tablename__ = "export_download"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    export_type = db.Column(db.String(100), nullable=False, index=True)
    status = db.Column(db.Enum(ExportStatus), nullable=False, default=ExportStatus.QUEUED, index=True)

    requested_by_user_id = db.Column(UUID(as_uuid=True), nullable=False, index=True)

    filters_json = db.Column(db.JSON, nullable=True)
    filename = db.Column(db.String(255), nullable=True)

    total_rows = db.Column(db.Integer, nullable=True)
    processed_rows = db.Column(db.Integer, nullable=False, default=0)

    file_path = db.Column(db.String(500), nullable=True)
    file_size_bytes = db.Column(db.Integer, nullable=True)
    content_type = db.Column(db.String(100), nullable=False, default="text/csv")
    upload_id = db.Column(UUID(as_uuid=True), nullable=True)

    error_code = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    failed_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    def __repr__(self):
        return f"<ExportDownload {self.id} {self.export_type} {self.status.value}>"
```

### 2.2 Enum stati

```python
# app/constants/export_status.py

# dFlango
from dflango.enum import Enum


class ExportStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

---

## 3) Contratto API

### 3.1 Richiesta export (sul microservizio richiedente)

Ogni entità esportabile espone un endpoint dedicato sul proprio microservizio:

```http
POST /api/<service>/<entity>/@export/
```

Esempi:
- `POST /api/auth/users/@export/` — Export utenti
- `POST /api/crm/sources/@export/` — Export sorgenti
- `POST /api/crm/leads/@export/` — Export lead
- `POST /api/crm/appointments/@export/` — Export appuntamenti

I filtri vengono passati come **query parameters** (stesso formato usato dalle tabelle/liste), non nel body della richiesta:

```http
POST /api/auth/users/@export/?created_at__gte=2026-01-01&created_at__lte=2026-01-31
```

Il body della richiesta è vuoto (o assente). I parametri riservati per paginazione e ordinamento (`page`, `per_page`, `sort`, `sort_field`, `sort_order`) vengono ignorati dalla view.

Risposta `202`:
```json
{
  "id": "export-download-uuid",
  "export_type": "users_csv",
  "status": "QUEUED"
}
```

Internamente, la view chiama `POST /internal/export-downloads/` sul microservizio `uploads`, che crea il record e pubblica su Pub/Sub.

### 3.2 Lista download (sul microservizio uploads)

```http
GET /api/uploads/export-downloads/
```

Filtri: `export_type` (exact), `status` (exact), `created_at` (gte, lte).

La lista è filtrata per `requested_by_user_id` dell'utente corrente.

### 3.3 Download file (sul microservizio uploads)

```http
GET /api/uploads/export-downloads/<uuid:export_download_id>/download/
```

Restituisce una presigned URL temporanea (1 ora) per il download del file da GCS. Verifica che l'export sia in stato `COMPLETED` e che l'utente sia il richiedente.

### 3.4 API interne uploads (protette da X-Internal-Token)

```http
POST /internal/export-downloads/                   — Crea ExportDownload + pubblica Pub/Sub
GET  /internal/export-downloads/<uuid>/             — Legge dettagli export
PUT  /internal/export-downloads/<uuid>/             — Aggiorna campi export
POST /internal/presigned-url/                       — Richiede presigned URL per upload GCS
POST /internal/<uuid:file_id>/                      — Conferma upload completato
```

---

## 4) Schema CSV standard

### 4.1 Field descriptor (`app/exports/csv/fields.py`)

```python
# Built-in
from dataclasses import dataclass
from typing import Any, Callable


DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_value(value: str) -> str:
    """Protezione OWASP contro CSV injection."""
    if value is None:
        return ""
    value = str(value)
    if value.startswith(DANGEROUS_CSV_PREFIXES):
        return "'" + value
    return value


@dataclass(frozen=True)
class CSVField:
    key: str
    header: str
    getter: Callable[[Any], Any] | None = None
    formatter: Callable[[Any], str] | None = None
    default: str = ""

    def get_value(self, obj: Any) -> str:
        if self.getter:
            raw_value = self.getter(obj)
        else:
            raw_value = getattr(obj, self.key, None)
        if raw_value is None:
            return self.default
        if self.formatter:
            return self.formatter(raw_value)
        return str(raw_value)


def format_datetime(value):
    if not value:
        return ""
    return value.isoformat()


def format_date(value):
    if not value:
        return ""
    return value.isoformat()


def format_decimal(value):
    if value is None:
        return ""
    return str(value)


def format_bool(value):
    if value is None:
        return ""
    return "true" if value else "false"
```

### 4.2 ExportContext e base schema (`app/exports/csv/schemas.py`)

```python
# Built-in
from datetime import datetime, timezone

# Exports
from app.exports.csv.fields import sanitize_csv_value


class ExportContext:
    """Contesto passato allo schema CSV per filtraggio e permessi."""

    def __init__(self, filters: dict = None, user: dict = None, requested_at: datetime = None):
        self.filters = filters or {}
        self.user = user
        self.requested_at = requested_at or datetime.now(timezone.utc)


class CSVExportSchema:
    export_type: str
    filename_prefix: str
    fields: list
    batch_size: int = 2000
    delimiter: str = ","
    encoding: str = "utf-8"
    include_bom: bool = False

    def validate_filters(self, filters: dict) -> dict:
        return filters

    def check_permissions(self, context: ExportContext) -> None:
        pass

    def get_queryset(self, context: ExportContext):
        raise NotImplementedError

    def get_filename(self, context: ExportContext) -> str:
        timestamp = context.requested_at.strftime("%Y%m%d_%H%M%S")
        return f"{self.filename_prefix}_{timestamp}.csv"

    def get_headers(self) -> list[str]:
        return [field.header for field in self.fields]

    def serialize_row(self, obj) -> list[str]:
        return [sanitize_csv_value(field.get_value(obj)) for field in self.fields]
```

### 4.3 Registry (`app/exports/csv/registry.py`)

```python
class CSVExportRegistry:
    _schemas: dict[str, type] = {}

    @classmethod
    def register(cls, schema_cls):
        cls._schemas[schema_cls.export_type] = schema_cls
        return schema_cls

    @classmethod
    def get(cls, export_type: str):
        schema_cls = cls._schemas.get(export_type)
        if not schema_cls:
            raise ValueError(f"Unknown export type: {export_type}")
        return schema_cls()
```

---

## 5) View Flask

### 5.1 Base view — `BaseExportRequestView` di dFlango

La view di richiesta export è fornita da dFlango (`from dflango.views import BaseExportRequestView`). Non crea il record `ExportDownload` localmente e non pubblica su Pub/Sub. Delega entrambe le operazioni al microservizio `uploads` tramite API HTTP interna.

La `BaseExportRequestView` di dFlango gestisce automaticamente:
- Validazione dell'`export_type` tramite `CSVExportRegistry`
- Parsing e validazione dei filtri dalla query string (escludendo parametri di paginazione/ordinamento)
- Verifica permessi tramite `ExportContext` e lo schema
- Chiamata al client HTTP per creare l'export

Ogni microservizio deve creare un proprio `BaseExportRequestView` locale che estende quello di dFlango, configurando il client HTTP per il microservizio `uploads`:

```python
# app/views/export/base_export_request.py

# Built-in
import logging

# Flask
from flask import jsonify

# dFlango
from dflango.views import BaseExportRequestView as DflangoBaseExportRequestView

# Constants
from app.constants.error_codes import ErrorCodes

# Services
from app.services.internal.export_downloads import ExportDownloadsInternalClient


class BaseExportRequestView(DflangoBaseExportRequestView):

    def get_export_client(self):
        return ExportDownloadsInternalClient()

    def create_export(self, client, export_type, user, filters):
        return client.create_export_download(
            export_type=export_type,
            user_id=str(user["id"]),
            filters=filters,
        )

    def handle_export_error(self, error):
        logging.error(f"Error creating export download: {error}")
        return jsonify({"error": ErrorCodes.INTERNAL_ERROR.value}), 500

    def get_success_response(self, result):
        return jsonify(result), 202
```

| Metodo hook | Scopo | Obbligo |
| --- | --- | --- |
| `get_export_client()` | Ritorna l'istanza del client HTTP per uploads | **Obbligatorio** |
| `create_export()` | Chiama il client per creare il record ExportDownload | **Obbligatorio** |
| `handle_export_error()` | Gestisce errori durante la creazione dell'export | Opzionale (default: 500 generico) |
| `get_success_response()` | Formatta la risposta di successo | Opzionale (default: 201) |

### 5.2 View specifica per entità

Ogni entità ha una view dedicata che estende il `BaseExportRequestView` locale impostando solo `export_type`:

```python
# app/views/export/user_export.py

from app.views.export.base_export_request import BaseExportRequestView

class UserExportView(BaseExportRequestView):
    export_type = "users_csv"
```

Questa view viene registrata in `urls.py` con un endpoint specifico (es. `/users/@export/`) e mappata in `permissions.py` con il nome dell'endpoint.

### 5.3 Client HTTP per uploads (`app/services/internal/export_downloads.py`)

```python
# Built-in
import logging

# Third-party
import requests

# Config
from app.config import Config


def create_export_download(export_type: str, user_id: str, filters: dict) -> dict:
    """
    Crea un ExportDownload e pubblica su PubSub tramite il servizio uploads.
    """
    headers = {"X-Internal-Token": Config.INTERNAL_API_SECRET}

    response = requests.post(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/export-downloads/",
        headers=headers,
        json={
            "export_type": export_type,
            "user_id": user_id,
            "filters": filters,
        },
        timeout=30,
    )
    response.raise_for_status()

    return response.json()


def get_export_download(export_download_id: str) -> dict:
    """
    Recupera i dettagli di un ExportDownload dal servizio uploads.
    """
    headers = {"X-Internal-Token": Config.INTERNAL_API_SECRET}

    response = requests.get(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/export-downloads/{export_download_id}/",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    return response.json()


def update_export_download(export_download_id: str, **fields) -> dict:
    """
    Aggiorna i campi di un ExportDownload nel servizio uploads.
    """
    headers = {"X-Internal-Token": Config.INTERNAL_API_SECRET}

    response = requests.put(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/export-downloads/{export_download_id}/",
        headers=headers,
        json=fields,
        timeout=30,
    )
    response.raise_for_status()

    return response.json()
```

> **Nota**: I microservizi che non hanno un worker (es. `crm`) implementano solo `create_export_download`. Le funzioni `get_export_download` e `update_export_download` servono solo al microservizio che esegue il worker (es. `auth`).

---

## 6) Flusso asincrono — Worker Pub/Sub

Il worker è un processo **in-process** nel microservizio che possiede i dati. In sviluppo, viene eseguito come processo background (`&`); in produzione, viene gestito da `supervisord` nello stesso container del web server.

Il worker consuma messaggi dalla subscription `csv-export-sub` e:

1. Legge il record `ExportDownload` dal servizio `uploads` tramite `GET /internal/export-downloads/<id>/`
2. Aggiorna lo stato a `RUNNING` tramite `PUT /internal/export-downloads/<id>/`
3. Istanzia lo schema tramite `CSVExportRegistry.get(export_type)`
4. Esegue la query a batch (`batch_size`) con keyset pagination
5. Scrive il file CSV temporaneo in locale (con `sanitize_csv_value`)
6. Carica su GCS tramite presigned URL dal servizio `uploads`:
   - `POST /internal/presigned-url/` per ottenere URL firmato
   - `PUT/POST` file su GCS
   - `POST /internal/<upload_id>/` per confermare upload
7. Aggiorna il record tramite `PUT`: stato `COMPLETED`, `filename`, `file_path`, `upload_id`, `total_rows`, `completed_at`
8. Pubblica notifica email tramite topic `notifications`
9. Elimina il file CSV locale

In caso di errore: aggiorna lo stato a `FAILED` con `error_message` e `failed_at`.

### 6.1 Storage — Upload CSV su GCS (`app/services/internal/uploads.py`)

```python
# Built-in
import logging
import os

# Third-party
import requests

# Config
from app.config import Config


def upload_csv_to_storage(file_path: str, filename: str, user_id: str) -> dict:
    """
    Carica un file CSV nel servizio uploads tramite API interna.

    Flusso:
    1. Richiede una presigned URL al servizio uploads
    2. Carica il file direttamente su GCS tramite la presigned URL
    3. Conferma il caricamento al servizio uploads

    Ritorna il dict con i dati dell'upload (id, file_path, ecc.)
    """
    headers = {"X-Internal-Token": Config.INTERNAL_API_SECRET}
    file_size = os.path.getsize(file_path)

    # Step 1: richiede presigned URL
    presigned_response = requests.post(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/presigned-url/",
        headers=headers,
        json={
            "user_id": user_id,
            "is_public": False,
            "file_type": "CSV_EXPORT",
            "files": [
                {
                    "file_name": filename,
                    "content_type": "text/csv",
                    "content_length": file_size,
                }
            ],
        },
        timeout=30,
    )
    presigned_response.raise_for_status()

    upload_data = presigned_response.json()["uploads"][0]
    upload_id = upload_data["id"]
    presigned_url = upload_data["presigned_url"]

    # Step 2: carica il file su GCS tramite la presigned URL
    upload_method = requests.post if "uploadType=media" in presigned_url else requests.put
    with open(file_path, "rb") as f:
        gcs_response = upload_method(
            presigned_url,
            data=f,
            headers={"Content-Type": "text/csv"},
            timeout=300,
        )
    gcs_response.raise_for_status()

    # Step 3: conferma il caricamento al servizio uploads
    confirm_response = requests.post(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/{upload_id}/",
        headers=headers,
        timeout=30,
    )
    confirm_response.raise_for_status()

    return upload_data
```

---

## 7) Pub/Sub — Pubblicazione (nel microservizio uploads)

La pubblicazione avviene nel microservizio `uploads`, quando riceve una richiesta HTTP interna di creazione export. Il microservizio richiedente (auth, crm) non pubblica direttamente su Pub/Sub.

```python
# app/services/pubsub/csv_export.py  (nel microservizio uploads)

# Built-in
import json
import logging

# Third-party
from google.cloud import pubsub_v1

# Config
from app.config import Config

# Services
from app.services.pubsub.common import get_publish_callback


def publish_csv_export_requested(export_download_id: str, export_type: str) -> None:
    payload = {
        "event_type": "csv_export_requested",
        "export_download_id": export_download_id,
        "export_type": export_type,
    }

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        Config.PUBSUB_PROJECT_ID,
        Config.PUBSUB_CSV_EXPORT_TOPIC,
    )

    message_data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, message_data)
    future.add_done_callback(get_publish_callback("csv_export_requested"))

    future.result(timeout=Config.CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS)
```

### 7.1 View interna di creazione (nel microservizio uploads)

```python
# app/views/export/internal_export_download_request.py  (nel microservizio uploads)

class InternalExportDownloadRequestView(InternalView):
    """
    POST /internal/export-downloads/
    Riceve richieste da auth/crm, crea il record ExportDownload e pubblica su Pub/Sub.
    """
    accepted_methods = ["POST"]

    def post(self):
        data = self.get_request_data()

        export_type = data.get("export_type")
        user_id = data.get("user_id")
        filters = data.get("filters", {})

        if not export_type or not user_id:
            return jsonify({"error": "export_type and user_id are required"}), 400

        export_download = ExportDownload(
            export_type=export_type,
            status=ExportStatus.QUEUED,
            requested_by_user_id=user_id,
            filters_json=filters,
            content_type="text/csv",
        )

        try:
            db.session.add(export_download)
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": ErrorCodes.STORAGE_INTERNAL_ERROR.value}), 500

        try:
            publish_csv_export_requested(
                export_download_id=str(export_download.id),
                export_type=export_type,
            )
        except Exception:
            export_download.status = ExportStatus.FAILED
            export_download.error_message = "Unable to publish CSV export request to Pub/Sub"
            export_download.failed_at = db.func.now()
            db.session.commit()
            return jsonify({"error": ErrorCodes.STORAGE_INTERNAL_ERROR.value}), 500

        return jsonify({
            "id": str(export_download.id),
            "export_type": export_type,
            "status": export_download.status.value,
        }), 202
```

---

## 8) Struttura file di progetto

### 8.1 Microservizio richiedente con worker (es. `auth`)

```text
apps/auth/
└── app/
    ├── exports/
    │   └── csv/
    │       ├── __init__.py            # Importa gli schema per registrarli
    │       ├── fields.py              # CSVField, sanitize_csv_value, formatters
    │       ├── schemas.py             # ExportContext, CSVExportSchema base
    │       ├── registry.py            # CSVExportRegistry
    │       ├── service.py             # Logica worker (handle_csv_export_requested)
    │       ├── storage.py             # generate_and_save_csv, iterate_queryset_by_pk
    │       └── <entity>_export.py     # Schema specifico (es. users_export.py)
    ├── services/
    │   ├── internal/
    │   │   ├── export_downloads.py    # Client HTTP: create/get/update ExportDownload su uploads
    │   │   └── uploads.py             # Client HTTP: presigned URL + upload GCS
    │   └── pubsub/
    │       ├── common.py              # get_publish_callback
    │       └── notifications.py       # send_export_ready_notification
    ├── views/
    │   └── export/
    │       ├── base_export_request.py # View base (delega a uploads)
    │       └── <entity>_export.py     # View specifica (imposta export_type)
    └── workers/
        └── csv_export_worker.py       # Entrypoint worker Pub/Sub
```

### 8.2 Microservizio richiedente senza worker (es. `crm`)

```text
apps/crm/
└── app/
    ├── exports/
    │   └── csv/
    │       ├── __init__.py            # Importa gli schema per registrarli
    │       ├── fields.py              # CSVField, sanitize_csv_value, formatters
    │       ├── schemas.py             # ExportContext, CSVExportSchema base
    │       ├── registry.py            # CSVExportRegistry
    │       └── <entity>_export.py     # Schema specifico (es. leads_export.py)
    ├── services/
    │   └── internal/
    │       └── export_downloads.py    # Client HTTP: solo create_export_download
    └── views/
        └── export/
            ├── base_export_request.py # View base (delega a uploads)
            └── <entity>_export.py     # View specifica (imposta export_type)
```

> **Nota**: `crm` non ha `workers/`, `pubsub/`, `service.py`, `storage.py`. Gli export CRM sono consumati dal worker di `auth`.

### 8.3 Microservizio `uploads` (centrale)

```text
apps/uploads/
└── app/
    ├── models/
    │   └── export_download.py         # Model ExportDownload (canonical)
    ├── constants/
    │   └── export_status.py           # ExportStatus enum
    ├── schemas/
    │   └── export_download.py         # ExportDownloadReadSchema
    ├── views/
    │   └── export/
    │       ├── internal_export_download_request.py  # POST interna: crea + pubblica Pub/Sub
    │       ├── internal_export_download_detail.py   # GET/PUT interna: legge/aggiorna
    │       ├── export_download_list.py              # GET pubblica: lista per utente
    │       └── export_download_file.py              # GET pubblica: presigned URL download
    └── services/
        └── pubsub/
            ├── common.py              # get_publish_callback
            └── csv_export.py          # publish_csv_export_requested
```
