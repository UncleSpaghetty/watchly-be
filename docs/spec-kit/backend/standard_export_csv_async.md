# Standard tecnico per Export CSV asincroni in Python/Flask

## 1. Obiettivo

Questo documento definisce uno standard riutilizzabile per implementare export CSV nei microservizi Python basati su Flask e dFlango, con pattern `model`, `schema`, `view`.

L'obiettivo è consentire a un agente AI o a uno sviluppatore di aggiungere un nuovo export CSV seguendo sempre la stessa architettura:

- richiesta asincrona da API HTTP;
- delega al microservizio `uploads` per la creazione del record e la pubblicazione del job su Pub/Sub;
- generazione CSV in background tramite worker dedicato;
- caricamento su Google Cloud Storage tramite presigned URL dal servizio `uploads`;
- aggiornamento del record `ExportDownload` nel servizio `uploads`;
- notifica email a fine generazione tramite topic `notifications`;
- download successivo da parte dell'utente tramite presigned URL da `uploads`.

## 2. Principi architetturali

### 2.1 Nessun CSV generato nella request HTTP

La request HTTP non deve mai generare direttamente il file CSV.

La view deve:

1. validare input, filtri e permessi;
2. chiamare l'API interna di `uploads` per creare un record `ExportDownload` in stato `QUEUED` e pubblicare su Pub/Sub;
3. restituire una risposta immediata al client con i dati ricevuti da `uploads`.

Se la chiamata HTTP a `uploads` fallisce, la chiamata API deve restituire errore. In questo caso l'utente dovrà richiedere nuovamente il download.

La generazione effettiva avviene sempre fuori dalla request HTTP, tramite un worker dedicato che consuma messaggi da una Pub/Sub pull subscription.

Non usare una Pub/Sub push subscription HTTP per generare direttamente CSV pesanti, perché un picco di messaggi potrebbe causare troppe generazioni concorrenti e sovraccaricare il backend principale.

### 2.2 Il messaggio Pub/Sub deve essere piccolo

Il messaggio Pub/Sub non deve contenere il dataset, né una query SQL serializzata.

Deve contenere solo dati minimi, ad esempio:

```json
{
  "event_type": "csv_export_requested",
  "export_download_id": "uuid",
  "export_type": "orders_csv"
}
```

Tutti i dettagli persistenti devono stare nel database, dentro il record `ExportDownload` o in tabelle correlate.

### 2.3 Ogni export deve avere uno schema dedicato

Ogni export CSV deve essere descritto da una classe schema, ad esempio:

```python
class OrdersCSVExportSchema(CSVExportSchema):
    export_type = "orders_csv"
    filename_prefix = "orders"
    batch_size = 2000

    fields = [
        CSVField("id", "ID ordine"),
        CSVField("created_at", "Data creazione", formatter=format_datetime),
        CSVField("customer_email", "Email cliente", getter=lambda obj: obj.customer.email),
        CSVField("total_amount", "Totale", formatter=format_decimal),
    ]

    def get_queryset(self, context: ExportContext):
        return (
            Order.query
            .filter_by(deleted_at=None)
            .filter(Order.id > context.last_pk if context.last_pk else True)
            .order_by(Order.id)
        )
```

Lo schema deve essere l'unico punto in cui sono definiti:

- colonne esportate;
- intestazioni CSV;
- formattazione valori;
- query di estrazione;
- batch size consigliata;
- naming del file;
- eventuali regole di autorizzazione specifiche.

## 3. Modello dati centralizzato

Il model `ExportDownload` è **centralizzato nel microservizio `uploads`**. I microservizi richiedenti (auth, crm) non possiedono una copia locale — interagiscono con esso tramite API HTTP interne.

### 3.1 Tabella `export_download` (in uploads)

Modello seguendo le convenzioni dFlango (`db.Model`, PK UUID, soft delete con `deleted_at`):

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

> **Nota**: il campo `upload_id` lega l'export al record `Upload` nel servizio uploads, usato per generare la presigned URL di download.

### 3.2 Enum stati standard

Definito in `app/constants/export_status.py` seguendo la convenzione dFlango con valori in **MAIUSCOLO**:

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

Regole:

- `QUEUED`: richiesta ricevuta, job non ancora iniziato;
- `RUNNING`: worker in esecuzione;
- `COMPLETED`: file generato e disponibile;
- `FAILED`: errore definitivo;
- `CANCELLED`: export annullato manualmente o da sistema.

### 3.3 Export model

Aggiornare `app/models/__init__.py`:

```python
from .export_download import ExportDownload
```

## 4. Contratto API lato Flask

### 4.1 Richiesta export (sul microservizio richiedente)

Ogni entità esportabile espone un endpoint dedicato sul proprio microservizio:

```http
POST /api/<service>/<entity>/@export/
```

Esempi:
- `POST /api/auth/users/@export/` — Export utenti
- `POST /api/crm/leads/@export/` — Export lead
- `POST /api/crm/sources/@export/` — Export sorgenti
- `POST /api/crm/appointments/@export/` — Export appuntamenti

I filtri vengono passati come **query parameters** (stesso formato usato dalle tabelle/liste), non nel body della richiesta:

```http
POST /api/auth/users/@export/?created_at__gte=2026-01-01&created_at__lte=2026-01-31&status=PAID
```

Il body della richiesta è vuoto (o assente). I parametri riservati per paginazione e ordinamento (`page`, `per_page`, `sort`, `sort_field`, `sort_order`) vengono ignorati dalla view.

Risposta:

```json
{
  "id": "export-download-uuid",
  "export_type": "users_csv",
  "status": "QUEUED"
}
```

Internamente, la view chiama `POST /internal/export-downloads/` sul microservizio `uploads`, che crea il record e pubblica su Pub/Sub.

### 4.2 Lista download dell'utente (sul microservizio uploads)

```http
GET /api/uploads/export-downloads/
```

Filtri disponibili (dichiarati in `allowed_filters`):

```python
allowed_filters = {
    "export_type": ["exact"],
    "status": ["exact"],
    "created_at": ["gte", "lte"],
}
```

La lista è filtrata per `requested_by_user_id` dell'utente corrente.

Risposta:

```json
{
  "results": [
    {
      "id": "uuid",
      "export_type": "orders_csv",
      "filename": "orders_20260101_100000.csv",
      "status": "COMPLETED",
      "total_rows": 10000,
      "processed_rows": 10000,
      "created_at": "2026-05-07T10:00:00",
      "completed_at": "2026-05-07T10:02:10"
    }
  ]
}
```

### 4.3 Download file (sul microservizio uploads)

Endpoint:

```http
GET /api/uploads/export-downloads/<uuid:export_download_id>/download/
```

Restituisce una presigned URL temporanea (1 ora) per il download da GCS. Verifica che l'export sia `COMPLETED`, che l'utente sia il richiedente e che l'`upload_id` sia valorizzato.

```json
{
  "download_url": "https://storage.googleapis.com/..."
}
```

### 4.4 API interne uploads (protette da X-Internal-Token)

```http
POST /internal/export-downloads/                   — Crea ExportDownload + pubblica Pub/Sub
GET  /internal/export-downloads/<uuid>/             — Legge dettagli export
PUT  /internal/export-downloads/<uuid>/             — Aggiorna campi export
POST /internal/presigned-url/                       — Richiede presigned URL per upload GCS
POST /internal/<uuid:file_id>/                      — Conferma upload completato
```

Queste API sono protette dal header `X-Internal-Token` verificato da `InternalView` (dFlango). Non richiedono autenticazione utente.

## 5. Schema CSV standard

### 5.1 Field descriptor

```python
# app/exports/csv/fields.py

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

### 5.2 ExportContext e base schema

```python
# app/exports/csv/schemas.py

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

### 5.3 Registry degli export

```python
# app/exports/csv/registry.py


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

Utilizzo:

```python
@CSVExportRegistry.register
class OrdersCSVExportSchema(CSVExportSchema):
    export_type = "orders_csv"
    filename_prefix = "orders"
    fields = [...]
```

## 6. Flusso asincrono completo

### 6.1 View Flask — `BaseExportRequestView` di dFlango

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

### 6.1.1 View specifica per entità

Ogni entità ha una view che estende il `BaseExportRequestView` locale impostando solo `export_type`:

```python
# app/views/export/user_export.py

from app.views.export.base_export_request import BaseExportRequestView

class UserExportView(BaseExportRequestView):
    export_type = "users_csv"
```

### 6.1.2 Client HTTP per uploads

```python
# app/services/internal/export_downloads.py

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

> **Nota**: I microservizi che non hanno un worker (es. `crm`) implementano solo `create_export_download`. Le funzioni `get_export_download` e `update_export_download` servono solo al microservizio che esegue il worker.

### 6.2 View lista download (nel microservizio uploads)

```python
# app/views/export/export_download_list.py  (nel microservizio uploads)

# dFlango
from dflango.views import ListView

# Models
from app.models.export_download import ExportDownload

# Schemas
from app.schemas.export.export_download_read import ExportDownloadReadSchema


class ExportDownloadListView(ListView):
    model = ExportDownload
    read_schema = ExportDownloadReadSchema
    accepted_methods = ["GET"]
    only_authenticated = True
    sort_default = "-created_at"

    allowed_filters = {
        "export_type": ["exact"],
        "status": ["exact"],
        "created_at": ["gte", "lte"],
    }

    def get_query(self):
        user = self.get_current_user()
        return ExportDownload.query.filter_by(
            requested_by_user_id=user["id"],
            deleted_at=None,
        )
```

### 6.3 Schema di lettura (nel microservizio uploads)

```python
# app/schemas/export_download.py  (nel microservizio uploads)

# dFlango
from dflango.schemas import ModelSchema, EnumField

# Third-party
from marshmallow import fields

# Models
from app.models.export_download import ExportDownload

# Constants
from app.constants.export_status import ExportStatus


class ExportDownloadReadSchema(ModelSchema):
    """Schema per la lettura di un export download."""

    id = fields.UUID(dump_only=True)
    export_type = fields.String(dump_only=True)
    status = EnumField(ExportStatus, dump_only=True)
    filename = fields.String(dump_only=True)
    total_rows = fields.Integer(dump_only=True)
    processed_rows = fields.Integer(dump_only=True)
    file_size_bytes = fields.Integer(dump_only=True)
    error_message = fields.String(dump_only=True)
    upload_id = fields.UUID(dump_only=True)
    started_at = fields.DateTime(dump_only=True)
    completed_at = fields.DateTime(dump_only=True)
    failed_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    class Meta:
        model = ExportDownload
```

### 6.4 Publish Pub/Sub (nel microservizio uploads)

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
```

```python
# app/services/pubsub/common.py

# Built-in
import logging


def get_publish_callback(event_type: str):
    def callback(future):
        try:
            message_id = future.result()
            logging.info(f"Published {event_type} message ID: {message_id}")
        except Exception as e:
            logging.error(f"Failed to publish {event_type} message: {e}")
    return callback
```

### 6.5 Registrazione URL

#### Nel microservizio richiedente (`urls.py` di auth/crm):

```python
# Export per entità
("/users/@export/", UserExportView.as_view("user_export")),
# ("/leads/@export/", LeadExportView.as_view("lead_export")),
# ecc.
```

#### Nel microservizio uploads (`urls.py`):

```python
# API interne (protette da X-Internal-Token)
("/internal/export-downloads/", InternalExportDownloadRequestView.as_view("internal_export_download_request")),
("/internal/export-downloads/<uuid:export_download_id>/", InternalExportDownloadDetailView.as_view("internal_export_download_detail")),

# API pubbliche (autenticazione utente)
("/export-downloads/", ExportDownloadListView.as_view("export_download_list")),
("/export-downloads/<uuid:export_download_id>/download/", ExportDownloadFileView.as_view("export_download_file")),
```

### 6.6 Permessi

#### Nel microservizio richiedente (`permissions.py` di auth/crm):

```python
# Export per entità (un permesso per ogni export)
user_export = EndpointPermission(
    post={
        "description": "Richiesta export utenti CSV",
        "roles": [UserTypes.ADMIN],
    },
)
```

#### Nel microservizio uploads (`permissions.py`):

```python
# Export Downloads
export_download_list = EndpointPermission(
    get={
        "description": "Lista export downloads dell'utente",
        "roles": [UserTypes.ADMIN],
    },
)
export_download_file = EndpointPermission(
    get={
        "description": "Download file export generato",
        "roles": [UserTypes.ADMIN],
    },
)
```

> **Nota**: Gli endpoint interni (`/internal/...`) sono protetti dal header `X-Internal-Token` e non richiedono permessi utente.

## 7. Worker di generazione CSV

### 7.1 Tecnologia da utilizzare

La generazione dei CSV deve essere eseguita da un worker dedicato, separato dal processo HTTP Flask.

Tecnologie:

- Python 3.12, usando lo stesso codebase del microservizio;
- `google-cloud-pubsub` per consumare messaggi da una Pub/Sub pull subscription;
- lo stesso ORM/framework dFlango già usato dal backend per accedere a model, schema e view;
- esecuzione tramite `run.py` con flag di modalità worker, avviato da `run.sh`.

Il worker deve essere un processo long-running che resta in ascolto sulla subscription Pub/Sub e processa un numero limitato di messaggi contemporaneamente.

### 7.2 Perché usare un worker pull e non una push subscription HTTP

Per gli export CSV pesanti non bisogna usare un endpoint HTTP chiamato direttamente da Pub/Sub tramite push subscription.

Una push subscription potrebbe generare troppe chiamate concorrenti al backend. Per esempio, 100 messaggi Pub/Sub potrebbero trasformarsi in 100 richieste HTTP concorrenti e quindi in 100 generazioni CSV simultanee.

Con un worker pull, invece, la concorrenza viene controllata dal processo worker:

```text
100 messaggi in coda
↓
CSV_EXPORT_MAX_CONCURRENT_WORKERS = 4
↓
4 export processati contemporaneamente
96 export restano in attesa sulla subscription Pub/Sub
```

### 7.3 Variabili di configurazione

In `app/config.py`, aggiungere le variabili dedicate per il worker:

```python
# PubSub - CSV Export
PUBSUB_CSV_EXPORT_TOPIC = os.environ.get("PUBSUB_CSV_EXPORT_TOPIC", "csv-export")
PUBSUB_CSV_EXPORT_SUBSCRIPTION = os.environ.get("PUBSUB_CSV_EXPORT_SUBSCRIPTION", "csv-export-sub")

# CSV Export Worker
CSV_EXPORT_DEFAULT_BATCH_SIZE = int(os.environ.get("CSV_EXPORT_DEFAULT_BATCH_SIZE", "2000"))
CSV_EXPORT_MAX_CONCURRENT_WORKERS = int(os.environ.get("CSV_EXPORT_MAX_CONCURRENT_WORKERS", "2"))
CSV_EXPORT_MAX_MESSAGES = int(os.environ.get("CSV_EXPORT_MAX_MESSAGES", "2"))
CSV_EXPORT_MAX_ATTEMPTS = int(os.environ.get("CSV_EXPORT_MAX_ATTEMPTS", "3"))
CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS = int(os.environ.get("CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS", "10"))
CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS = int(os.environ.get("CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS", "30"))

# Storage
EXPORT_STORAGE_PATH = os.environ.get("EXPORT_STORAGE_PATH", "/data/exports")
```

### 7.4 Setup Pub/Sub locale

Seguendo lo stesso pattern del servizio `notifications`, aggiungere la creazione del topic e della subscription nel file `setup-pubsub.sh`:

```bash
# Create the CSV export topic
curl -s -o /dev/null -X PUT "http://localhost:8085/v1/projects/crm/topics/csv-export"

# Create the CSV export subscription
curl -s -o /dev/null -X PUT -H "Content-Type: application/json" \
     -d "{\"topic\": \"projects/crm/topics/csv-export\"}" \
     "http://localhost:8085/v1/projects/crm/subscriptions/csv-export-sub"
```

### 7.5 Struttura consigliata del codice

#### Microservizio richiedente con worker (es. `auth`)

```text
app/
  exports/
    csv/
      __init__.py            # Importa gli schema per registrarli
      fields.py              # CSVField, sanitize_csv_value, formatters
      schemas.py             # ExportContext, CSVExportSchema base
      registry.py            # CSVExportRegistry
      service.py             # Logica worker (handle_csv_export_requested)
      storage.py             # generate_and_save_csv, iterate_queryset_by_pk
      <entity>_export.py     # Schema specifico (es. users_export.py)
  services/
    internal/
      export_downloads.py    # Client HTTP: create/get/update ExportDownload su uploads
      uploads.py             # Client HTTP: presigned URL + upload GCS
    pubsub/
      __init__.py
      common.py              # get_publish_callback
      notifications.py       # send_export_ready_notification
  workers/
    __init__.py
    csv_export_worker.py     # Entrypoint worker Pub/Sub
```

#### Microservizio richiedente senza worker (es. `crm`)

```text
app/
  exports/
    csv/
      __init__.py            # Importa gli schema per registrarli
      fields.py              # CSVField, sanitize_csv_value, formatters
      schemas.py             # ExportContext, CSVExportSchema base
      registry.py            # CSVExportRegistry
      <entity>_export.py     # Schema specifico (es. leads_export.py)
  services/
    internal/
      export_downloads.py    # Client HTTP: solo create_export_download
```

> **Nota**: `crm` non ha `workers/`, `pubsub/`, `service.py`, `storage.py`. Gli export CRM sono consumati dal worker di `auth`.

#### Microservizio `uploads` (centrale)

```text
app/
  models/
    export_download.py       # Model ExportDownload (canonical)
  constants/
    export_status.py         # ExportStatus enum
  schemas/
    export_download.py       # ExportDownloadReadSchema
  views/
    export/
      internal_export_download_request.py  # POST interna: crea + pubblica Pub/Sub
      internal_export_download_detail.py   # GET/PUT interna: legge/aggiorna
      export_download_list.py              # GET pubblica: lista per utente
      export_download_file.py              # GET pubblica: presigned URL download
  services/
    pubsub/
      common.py              # get_publish_callback
      csv_export.py          # publish_csv_export_requested
```

### 7.6 Adattamento `run.sh`

Il worker viene eseguito **nello stesso container** del web server. In sviluppo, come processo background; in produzione, gestito da `supervisord`:

```bash
#! /bin/bash

echo -e "\e[34m >>> Migrating changes \e[97m"
flask db upgrade
echo -e "\e[32m >>> Migration completed \e[97m"

if [ "$FLASK_ENV" = "development" ]; then
    echo -e "\e[34m >>> Running in development mode \e[97m"
    python -m app.workers.csv_export_worker &
    python run.py
else
    echo -e "\e[34m >>> Running in production mode \e[97m"
    exec supervisord -c /supervisord.conf
fi
```

### 7.6.1 Configurazione supervisord

In produzione, `supervisord` gestisce sia il web server che il worker nello stesso container:

```ini
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:web]
command=waitress-serve --listen=*:8000 --call app:create_app
directory=/
autostart=true
autorestart=true
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0

[program:csv-export-worker]
command=python -m app.workers.csv_export_worker
directory=/
autostart=true
autorestart=true
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
```

### 7.7 Adattamento `run.py`

Il `run.py` non necessita di modifiche. Il worker viene avviato direttamente come modulo Python:

```bash
python -m app.workers.csv_export_worker
```

### 7.8 Entrypoint del worker

```python
# app/workers/csv_export_worker.py

# Built-in
import json
import logging

# Third-party
from google.cloud import pubsub_v1

# Local
from app import create_app

# Config
from app.config import Config


def main():
    app = create_app()

    with app.app_context():
        start_csv_export_worker()


def start_csv_export_worker():
    subscriber = pubsub_v1.SubscriberClient()

    subscription_path = subscriber.subscription_path(
        Config.PUBSUB_PROJECT_ID,
        Config.PUBSUB_CSV_EXPORT_SUBSCRIPTION,
    )

    flow_control = pubsub_v1.types.FlowControl(
        max_messages=Config.CSV_EXPORT_MAX_MESSAGES,
    )

    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=lambda message: handle_pubsub_message(message),
        flow_control=flow_control,
    )

    logging.info(f"CSV export worker started on {subscription_path}")

    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        streaming_pull_future.result(timeout=Config.CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS)


def handle_pubsub_message(message):
    try:
        payload = json.loads(message.data.decode("utf-8"))

        if payload.get("event_type") != "csv_export_requested":
            message.ack()
            return

        handle_csv_export_requested(payload)
        message.ack()

    except RetryableCSVExportError as exc:
        logging.warning(f"Retryable CSV export error: {exc}")
        message.nack()

    except Exception as exc:
        logging.exception("Non retryable CSV export error")
        mark_export_as_failed_from_message(message=message, exc=exc)
        message.ack()


if __name__ == "__main__":
    main()
```

### 7.9 Handler applicativo

Il worker delega la logica applicativa a un service. Le operazioni sull'`ExportDownload` avvengono tramite HTTP al servizio `uploads` (dict, non model ORM):

```python
# app/exports/csv/service.py

# Built-in
import logging
import os
from datetime import datetime, timezone

# Config
from app.config import Config

# Exports
from app.exports.csv.registry import CSVExportRegistry
from app.exports.csv.schemas import ExportContext
from app.exports.csv.storage import generate_and_save_csv

# Services
from app.services.pubsub.notifications import send_export_ready_notification
from app.services.internal.uploads import upload_csv_to_storage
from app.services.internal.export_downloads import get_export_download, update_export_download


class RetryableCSVExportError(Exception):
    pass


def handle_csv_export_requested(payload: dict):
    export_id = payload["export_download_id"]
    export_type = payload["export_type"]

    export = acquire_export_lock(export_id)

    if export is None:
        return

    if export["export_type"] != export_type:
        logging.error(f"Export type mismatch: expected {export['export_type']}, got {export_type}")
        return

    try:
        generate_csv_export(export)

    except RetryableCSVExportError:
        release_export_lock(export["id"])
        raise

    except Exception as exc:
        mark_export_failed(export["id"], exc)
        raise
```

### 7.10 Lock e idempotenza del worker

Pub/Sub può consegnare lo stesso messaggio più di una volta. Il worker deve quindi essere idempotente.

L'acquisizione del lock avviene tramite HTTP al servizio `uploads`, non con `SELECT ... FOR UPDATE` locale:

```python
def acquire_export_lock(export_id) -> dict | None:
    try:
        export = get_export_download(export_id)
    except Exception:
        return None

    if export is None:
        return None

    if export["status"] == "COMPLETED":
        return None

    if export["status"] == "RUNNING" and not lock_is_expired(export):
        return None

    if export["status"] not in ("QUEUED", "FAILED"):
        return None

    if export["attempts"] >= Config.CSV_EXPORT_MAX_ATTEMPTS:
        return None

    now = datetime.now(timezone.utc)
    update_export_download(
        export_id,
        status="RUNNING",
        locked_at=now.isoformat(),
        started_at=export["started_at"] or now.isoformat(),
        attempts=export["attempts"] + 1,
    )
    export["status"] = "RUNNING"
    export["locked_at"] = now.isoformat()
    export["started_at"] = export["started_at"] or now.isoformat()
    export["attempts"] = export["attempts"] + 1

    return export
```

    if export.status not in (ExportStatus.QUEUED, ExportStatus.FAILED):
        return None

    if export.attempts >= Config.CSV_EXPORT_MAX_ATTEMPTS:
        return None

    now = datetime.now(timezone.utc)
    export.status = ExportStatus.RUNNING
    export.locked_at = now
    export.started_at = export.started_at or now
    export.attempts += 1
    db.session.commit()

    return export
```

Regole:

- `COMPLETED`: il worker non fa nulla e fa ack del messaggio;
- `RUNNING` con lock valido: il worker non fa nulla e fa ack del messaggio;
- `QUEUED`: il worker acquisisce il lock e processa;
- `FAILED` con attempts disponibili: può essere ritentato;
- attempts esauriti: il worker lascia il record in `FAILED` e fa ack.

### 7.11 Generazione CSV e upload su GCS

```python
def generate_csv_export(export: dict) -> None:
    schema = CSVExportRegistry.get(export["export_type"])

    context = ExportContext(
        filters=export.get("filters_json") or {},
        requested_at=datetime.fromisoformat(export["created_at"]) if export.get("created_at") else datetime.now(timezone.utc),
    )
    schema.check_permissions(context)

    queryset = schema.get_queryset(context)

    total_rows = safe_count(queryset)
    update_export_download(export["id"], total_rows=total_rows)

    filename = schema.get_filename(context)

    written_rows, file_size = generate_and_save_csv(
        schema=schema,
        queryset=queryset,
        export_id=export["id"],
        filename=filename,
    )

    local_file_path = os.path.join(Config.EXPORT_STORAGE_PATH, export["id"], filename)

    # Carica il file su GCS tramite il servizio uploads
    upload_data = upload_csv_to_storage(
        file_path=local_file_path,
        filename=filename,
        user_id=export["requested_by_user_id"],
    )

    # Elimina il file locale dopo il caricamento su GCS
    try:
        os.remove(local_file_path)
        os.rmdir(os.path.dirname(local_file_path))
    except OSError as e:
        logging.warning(f"Could not clean up local export file {local_file_path}: {e}")

    update_export_download(
        export["id"],
        status="COMPLETED",
        filename=filename,
        file_path=upload_data.get("file_path"),
        upload_id=upload_data["id"],
        processed_rows=written_rows,
        file_size_bytes=file_size,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    # Invia notifica email
    updated_export = get_export_download(export["id"])
    send_export_ready_notification(updated_export)
```

### 7.11.1 Upload CSV su GCS tramite uploads

Il file CSV viene caricato su GCS in tre step tramite il servizio `uploads`:

```python
# app/services/internal/uploads.py

def upload_csv_to_storage(file_path: str, filename: str, user_id: str) -> dict:
    """
    Flusso:
    1. Richiede una presigned URL al servizio uploads
    2. Carica il file direttamente su GCS tramite la presigned URL
    3. Conferma il caricamento al servizio uploads
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
            "files": [{
                "file_name": filename,
                "content_type": "text/csv",
                "content_length": file_size,
            }],
        },
        timeout=30,
    )
    presigned_response.raise_for_status()

    upload_data = presigned_response.json()["uploads"][0]
    upload_id = upload_data["id"]
    presigned_url = upload_data["presigned_url"]

    # Step 2: carica su GCS
    upload_method = requests.post if "uploadType=media" in presigned_url else requests.put
    with open(file_path, "rb") as f:
        gcs_response = upload_method(presigned_url, data=f, headers={"Content-Type": "text/csv"}, timeout=300)
    gcs_response.raise_for_status()

    # Step 3: conferma upload
    confirm_response = requests.post(
        f"{Config.UPLOADS_INTERNAL_API_URL}/internal/{upload_id}/",
        headers=headers,
        timeout=30,
    )
    confirm_response.raise_for_status()

    return upload_data
```

### 7.12 Notifica email a completamento

La notifica email utilizza il topic `notifications` già esistente, seguendo lo stesso pattern usato dal resto del sistema:

```python
# app/services/pubsub/notifications.py

# Built-in
import json
import logging

# Third-party
from google.cloud import pubsub_v1

# Config
from app.config import Config

# Services
from app.services.pubsub.common import get_publish_callback


def send_export_ready_notification(export):
    """Pubblica un messaggio sul topic notifications per inviare email di export pronto."""
    payload = {
        "recipients": get_user_email(export.requested_by_user_id),
        "subject": f"Export {export.export_type} completato",
        "html_content": render_export_ready_email(export),
    }

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        Config.PUBSUB_PROJECT_ID,
        Config.PUBSUB_NOTIFICATIONS_TOPIC,
    )

    message_data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, message_data)
    future.add_done_callback(get_publish_callback("export_ready_notification"))
```

### 7.13 Modifiche a Docker Compose

**Non** serve un servizio Docker Compose separato per il worker. Il worker viene eseguito nello stesso container del microservizio, gestito da `supervisord` in produzione e come processo background (`&`) in sviluppo.

Il servizio del microservizio richiedente (es. `auth`) deve avere le seguenti variabili di ambiente aggiuntive:

```yaml
services:
  auth:
    build: ./apps/auth
    environment:
      # ... configurazione esistente ...
      # PubSub - CSV Export
      - PUBSUB_CSV_EXPORT_TOPIC=csv-export
      - PUBSUB_CSV_EXPORT_SUBSCRIPTION=csv-export-sub
      # CSV Export Worker
      - CSV_EXPORT_MAX_CONCURRENT_WORKERS=2
      - CSV_EXPORT_MAX_MESSAGES=2
      - CSV_EXPORT_MAX_ATTEMPTS=3
      - EXPORT_STORAGE_PATH=/data/exports
      # Internal API (uploads)
      - UPLOADS_INTERNAL_API_URL=http://uploads:8000/api/uploads
      - INTERNAL_API_SECRET=${INTERNAL_API_SECRET:-internal-secret-token-change-in-production}
    volumes:
      - auth-export-data:/data/exports

volumes:
  auth-export-data:
```

Il servizio `uploads` deve avere la configurazione Pub/Sub per il topic `csv-export`:

```yaml
  uploads:
    build: ./apps/uploads
    environment:
      # ... configurazione esistente ...
      - PUBSUB_CSV_EXPORT_TOPIC=csv-export
      - CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS=10
```

### 7.14 Setup Pub/Sub locale

Modificare `apps/pubsub/setup-pubsub.sh` per aggiungere il topic e la subscription per CSV export, seguendo lo stesso pattern di `notifications`:

```bash
#!/bin/sh

# ... setup esistente (emulator start, wait, ecc.) ...

# Create the notifications topic
curl -s -o /dev/null -X PUT "http://localhost:8085/v1/projects/crm/topics/notifications"

# Create the notifications subscription
curl -s -o /dev/null -X PUT -H "Content-Type: application/json" \
     -d "{\"topic\": \"projects/crm/topics/notifications\"}" \
     "http://localhost:8085/v1/projects/crm/subscriptions/notifications-sub"

# Create the CSV export topic
curl -s -o /dev/null -X PUT "http://localhost:8085/v1/projects/crm/topics/csv-export"

# Create the CSV export subscription
curl -s -o /dev/null -X PUT -H "Content-Type: application/json" \
     -d "{\"topic\": \"projects/crm/topics/csv-export\"}" \
     "http://localhost:8085/v1/projects/crm/subscriptions/csv-export-sub"

echo "Pub/Sub setup complete. Keeping the container running..."
tail -f /dev/null
```

### 7.15 Osservabilità

Il worker deve produrre log strutturati con almeno:

- `export_download_id`;
- `export_type`;
- `status`;
- `processed_rows`;
- `total_rows`;
- durata generazione;
- dimensione file;
- errore, se presente.

## 8. Strategia efficiente per dataset grandi

### 8.1 Queryset da 100k righe: è pesante?

Non è un problema creare un oggetto queryset lazy che rappresenta la query. È invece un problema materializzarlo tutto in memoria, ad esempio con:

```python
rows = list(queryset)
```

Per export grandi bisogna iterare a batch, mantenendo in memoria solo un blocco limitato di righe.

### 8.2 Count del queryset

Il `count()` può essere utile per mostrare avanzamento e stimare durata, ma non è sempre gratuito.

Lo standard consigliato è:

- eseguire `count()` solo se ragionevolmente sostenibile;
- consentire `total_rows = None` se il count fallisce o supera una soglia;
- non bloccare l'export solo perché il count non è disponibile.

```python
def safe_count(queryset) -> int | None:
    try:
        return queryset.count()
    except Exception:
        return None
```

### 8.3 Evitare offset pagination per export grandi

Evitare questo pattern per dataset grandi:

```python
for offset in range(0, total_rows, batch_size):
    batch = queryset[offset:offset + batch_size]
```

Preferire keyset pagination:

```python
def iterate_queryset_by_pk(queryset, batch_size: int):
    last_pk = None

    while True:
        batch_qs = queryset.order_by(queryset.column_descriptions[0]["entity"].id)

        if last_pk is not None:
            batch_qs = batch_qs.filter(queryset.column_descriptions[0]["entity"].id > last_pk)

        batch = batch_qs.limit(batch_size).all()

        if not batch:
            break

        for obj in batch:
            yield obj

        last_pk = batch[-1].id
```

### 8.4 Evitare N+1 query

Ogni schema deve ottimizzare la query usando:

- `lazy="selectin"` sulle relazioni nel model (standard dFlango);
- `.options(joinedload(...))` per relazioni specifiche;
- `.with_entities(...)` per caricare solo i campi necessari quando possibile.

## 9. Scrittura CSV e salvataggio file

### 9.1 Approccio consigliato

L'implementazione dello storage è agnostica. Lo standard definisce un'interfaccia di salvataggio che può essere implementata per:

- filesystem locale o volume montato;
- object storage (S3, GCS, Azure Blob);
- qualsiasi altro sistema di storage.

### 9.2 Scrittura su file temporaneo e salvataggio

```python
# app/exports/csv/storage.py

# Built-in
import csv
import os
import tempfile

# Config
from app.config import Config


def generate_and_save_csv(schema, queryset, export, filename):
    """Genera il CSV su file temporaneo e lo salva nel path definitivo."""
    export_dir = os.path.join(Config.EXPORT_STORAGE_PATH, str(export.id))
    os.makedirs(export_dir, exist_ok=True)
    final_path = os.path.join(export_dir, filename)

    written_rows = 0

    with tempfile.NamedTemporaryFile(
        mode="w", encoding=schema.encoding, newline="", suffix=".csv", delete=False
    ) as tmp:
        writer = csv.writer(tmp, delimiter=schema.delimiter, lineterminator="\n")
        writer.writerow(schema.get_headers())

        for obj in iterate_queryset_by_pk(queryset, schema.batch_size):
            writer.writerow(schema.serialize_row(obj))
            written_rows += 1

            if written_rows % schema.batch_size == 0:
                update_export_progress(export.id, written_rows)

        tmp.flush()
        temp_path = tmp.name

    # Move temp file to final location
    os.rename(temp_path, final_path)
    file_size = os.path.getsize(final_path)

    return written_rows, file_size


def get_export_file_path(export_id, filename):
    """Restituisce il path relativo del file export."""
    return os.path.join(str(export_id), filename)
```

### 9.3 Path di salvataggio

I file vengono salvati nella directory configurata da `EXPORT_STORAGE_PATH`:

```text
/data/exports/<export_id>/<filename>
```

Lo stato `COMPLETED` deve essere salvato solo dopo che il file definitivo è disponibile.

## 10. Sicurezza dei valori CSV

### 10.1 CSV injection

I CSV aperti con Excel o strumenti simili possono interpretare celle che iniziano con caratteri speciali come formule.

Sanitizzare sempre i valori stringa che iniziano con:

- `=`
- `+`
- `-`
- `@`
- tab
- carriage return

```python
# app/exports/csv/fields.py

DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_value(value: str) -> str:
    if value is None:
        return ""

    value = str(value)

    if value.startswith(DANGEROUS_CSV_PREFIXES):
        return "'" + value

    return value
```

### 10.2 Autorizzazioni

Ogni export deve applicare sempre:

- permessi utente (tramite `ViewPermissions`);
- filtri consentiti;
- row-level security applicativa;
- esclusione di campi sensibili non previsti.

Il worker deve ricostruire il contesto dell'utente dal record `ExportDownload` e rieseguire i controlli principali.

## 11. Idempotenza e retry

Pub/Sub può consegnare lo stesso messaggio più di una volta. Il worker deve quindi essere idempotente.

Regole consigliate:

- se l'export è già `COMPLETED`, il worker esce senza fare nulla;
- se l'export è `RUNNING` con lock recente, il worker esce;
- se l'export è `FAILED` ma ancora entro `max_attempts`, può essere ritentato;
- usare path basati su `export_id`, non su timestamp casuali;
- inviare notifica email solo dopo transizione effettiva a `COMPLETED`.

## 12. Limiti e policy

Definire limiti globali configurabili:

```python
CSV_EXPORT_DEFAULT_BATCH_SIZE = 2000
CSV_EXPORT_MAX_ATTEMPTS = 3
CSV_EXPORT_MAX_CONCURRENT_WORKERS = 2
CSV_EXPORT_MAX_MESSAGES = 2
CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS = 10
CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30
```

Policy consigliate:

- non consentire export illimitati senza filtri su tabelle enormi;
- imporre un limite massimo di righe per alcuni export;
- richiedere intervalli data per dataset storici;
- rate limit per utente;
- nessuna retention automatica in questa versione dello standard;
- i CSV generati restano disponibili permanentemente;
- un eventuale sistema di cleanup dei vecchi file potrà essere progettato successivamente.

## 13. Formattazione standard

Definire formatter riutilizzabili in `app/exports/csv/fields.py`:

```python
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

Scelte consigliate:

- encoding default: `utf-8`;
- newline: `\n`;
- quoting: `csv.QUOTE_MINIMAL`;
- delimiter default: `,`;
- BOM disabilitato di default, abilitabile per compatibilità Excel;
- date/datetime in ISO 8601 salvo requisiti business diversi.

## 14. Esempio completo: export ordini

```python
# app/exports/csv/order_export.py

# Exports
from app.exports.csv.schemas import CSVExportSchema
from app.exports.csv.fields import CSVField, format_datetime, format_decimal
from app.exports.csv.registry import CSVExportRegistry

# Models
from app.models.order import Order


@CSVExportRegistry.register
class OrdersCSVExportSchema(CSVExportSchema):
    export_type = "orders_csv"
    filename_prefix = "orders"
    batch_size = 2000

    fields = [
        CSVField("id", "ID ordine"),
        CSVField("created_at", "Data creazione", formatter=format_datetime),
        CSVField("status", "Stato"),
        CSVField("customer_email", "Email cliente", getter=lambda obj: obj.customer.email),
        CSVField("total_amount", "Totale", formatter=format_decimal),
    ]

    def validate_filters(self, filters: dict) -> dict:
        validated = {}

        if "date_from" in filters:
            validated["date_from"] = filters["date_from"]

        if "date_to" in filters:
            validated["date_to"] = filters["date_to"]

        if "status" in filters:
            validated["status"] = filters["status"]

        return validated

    def check_permissions(self, context) -> None:
        # Verificare permessi specifici se necessario
        pass

    def get_queryset(self, context):
        query = Order.query.filter_by(deleted_at=None)

        if context.filters.get("date_from"):
            query = query.filter(Order.created_at >= context.filters["date_from"])

        if context.filters.get("date_to"):
            query = query.filter(Order.created_at <= context.filters["date_to"])

        if context.filters.get("status"):
            query = query.filter(Order.status == context.filters["status"])

        return query.order_by(Order.id)
```

## 15. Istruzioni operative per un agente AI

Quando viene richiesto di implementare un nuovo export CSV, l'agente deve seguire questi passaggi.

### 15.1 Creare lo schema CSV export

Creare una classe che estende `CSVExportSchema` in `app/exports/csv/`.

La classe deve definire:

- `export_type` univoco;
- `filename_prefix`;
- `fields` (lista di `CSVField`);
- `validate_filters`;
- `check_permissions`;
- `get_queryset`.

### 15.2 Ottimizzare la query

La query deve:

- filtrare sempre con `deleted_at=None` (soft delete standard dFlango);
- applicare solo filtri validati;
- ordinare per chiave stabile (`Order.id`);
- evitare N+1 query (usare `lazy="selectin"` o `joinedload`);
- caricare solo i campi necessari;
- non materializzare l'intero dataset.

### 15.3 Registrare lo schema

Registrare la classe nel registry:

```python
@CSVExportRegistry.register
class MyExportSchema(CSVExportSchema):
    ...
```

### 15.4 Creare il model ExportDownload

Se non esiste, creare il model `ExportDownload` in `app/models/export_download.py` seguendo le convenzioni:

- PK UUID;
- `__tablename__ = "export_download"`;
- timestamp standard (`created_at`, `updated_at`, `deleted_at`);
- status come `db.Enum(ExportStatus)` con valori in MAIUSCOLO;
- aggiornare `app/models/__init__.py`.

### 15.5 Creare l'enum ExportStatus

Creare in `app/constants/export_status.py`:

```python
from dflango.enum import Enum

class ExportStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

### 15.6 Creare le view

Creare le view seguendo lo standard dFlango:

- `ExportDownloadRequestView` — `BaseView` con metodo `post(self, export_type)`;
- `ExportDownloadListView` — `ListView` con `allowed_filters` e `get_query()` filtrato per `requested_by_user_id`;
- `ExportDownloadFileView` — `BaseView` con metodo `get(self, export_download_id)` per il download.

Tutte le view devono:

- dichiarare `only_authenticated = True`;
- NON dichiarare ruoli direttamente (vengono risolti da `ViewPermissions`).

### 15.7 Registrare URL e permessi

- Aggiungere le URL in `app/urls.py` usando path al plurale;
- Aggiungere i permessi in `app/config/permissions.py` usando `EndpointPermission`;
- Il nome dell'endpoint in `as_view("...")` deve corrispondere all'attributo su `ViewPermissions`.

### 15.8 Creare lo schema Marshmallow di lettura

Creare `app/schemas/export/export_download_read.py` con `ModelSchema` e tutti i campi `dump_only=True`.

### 15.9 Creare il servizio Pub/Sub

Creare `app/services/pubsub/csv_export.py` seguendo il pattern di `common.py` + publish con callback.

### 15.10 Non generare il CSV nella view

È vietato generare il CSV nella request HTTP.

La view deve solo creare il record e accodare il job su Pub/Sub.

### 15.11 Non salvare il CSV completo in memoria

È vietato usare pattern come:

```python
rows = list(queryset)
csv_content = "..."
```

Usare sempre file temporaneo con iterazione a batch.

### 15.12 Adattare Docker Compose

- Aggiungere il servizio `csv-export-worker` nel `docker-compose.yml` usando la stessa build del microservizio;
- Impostare `APP_MODE=worker` nelle variabili d'ambiente;
- Aggiungere le variabili Pub/Sub (`PUBSUB_CSV_EXPORT_TOPIC`, `PUBSUB_CSV_EXPORT_SUBSCRIPTION`);
- Non esporre porte HTTP (il worker non serve richieste HTTP);
- Impostare `traefik.enable=false`.

### 15.13 Adattare run.sh

Aggiungere il branch `APP_MODE=worker` nel `run.sh` per avviare il worker con:

```bash
python -m app.workers.csv_export_worker
```

### 15.14 Aggiungere topic al setup Pub/Sub

Aggiungere la creazione del topic `csv-export` e della subscription `csv-export-sub` in `apps/pubsub/setup-pubsub.sh`, seguendo lo stesso pattern di `notifications`.

### 15.15 Usare il topic notifications per le email

La notifica email a completamento export deve pubblicare un messaggio sul topic `notifications` già esistente, con il formato atteso dal servizio notifications:

```json
{
  "recipients": "user@example.com",
  "subject": "Export completato",
  "html_content": "<html>...</html>"
}
```

### 15.16 Ordine degli import

Tutti i file devono rispettare l'ordine degli import definito in `DEVELOPMENT_STANDARDS.md`:

1. Built-in
2. Flask
3. dFlango
4. Third-party
5. Models
6. Schemas
7. Constants
8. Utils
9. Services

## 16. Checklist finale per ogni export

Prima di considerare completo un export CSV verificare:

- [ ] esiste una classe `CSVExportSchema` dedicata in `app/exports/csv/`;
- [ ] lo schema è registrato nel `CSVExportRegistry`;
- [ ] i filtri sono validati;
- [ ] i permessi sono controllati tramite `ViewPermissions`;
- [ ] la query filtra per `deleted_at=None`;
- [ ] la query evita N+1;
- [ ] l'iterazione avviene a batch con keyset pagination;
- [ ] il CSV viene scritto su file temporaneo, mai in memoria;
- [ ] i valori sono protetti da CSV injection (`sanitize_csv_value`);
- [ ] il job è idempotente;
- [ ] il record `ExportDownload` viene aggiornato con progress e stato finale;
- [ ] il file viene salvato nel path definitivo solo a generazione completata;
- [ ] viene inviata notifica tramite topic `notifications`;
- [ ] il download avviene tramite endpoint protetto;
- [ ] le URL sono registrate in `urls.py`;
- [ ] i permessi sono configurati in `permissions.py`;
- [ ] gli enum usano valori in MAIUSCOLO;
- [ ] gli import seguono l'ordine standard;
- [ ] esistono test automatici.

## 17. Test consigliati

### 17.1 Unit test schema CSV

- validazione filtri;
- headers CSV;
- serializzazione riga;
- formattazione valori nulli;
- sanitizzazione CSV injection.

### 17.2 Integration test worker

- export completato correttamente con stato `COMPLETED`;
- export fallito con stato `FAILED`;
- retry idempotente;
- aggiornamento `processed_rows`;
- salvataggio file;
- notifica email inviata una sola volta.

### 17.3 Test API (seguendo `TEST_STANDARDS.md`)

- `POST /export-downloads/<export_type>/` → 202 con record creato;
- `POST /export-downloads/<export_type>/` → 403 per ruolo non autorizzato;
- `GET /export-downloads/` → lista filtrata per utente corrente;
- `GET /export-downloads/<id>/download/` → 404 se non esiste o non appartiene all'utente;
- filtri `allowed_filters` funzionanti.

## 18. Raccomandazione finale

Il design consigliato è:

1. API Flask con `BaseView`;
2. record `ExportDownload` persistito subito con `ExportStatus.QUEUED`;
3. publish Pub/Sub diretto dalla API su topic `csv-export`;
4. errore API se il publish Pub/Sub fallisce;
5. Pub/Sub con payload minimo;
6. worker pull dedicato, avviato tramite `APP_MODE=worker` in `run.sh`;
7. concorrenza controllata tramite `CSV_EXPORT_MAX_CONCURRENT_WORKERS` e flow control Pub/Sub;
8. schema CSV per ogni export registrato nel `CSVExportRegistry`;
9. query lazy con `filter_by(deleted_at=None)` e iterata a batch;
10. scrittura su file temporaneo e salvataggio nel path definitivo;
11. update progressivo del record download;
12. notifica email tramite topic `notifications` esistente;
13. disponibilità permanente del CSV generato, salvo futuri sistemi di cleanup.

Per il caso da 100k righe, non è necessario caricare tutto in memoria. È preferibile scrivere riga per riga su file temporaneo con iterazione a batch, aggiornando sul database solo il progresso logico dell'export.

La generazione deve essere eseguita dal worker dedicato con lo stesso Dockerfile del microservizio, differenziato solo dalla variabile `APP_MODE=worker` e dal relativo branch in `run.sh`.
