# Guida pratica: Gestione File nei Microservizi

## Obiettivo

Questa guida definisce lo standard per la gestione dei file (upload, download, visualizzazione) in un'architettura a microservizi Python/Flask. I file sono gestiti centralmente dal **microservizio uploads**, che espone API interne per la generazione di presigned URL, conferma upload e recupero URL di download. Gli altri microservizi interagiscono con lo storage esclusivamente tramite il client interno verso il servizio uploads.

---

## 1) Architettura

### 1.1 Principi

| Principio                           | Descrizione                                                                                                |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Storage centralizzato               | Tutti i file sono salvati su object storage (GCS, MinIO, S3-compatible) tramite il microservizio `uploads` |
| Nessun accesso diretto allo storage | I microservizi NON accedono mai direttamente al bucket                                                     |
| Presigned URL                       | L'upload e il download dei file avvengono tramite URL firmati con scadenza                                 |
| Tracciamento                        | Ogni file caricato ha un record nel database del servizio uploads                                          |
| Indipendenza                        | Il microservizio chiamante salva solo l'`upload_id` (UUID) come riferimento                                |

### 1.2 Flusso upload (lato client → microservizio → Object Storage)

```
┌─────────┐       ┌──────────────────┐       ┌──────────────────┐       ┌────────────────┐
│  Client │──1──▶ │  Microservizio X │──2──▶ │  Uploads Service │──3──▶ │ Object Storage │
│ (FE/BE) │       │  (es. auth, crm) │       │   (internal API) │       │ (GCS/MinIO/S3) │
└─────────┘       └──────────────────┘       └──────────────────┘       └────────────────┘
     │                                                                          ▲
     └──────────────────────── 4. PUT file to presigned URL ────────────────────┘
```

1. Il client invia la richiesta al microservizio di competenza (es. "aggiorna profilo con immagine")
2. Il microservizio richiede una presigned URL al servizio uploads (API interna)
3. Il servizio uploads genera il record e la presigned URL dal bucket
4. Il file viene caricato direttamente sull'object storage tramite la presigned URL (dal client o dal backend)
5. Il microservizio conferma l'upload al servizio uploads
6. Il microservizio salva l'`upload_id` nel proprio model

### 1.3 Flusso download (lettura file)

```
┌─────────┐       ┌──────────────────┐       ┌─────────────────┐
│  Client │◀──3── │ Microservizio X  │──1──▶ │ Uploads Service │
│         │       │                  │◀──2── │                 │
└─────────┘       └──────────────────┘       └─────────────────┘
```

1. Il microservizio chiede l'URL di download al servizio uploads (`GET /internal/<file_id>/`)
2. Il servizio uploads restituisce una presigned URL per il download
3. Il microservizio restituisce l'URL al client (redirect o nel payload JSON)

---

## 2) Configurazione

### 2.1 Variabili d'ambiente

Ogni microservizio che interagisce con i file deve avere nel `docker-compose.yml`:

```yaml
environment:
  - UPLOADS_INTERNAL_API_URL=${UPLOADS_INTERNAL_API_URL:-http://uploads:8000/api/uploads}
  - INTERNAL_API_SECRET=${INTERNAL_API_SECRET:-internal-secret-token-change-in-production}
```

### 2.2 Configurazione Flask (`app/config.py`)

```python
# Internal APIs
UPLOADS_INTERNAL_API_URL = os.environ.get("UPLOADS_INTERNAL_API_URL", "http://uploads:8000/api/uploads")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
```

### 2.3 Dipendenze (`requirements.txt`)

Aggiungere `requests>=2.31` se non già presente.

### 2.4 Docker Compose

Aggiungere `uploads` come dipendenza del microservizio:

```yaml
depends_on:
  uploads:
    condition: service_started
```

---

## 3) Client Interno — `UploadsInternalClient`

### 3.1 Posizione file

```
app/services/internal/uploads.py
```

### 3.2 Implementazione standard

```python
# Built-in
import logging

# Third-party
import requests
from flask import current_app


class UploadsInternalClient:
    def __init__(self):
        self.base_url = current_app.config.get("UPLOADS_INTERNAL_API_URL")
        self.secret = current_app.config.get("INTERNAL_API_SECRET")

    @property
    def _headers(self):
        return {"X-Internal-Token": self.secret}

    def _get(self, url, timeout=10):
        try:
            response = requests.get(url, headers=self._headers, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            logging.error(f"Uploads internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Uploads internal API unreachable: {e}")
            return None

    def _post(self, url, json=None, timeout=10):
        try:
            response = requests.post(url, json=json, headers=self._headers, timeout=timeout)
            if response.status_code in (200, 201, 202):
                return response.json()
            logging.error(f"Uploads internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Uploads internal API unreachable: {e}")
            return None

    def _put(self, url, json=None, timeout=10):
        try:
            response = requests.put(url, json=json, headers=self._headers, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            logging.error(f"Uploads internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Uploads internal API unreachable: {e}")
            return None

    def get_presigned_url(
        self,
        file_name: str,
        content_type: str,
        content_length: int,
        user_id: str,
        is_public: bool,
        file_type: str | None = None,
    ) -> dict | None:
        """
        Request a presigned URL from the uploads service.
        Returns the first upload entry dict or None on failure.

        Response dict keys: id, file_name, file_path, file_type, mime_type,
                           is_public, created_at, uploaded_at, presigned_url
        """
        payload = {
            "user_id": user_id,
            "is_public": is_public,
            "file_type": file_type,
            "files": [{
                "file_name": file_name,
                "content_type": content_type,
                "content_length": content_length,
            }]
        }
        result = self._post(f"{self.base_url}/internal/presigned-url/", json=payload)
        if result:
            uploads = result.get("uploads", [])
            return uploads[0] if uploads else None
        return None

    def confirm_upload(self, file_id: str) -> dict | None:
        """
        Confirm upload completion. Returns the upload record dict or None on failure.

        Response dict keys: id, file_name, file_path, file_type, mime_type,
                           is_public, created_at, uploaded_at
        """
        return self._post(f"{self.base_url}/internal/{file_id}/")

    def get_upload_info(self, file_id: str) -> dict | None:
        """
        Get the download URL for a file from the uploads service.
        Returns a dict with url (and optionally expires_in) or None on failure.

        Response dict keys: id, file_name, file_path, file_type, mime_type,
                           is_public, url, expires_in (optional)
        """
        return self._get(f"{self.base_url}/internal/{file_id}/")
```

### 3.3 Regole di utilizzo

| Regola                               | Dettaglio                                                                                                                  |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Istanziare dentro il request context | `UploadsInternalClient()` accede a `current_app.config`, quindi va istanziato dentro una view o dentro `app.app_context()` |
| Gestione errori                      | Il client ritorna `None` in caso di errore — il chiamante DEVE gestire il caso `None`                                      |
| Nessun import circolare              | Il file è in `app/services/internal/` e non importa model o view                                                           |
| Timeout                              | Tutti i metodi hanno timeout di 10 secondi                                                                                 |

---

## 4) Model — Campi per file

### 4.1 Pattern: campo file singolo

Quando un model ha un campo che rappresenta un file (immagine profilo, documento allegato, ecc.), salvare **due campi**:

```python
# Third-party
from sqlalchemy.dialects.postgresql import UUID

# Campo file: immagine profilo
profile_picture_file_id = db.Column(UUID(as_uuid=True), nullable=True)
profile_picture_file_path = db.Column(db.String(512), nullable=True)
```

| Campo              | Scopo                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------------- |
| `<nome>_file_id`   | UUID del record nel servizio uploads — usato per ottenere l'URL di download                                    |
| `<nome>_file_path` | Path del file nel bucket — usato come cache per evitare chiamate al servizio uploads quando serve solo il path |

**Convenzione naming:** il prefisso è il nome logico del file (es. `profile_picture`, `document`, `attachment`), seguito da `_file_id` e `_file_path`.

### 4.2 Pattern: campo file multiplo

Se un'entità può avere più file dello stesso tipo, usare una tabella di relazione:

```python
class ResourceAttachment(db.Model):
    __tablename__ = "resource_attachment"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id = db.Column(UUID(as_uuid=True), db.ForeignKey("resource.id"), nullable=False, index=True)
    upload_id = db.Column(UUID(as_uuid=True), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
```

### 4.3 File types

Il campo `file_type` nel servizio uploads è una **stringa libera** — non esiste un enum vincolante. Il valore è a discrezione del microservizio chiamante e serve come etichetta semantica per categorizzare i file.

**Convenzione:** usare stringhe in `UPPER_SNAKE_CASE` che descrivano il contesto d'uso del file (es. `PROFILE_PICTURE`, `DOCUMENT`, `ATTACHMENT`, `CSV_EXPORT`). Ogni microservizio può introdurre nuovi valori secondo necessità senza modificare il servizio uploads.

---

## 5) Schema — Gestione file in lettura e scrittura

### 5.1 Schema di lettura (`ReadSchema`)

I campi file nello schema di lettura devono esporre l'**URL di download**, non l'ID grezzo. Usare `fields.Method()`:

```python
# dFlango
from dflango.schemas import ModelSchema

# Third-party
from marshmallow import fields

# Models
from app.models.resource import Resource

# Services
from app.services.internal.uploads import UploadsInternalClient


class ResourceReadSchema(ModelSchema):
    """Schema per la lettura di una risorsa."""

    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    profile_picture = fields.Method("get_profile_picture_url", dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    class Meta:
        model = Resource

    def get_profile_picture_url(self, obj):
        file_id = obj.profile_picture_file_id if hasattr(obj, "profile_picture_file_id") else None
        if not file_id:
            return None
        client = UploadsInternalClient()
        upload_info = client.get_upload_info(str(file_id))
        return upload_info.get("url") if upload_info else None
```

**Regole:**

- Il campo esposto nell'API è il **nome logico** (es. `profile_picture`), non il nome tecnico (`profile_picture_file_id`)
- Se il servizio uploads è irraggiungibile, `get_upload_info` ritorna `None` e il campo restituisce `None` (mai errore 500)
- Non è necessario un `try/except`: il client gestisce internamente tutte le eccezioni e ritorna `None` in caso di errore

### 5.2 Schema di scrittura (`WriteSchema` / `UpdateSchema`)

Lo schema di scrittura accetta l'**UUID del file** (ottenuto dal client dopo l'upload) e lo valida contro il servizio uploads:

```python
# dFlango
from dflango.schemas import ModelSchema

# Third-party
from marshmallow import fields, validates, post_load, ValidationError

# Models
from app.models.resource import Resource

# Services
from app.services.internal.uploads import UploadsInternalClient


class ResourceUpdateSchema(ModelSchema):
    """Schema per l'aggiornamento di una risorsa."""

    name = fields.String(required=False)
    profile_picture = fields.UUID(required=False, allow_none=True, load_only=True)

    # Campi interni mappati dal post_load
    profile_picture_file_id = fields.UUID(required=False, allow_none=True, load_only=True)
    profile_picture_file_path = fields.String(required=False, allow_none=True, load_only=True)

    class Meta:
        model = Resource

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
                # Se il client invia null, rimuove il file
                data["profile_picture_file_id"] = None
                data["profile_picture_file_path"] = None
        return data
```

**Regole:**

- Il campo di input è il **nome logico** (es. `profile_picture`) e accetta un UUID
- `allow_none=True` permette di rimuovere un file inviando `null`
- Il `@validates` verifica che il file esista nel servizio uploads
- Il `@post_load` mappa l'UUID ai campi tecnici del model (`_file_id`, `_file_path`)
- Il `file_path` viene recuperato dalla response del servizio uploads e salvato come cache

### 5.3 Schema di creazione (`CreateSchema`)

Stesso pattern dello `UpdateSchema`, con `required=True` se il file è obbligatorio:

```python
profile_picture = fields.UUID(required=True, load_only=True)
```

---

## 6) View — Endpoint con gestione file

### 6.1 Upload lato client (presigned URL flow)

Quando il frontend deve caricare un file, il flusso standard è:

1. **Frontend** chiede una presigned URL al microservizio di competenza
2. **Microservizio** chiama `UploadsInternalClient().get_presigned_url(...)` e restituisce la presigned URL + upload ID al frontend
3. **Frontend** carica il file direttamente sull'object storage via PUT sulla presigned URL
4. **Frontend** invia l'`upload_id` al microservizio nel body della richiesta di creazione/aggiornamento
5. **Microservizio** valida l'UUID nello schema e conferma l'upload

#### View base per presigned URL

Poiché la logica di generazione presigned URL è comune a più entità (profilo, documenti, allegati, ecc.), definire una **view base riusabile** in `app/views/mixins/presigned_upload.py`:

```python
# Flask
from flask import jsonify

# dFlango
from dflango.views import BaseView

# Mixins

# Services
from app.services.internal.uploads import UploadsInternalClient


class BasePresignedUploadView(BaseView):
    """
    View base per la generazione di presigned URL.
    Le sottoclassi devono definire:
    - ALLOWED_EXTENSIONS: tuple di estensioni ammesse (es. (".jpg", ".png", ".webp"))
    - ALLOWED_CONTENT_TYPES: tuple di content type ammessi (es. ("image/jpeg", "image/png"))
    - MAX_FILE_SIZE: dimensione massima in bytes
    - FILE_TYPE: stringa per il campo file_type nel servizio uploads
    - IS_PUBLIC: se il file è pubblico (default: False)
    """

    accepted_methods = ["POST"]
    only_authenticated = True

    ALLOWED_EXTENSIONS: tuple = ()
    ALLOWED_CONTENT_TYPES: tuple = ()
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB default
    FILE_TYPE: str = "DOCUMENT"
    IS_PUBLIC: bool = False

    _REQUIRED_FIELDS = ("file_name", "content_type", "content_length")

    def post(self):
        user = self.get_current_user()
        data = self.get_request_data()

        # Validazione campi obbligatori
        missing = [f for f in self._REQUIRED_FIELDS if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

        file_name = data["file_name"]
        content_type = data["content_type"]
        content_length = data["content_length"]

        # Validazione estensione
        if self.ALLOWED_EXTENSIONS:
            ext = f".{file_name.rsplit('.', 1)[-1].lower()}" if "." in file_name else ""
            if ext not in self.ALLOWED_EXTENSIONS:
                return jsonify({"error": f"File extension not allowed. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"}), 400

        # Validazione content type
        if self.ALLOWED_CONTENT_TYPES and content_type not in self.ALLOWED_CONTENT_TYPES:
            return jsonify({"error": f"Content type not allowed. Allowed: {', '.join(self.ALLOWED_CONTENT_TYPES)}"}), 400

        # Validazione dimensione
        if content_length > self.MAX_FILE_SIZE:
            max_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            return jsonify({"error": f"File too large. Max size: {max_mb:.0f} MB"}), 400

        client = UploadsInternalClient()
        upload_data = client.get_presigned_url(
            file_name=file_name,
            content_type=content_type,
            content_length=content_length,
            user_id=str(user["id"]),
            is_public=self.IS_PUBLIC,
            file_type=self.FILE_TYPE,
        )

        if upload_data is None:
            return jsonify({"error": "Failed to generate upload URL"}), 502

        return jsonify({
            "upload_id": upload_data["id"],
            "presigned_url": upload_data["presigned_url"],
        }), 200
```

#### View specifica per entità

Ogni entità che richiede upload crea una sottoclasse con la propria configurazione:

```python
# Views
from app.views.mixins.presigned_upload import BasePresignedUploadView


class ProfilePicturePresignedUploadView(BasePresignedUploadView):
    """Presigned URL per upload immagine profilo."""

    ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
    ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    FILE_TYPE = "PROFILE_PICTURE"
    IS_PUBLIC = True


class DocumentPresignedUploadView(BasePresignedUploadView):
    """Presigned URL per upload documenti."""

    ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx")
    ALLOWED_CONTENT_TYPES = ("application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
    FILE_TYPE = "DOCUMENT"
    IS_PUBLIC = False
```

### 6.2 Download file (redirect to presigned URL)

```python
# Flask
from flask import jsonify, redirect

# dFlango
from dflango.views import BaseView

# Models
from app.models.resource import Resource

# Constants
from app.constants.error_codes import ErrorCodes

# Mixins

# Services
from app.services.internal.uploads import UploadsInternalClient


class ResourceFileDownloadView(BaseView):
    accepted_methods = ["GET"]
    only_authenticated = True

    def get(self, resource_id):
        resource = Resource.query.filter_by(id=resource_id, deleted_at=None).first()

        if not resource:
            return jsonify({"error": "Resource not found", "code": ErrorCodes.NOT_FOUND.value}), 404

        if not resource.profile_picture_file_id:
            return jsonify({"error": "No file attached", "code": ErrorCodes.NOT_FOUND.value}), 404

        client = UploadsInternalClient()
        upload_info = client.get_upload_info(str(resource.profile_picture_file_id))

        if upload_info is None:
            return jsonify({"error": "File not available", "code": ErrorCodes.NOT_FOUND.value}), 404

        return redirect(upload_info["url"])
```

### 6.3 Upload lato server (backend-to-storage)

Quando il file viene generato dal backend (es. export CSV, generazione PDF), il flusso è:

1. Il backend genera il file localmente (temp directory)
2. Richiede una presigned URL al servizio uploads tramite `UploadsInternalClient().get_presigned_url()`
3. Carica il file sull'object storage tramite PUT sulla presigned URL
4. Conferma l'upload tramite `UploadsInternalClient().confirm_upload()`
5. Elimina il file locale
6. Salva l'`upload_id` nel record

La logica di upload lato server va incapsulata in una funzione dedicata nel modulo di competenza (es. `app/exports/csv/service.py`). Non esiste una funzione condivisa globale: ogni funzionalità gestisce il proprio flusso perché le specifiche (content type, file type, cleanup, record da aggiornare) variano.

#### Definizione della funzione di upload

```python
# Built-in
import os
import logging

# Third-party
import requests

# Services
from app.services.internal.uploads import UploadsInternalClient


def upload_csv_to_storage(file_path: str, filename: str, user_id: str) -> dict:
    """
    Carica un file CSV generato localmente sull'object storage tramite il servizio uploads.

    Flusso: presigned URL → PUT file → confirm upload

    Returns:
        Upload data dict (con id, file_path, ecc.)

    Raises:
        RuntimeError: se uno dei passi del flusso fallisce
    """
    client = UploadsInternalClient()

    # Step 1: Richiede presigned URL
    upload_data = client.get_presigned_url(
        file_name=filename,
        content_type="text/csv",
        content_length=os.path.getsize(file_path),
        user_id=user_id,
        is_public=False,
        file_type="CSV_EXPORT",
    )

    if upload_data is None:
        raise RuntimeError("Failed to obtain presigned URL from uploads service")

    # Step 2: Carica il file sull'object storage
    with open(file_path, "rb") as f:
        response = requests.put(
            upload_data["presigned_url"],
            data=f,
            headers={"Content-Type": "text/csv"},
            timeout=300,
        )
    response.raise_for_status()

    # Step 3: Conferma l'upload
    if client.confirm_upload(upload_data["id"]) is None:
        raise RuntimeError(f"Failed to confirm upload {upload_data['id']}")

    return upload_data
```

#### Utilizzo nel servizio (esempio: generazione CSV)

```python
# Built-in
import os
import logging
from datetime import datetime, timezone

# dFlango
from dflango.db import db

# Models
from app.models.export_download import ExportDownload

# Constants
from app.constants.export_status import ExportStatus

# Exports
from app.exports.csv.storage import generate_and_save_csv


def generate_csv_export(export: ExportDownload) -> None:
    # ... generazione queryset e filename ...

    written_rows, file_size = generate_and_save_csv(
        schema=schema,
        queryset=queryset,
        export=export,
        filename=filename,
    )

    local_file_path = os.path.join(Config.EXPORT_STORAGE_PATH, str(export.id), filename)

    # Carica su object storage
    upload_data = upload_csv_to_storage(
        file_path=local_file_path,
        filename=filename,
        user_id=str(export.requested_by_user_id),
    )

    # Cleanup locale
    try:
        os.remove(local_file_path)
        parent_dir = os.path.dirname(local_file_path)
        if not os.listdir(parent_dir):
            os.rmdir(parent_dir)
    except OSError as e:
        logging.warning(f"Could not clean up local export file: {e}")

    # Aggiorna il record
    export.status = ExportStatus.COMPLETED
    export.upload_id = upload_data["id"]
    export.file_path = upload_data.get("file_path")
    export.file_size_bytes = file_size
    export.processed_rows = written_rows
    export.completed_at = datetime.now(timezone.utc)
    db.session.commit()
```

---

## 7) API del Servizio Uploads — Riferimento

### 7.1 Autenticazione

Tutte le API interne del servizio uploads richiedono l'header:

```
X-Internal-Token: <INTERNAL_API_SECRET>
```

**Nota:** il servizio uploads astrae il backend di storage (GCS, MinIO, S3-compatible). I microservizi chiamanti non devono assumere quale provider sia in uso.

### 7.2 Endpoint disponibili

#### Generazione presigned URL per upload

```
PUT /api/uploads/internal/presigned-url/
POST /api/uploads/internal/presigned-url/
```

**Request body:**

```json
{
  "user_id": "uuid-dell-utente",
  "is_public": false,
  "file_type": "PROFILE_PICTURE",
  "files": [
    {
      "file_name": "photo.jpg",
      "content_type": "image/jpeg",
      "content_length": 102400
    }
  ]
}
```

**Response (200/201):**

```json
{
  "uploads": [
    {
      "id": "uuid-dell-upload",
      "file_name": "photo.jpg",
      "file_path": "user-uuid/upload-uuid.jpg",
      "file_type": "PROFILE_PICTURE",
      "mime_type": "image/jpeg",
      "is_public": false,
      "created_at": "2026-01-01T00:00:00",
      "uploaded_at": null,
      "presigned_url": "https://<storage-endpoint>/bucket/..."
    }
  ]
}
```

#### Conferma upload

```
POST /api/uploads/internal/<file_id>/
PUT /api/uploads/internal/<file_id>/
```

**Response (200):**

```json
{
  "id": "uuid-dell-upload",
  "file_name": "photo.jpg",
  "file_path": "user-uuid/upload-uuid.jpg",
  "file_type": "PROFILE_PICTURE",
  "mime_type": "image/jpeg",
  "is_public": false,
  "created_at": "2026-01-01T00:00:00",
  "uploaded_at": "2026-01-01T00:00:05"
}
```

#### Recupero URL download

```
GET /api/uploads/internal/<file_id>/
```

**Response (200):**

```json
{
  "id": "uuid-dell-upload",
  "file_name": "photo.jpg",
  "file_path": "user-uuid/upload-uuid.jpg",
  "file_type": "PROFILE_PICTURE",
  "mime_type": "image/jpeg",
  "is_public": false,
  "url": "https://<storage-endpoint>/bucket/...",
  "expires_in": 3600
}
```

**Note:** `expires_in` è presente solo per file privati (`is_public: false`).

---

## 8) Test — Mock del servizio uploads

### 8.1 Fixture per mock del client

Nei test, il servizio uploads non è disponibile. Usare `unittest.mock.patch` per mockare il client:

```python
# Built-in
from unittest.mock import patch, MagicMock

# Third-party
import pytest


@pytest.fixture
def mock_uploads_client():
    """Mock UploadsInternalClient per i test."""
    with patch("app.services.internal.uploads.UploadsInternalClient") as MockClient:
        instance = MockClient.return_value
        instance.get_upload_info.return_value = {
            "id": "00000000-0000-0000-0000-000000000099",
            "file_name": "test-file.jpg",
            "file_path": "user-uuid/file-uuid.jpg",
            "file_type": "PROFILE_PICTURE",
            "mime_type": "image/jpeg",
            "is_public": False,
            "url": "https://storage.example.com/mock-presigned-url",
            "expires_in": 3600,
        }
        instance.get_presigned_url.return_value = {
            "id": "00000000-0000-0000-0000-000000000099",
            "file_name": "test-file.jpg",
            "file_path": "user-uuid/file-uuid.jpg",
            "presigned_url": "https://storage.example.com/mock-upload-url",
        }
        instance.confirm_upload.return_value = {
            "id": "00000000-0000-0000-0000-000000000099",
            "file_name": "test-file.jpg",
            "uploaded_at": "2026-01-01T00:00:05",
        }
        yield instance


@pytest.fixture
def mock_uploads_client_unavailable():
    """Mock UploadsInternalClient che simula servizio irraggiungibile."""
    with patch("app.services.internal.uploads.UploadsInternalClient") as MockClient:
        instance = MockClient.return_value
        instance.get_upload_info.return_value = None
        instance.get_presigned_url.return_value = None
        instance.confirm_upload.return_value = None
        yield instance
```

### 8.2 Esempio test con file field

```python
import uuid


class TestResourceUpdate:
    """Test per PUT /api/<service>/resources/<uuid>/"""

    def test_update_with_profile_picture(self, client, auth_headers, session, mock_uploads_client):
        resource = Resource(name="Test")
        session.add(resource)
        session.commit()

        file_id = "00000000-0000-0000-0000-000000000099"
        response = client.put(
            f"/api/<service>/resources/{resource.id}/",
            json={"profile_picture": file_id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["profile_picture"] == "https://storage.example.com/mock-presigned-url"

    def test_update_remove_profile_picture(self, client, auth_headers, session, mock_uploads_client):
        resource = Resource(
            name="Test",
            profile_picture_file_id=uuid.uuid4(),
            profile_picture_file_path="user/file.jpg",
        )
        session.add(resource)
        session.commit()

        response = client.put(
            f"/api/<service>/resources/{resource.id}/",
            json={"profile_picture": None},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["profile_picture"] is None

    def test_update_with_invalid_file_id(self, client, auth_headers, session, mock_uploads_client_unavailable):
        resource = Resource(name="Test")
        session.add(resource)
        session.commit()

        response = client.put(
            f"/api/<service>/resources/{resource.id}/",
            json={"profile_picture": str(uuid.uuid4())},
            headers=auth_headers,
        )

        assert response.status_code == 400
```

### 8.3 Posizionamento del mock path

Il path del mock deve corrispondere a dove il client viene **importato**, non dove è definito:

```python
# Se lo schema importa con:
# from app.services.internal.uploads import UploadsInternalClient

# Il mock path sarà:
@patch("app.schemas.resource.resource_update.UploadsInternalClient")
```

Oppure usare la fixture globale nel `conftest.py` se il mock è usato frequentemente.

---

## 9) Riepilogo convenzioni

| Aspetto            | Convenzione                                                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Posizione client   | `app/services/internal/uploads.py`                                                                                               |
| Classe client      | `UploadsInternalClient`                                                                                                          |
| Campi model        | `<nome>_file_id` (UUID) + `<nome>_file_path` (String)                                                                            |
| Campo schema read  | `fields.Method("get_<nome>_url")` → restituisce URL firmato                                                                      |
| Campo schema write | `fields.UUID(allow_none=True, load_only=True)` + `@validates` + `@post_load`                                                     |
| Validazione write  | Chiama `get_upload_info()` per verificare esistenza file                                                                         |
| Download endpoint  | Redirect alla presigned URL ottenuta dal servizio uploads                                                                        |
| Upload frontend    | Presigned URL flow: chiedi URL → upload diretto su object storage → invia UUID                                                   |
| Upload backend     | Funzione dedicata nel modulo di competenza: presigned URL → PUT su object storage → confirm → cleanup locale → salva `upload_id` |
| File type          | Stringa libera in `UPPER_SNAKE_CASE`, semantica a discrezione del microservizio                                                  |
| View presigned URL | `BasePresignedUploadView` in `app/views/mixins/presigned_upload.py`, estesa per entità                                           |
| Test               | Mock di `UploadsInternalClient` con `unittest.mock.patch`                                                                        |
| Error handling     | Il client restituisce `None` in caso di errore, mai eccezioni                                                                    |
| Dipendenza docker  | `uploads: condition: service_started`                                                                                            |
| Config             | `UPLOADS_INTERNAL_API_URL` + `INTERNAL_API_SECRET`                                                                               |
