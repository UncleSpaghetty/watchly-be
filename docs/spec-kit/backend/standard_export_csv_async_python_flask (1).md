# Standard tecnico per Export CSV asincroni in Python/Flask

## 1. Obiettivo

Questo documento definisce uno standard riutilizzabile per implementare export CSV nei backend Python basati su Flask e su un framework interno ispirato a Django, con pattern `model`, `schema`, `view`.

L’obiettivo è consentire a un agente AI o a uno sviluppatore di aggiungere un nuovo export CSV seguendo sempre la stessa architettura:

- richiesta asincrona da API HTTP;
- pubblicazione del job su Pub/Sub;
- generazione CSV in background;
- caricamento su Google Cloud Storage;
- salvataggio di un record nella tabella dei download;
- notifica email a fine generazione;
- download successivo da parte dell’utente tramite lista file generati.

## 2. Principi architetturali

### 2.1 Nessun CSV generato nella request HTTP

La request HTTP non deve mai generare direttamente il file CSV.

La view deve:

1. validare input, filtri e permessi;
2. creare un record `ExportDownload` in stato `QUEUED`;
3. pubblicare direttamente un messaggio Pub/Sub contenente l’identificativo dell’export;
4. restituire una risposta immediata al client solo se il publish Pub/Sub è andato a buon fine.

Se la pubblicazione del messaggio Pub/Sub fallisce, la chiamata API deve restituire errore. In questo caso l’utente dovrà richiedere nuovamente il download.

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
            Order.objects
            .filter(tenant_id=context.tenant_id)
            .filter_by_export_filters(context.filters)
            .select_related("customer")
            .only("id", "created_at", "total_amount", "customer__email")
        )
```

Lo schema deve essere l’unico punto in cui sono definiti:

- colonne esportate;
- intestazioni CSV;
- formattazione valori;
- query di estrazione;
- batch size consigliata;
- naming del file;
- eventuali regole di autorizzazione specifiche.

## 3. Modello dati consigliato

### 3.1 Tabella `export_downloads`

Esempio concettuale:

```python
class ExportDownload(Model):
    id: UUID
    export_type: str
    status: str

    requested_by_user_id: UUID
    tenant_id: UUID | None

    filters_json: dict
    filename: str | None

    total_rows: int | None
    processed_rows: int

    gcs_bucket: str | None
    gcs_object_path: str | None
    file_size_bytes: int | None
    content_type: str

    error_code: str | None
    error_message: str | None

    attempts: int
    locked_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None

    created_at: datetime
    updated_at: datetime
```

### 3.2 Stati standard

Usare un set chiuso di stati:

```python
class ExportStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

Regole:

- `QUEUED`: richiesta ricevuta, job non ancora iniziato;
- `RUNNING`: worker in esecuzione;
- `COMPLETED`: file generato e disponibile;
- `FAILED`: errore definitivo;
- `CANCELLED`: export annullato manualmente o da sistema.

## 4. Contratto API lato Flask

### 4.1 Richiesta export

Endpoint consigliato:

```http
POST /api/export-downloads/<export_type>
```

I filtri vengono passati come **query parameters** (stesso formato usato dalle tabelle/liste), non nel body della richiesta:

```http
POST /api/export-downloads/orders_csv?date_from=2026-01-01&date_to=2026-01-31&status=paid
```

Il body della richiesta è vuoto (o assente). I parametri riservati per paginazione e ordinamento (`page`, `per_page`, `sort`, `sort_field`, `sort_order`) vengono ignorati dalla view.

Risposta:

```json
{
  "id": "export-download-uuid",
  "export_type": "orders_csv",
  "status": "queued"
}
```

### 4.2 Lista download dell’utente

```http
GET /api/export-downloads
```

Risposta:

```json
{
  "results": [
    {
      "id": "uuid",
      "export_type": "orders_csv",
      "filename": "orders_2026-01-01_2026-01-31.csv",
      "status": "completed",
      "total_rows": 10000,
      "processed_rows": 10000,
      "created_at": "2026-05-07T10:00:00Z",
      "completed_at": "2026-05-07T10:02:10Z"
    }
  ]
}
```

### 4.3 Download file

Endpoint consigliato:

```http
GET /api/export-downloads/<id>/download-url
```

La risposta può essere una signed URL temporanea:

```json
{
  "url": "https://storage.googleapis.com/...",
  "expires_in_seconds": 300
}
```

Il backend deve verificare che l’utente possa accedere al record prima di restituire la signed URL.

## 5. Schema CSV standard

### 5.1 Field descriptor

```python
from dataclasses import dataclass
from typing import Any, Callable

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
```

### 5.2 Base schema

```python
class CSVExportSchema:
    export_type: str
    filename_prefix: str
    fields: list[CSVField]
    batch_size: int = 2000
    delimiter: str = ","
    encoding: str = "utf-8"
    include_bom: bool = False

    def validate_filters(self, filters: dict) -> dict:
        return filters

    def check_permissions(self, context: "ExportContext") -> None:
        pass

    def get_queryset(self, context: "ExportContext"):
        raise NotImplementedError

    def get_filename(self, context: "ExportContext") -> str:
        timestamp = context.requested_at.strftime("%Y%m%d_%H%M%S")
        return f"{self.filename_prefix}_{timestamp}.csv"

    def get_headers(self) -> list[str]:
        return [field.header for field in self.fields]

    def serialize_row(self, obj) -> list[str]:
        return [sanitize_csv_value(field.get_value(obj)) for field in self.fields]
```

### 5.3 Registry degli export

```python
class CSVExportRegistry:
    _schemas: dict[str, type[CSVExportSchema]] = {}

    @classmethod
    def register(cls, schema_cls: type[CSVExportSchema]):
        cls._schemas[schema_cls.export_type] = schema_cls
        return schema_cls

    @classmethod
    def get(cls, export_type: str) -> CSVExportSchema:
        schema_cls = cls._schemas.get(export_type)
        if not schema_cls:
            raise UnknownExportType(export_type)
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

### 6.1 View Flask

```python
@app.post("/api/export-downloads/<export_type>")
def request_csv_export(export_type: str):
    user = get_current_user()
    raw_filters = {k: v for k, v in request.args.items() if k not in ("page", "per_page", "sort", "sort_field", "sort_order")}

    schema = CSVExportRegistry.get(export_type)
    filters = schema.validate_filters(raw_filters)

    context = ExportContext(
        user=user,
        tenant_id=user.tenant_id,
        filters=filters,
        requested_at=utcnow(),
    )
    schema.check_permissions(context)

    export_download = ExportDownload.create(
        export_type=export_type,
        status=ExportStatus.QUEUED,
        requested_by_user_id=user.id,
        tenant_id=user.tenant_id,
        filters_json=filters,
        processed_rows=0,
        attempts=0,
        content_type="text/csv",
    )

    try:
        publish_csv_export_requested(
            export_download_id=str(export_download.id),
            export_type=export_type,
        )
    except Exception as exc:
        export_download.status = ExportStatus.FAILED
        export_download.error_code = exc.__class__.__name__
        export_download.error_message = "Unable to publish CSV export request to Pub/Sub"
        export_download.failed_at = utcnow()
        export_download.save()

        return jsonify({
            "error": "csv_export_publish_failed",
            "message": "Impossibile avviare la generazione del CSV. Riprovare più tardi.",
        }), 500

    return jsonify({
        "id": str(export_download.id),
        "export_type": export_type,
        "status": export_download.status,
    }), 202
```

### 6.2 Publish Pub/Sub diretto dalla API

La pubblicazione del messaggio Pub/Sub avviene direttamente durante la chiamata API.

Il flusso è intenzionalmente semplice:

1. la API crea il record `ExportDownload`;
2. la API pubblica il messaggio Pub/Sub;
3. se il publish riesce, la API restituisce `202 Accepted`;
4. se il publish fallisce, la API restituisce errore e l’utente dovrà richiedere nuovamente il download.

Non è previsto, in questa versione dello standard, un outbox pattern o un job separato di dispatch degli eventi.

Esempio di funzione di publish:

```python
import json
from google.cloud import pubsub_v1

publisher = pubsub_v1.PublisherClient()


def publish_csv_export_requested(export_download_id: str, export_type: str) -> str:
    topic_path = publisher.topic_path(
        settings.GCP_PROJECT_ID,
        settings.CSV_EXPORT_PUBSUB_TOPIC,
    )

    payload = {
        "event_type": "csv_export_requested",
        "export_download_id": export_download_id,
        "export_type": export_type,
    }

    future = publisher.publish(
        topic_path,
        json.dumps(payload).encode("utf-8"),
        event_type="csv_export_requested",
        export_type=export_type,
    )

    return future.result(timeout=settings.CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS)
```

## 7. Worker di generazione CSV

### 7.1 Tecnologia da utilizzare

La generazione dei CSV deve essere eseguita da un worker dedicato, separato dal processo HTTP Flask.

Tecnologie consigliate:

- Python, usando lo stesso codebase del backend Flask;
- `google-cloud-pubsub` per consumare messaggi da una Pub/Sub pull subscription;
- `google-cloud-storage` per scrivere il file CSV su GCS;
- lo stesso ORM/framework interno già usato dal backend per accedere a `model`, `schema` e `view`;
- un entrypoint Python dedicato, ad esempio `python -m app.workers.csv_export_worker`.

Non è necessario introdurre Celery se Pub/Sub è già lo standard di messaging del progetto.

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

Questo protegge:

- database;
- memoria;
- CPU;
- connessioni GCS;
- backend API principale.

### 7.3 Variabili di configurazione

Definire variabili dedicate per il worker:

```python
GCP_PROJECT_ID = "my-project"
CSV_EXPORT_PUBSUB_TOPIC = "csv-export-requested"
CSV_EXPORT_PUBSUB_SUBSCRIPTION = "csv-export-requested-worker-sub"
CSV_EXPORT_BUCKET_NAME = "my-export-bucket"

CSV_EXPORT_DEFAULT_BATCH_SIZE = 2000
CSV_EXPORT_MAX_CONCURRENT_WORKERS = 2
CSV_EXPORT_MAX_MESSAGES = CSV_EXPORT_MAX_CONCURRENT_WORKERS
CSV_EXPORT_MAX_ATTEMPTS = 3
CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS = 10
CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30
CSV_EXPORT_SIGNED_URL_TTL_SECONDS = 300
```

In produzione partire con una concorrenza conservativa, ad esempio `2`, e aumentare solo dopo performance test.

### 7.4 Subscription Pub/Sub

Creare un topic e una pull subscription dedicati:

```bash
gcloud pubsub topics create csv-export-requested

gcloud pubsub subscriptions create csv-export-requested-worker-sub \
  --topic=csv-export-requested \
  --ack-deadline=600 \
  --max-delivery-attempts=5 \
  --dead-letter-topic=csv-export-dead-letter
```

Creare anche la dead letter topic:

```bash
gcloud pubsub topics create csv-export-dead-letter
```

La dead letter topic serve a raccogliere messaggi che non possono essere processati dopo vari tentativi.

### 7.5 Struttura consigliata del codice

Struttura indicativa:

```text
app/
  exports/
    csv/
      fields.py
      schemas.py
      registry.py
      service.py
      storage.py
      pubsub.py
  workers/
    csv_export_worker.py
```

Responsabilità:

- `fields.py`: definizione `CSVField` e formatter comuni;
- `schemas.py`: classi concrete di export CSV;
- `registry.py`: registry degli schema;
- `service.py`: logica applicativa di generazione CSV;
- `storage.py`: funzioni di upload/finalizzazione GCS;
- `pubsub.py`: funzioni di publish e parsing messaggi;
- `csv_export_worker.py`: entrypoint del worker.

### 7.6 Entrypoint del worker

Esempio:

```python
# app/workers/csv_export_worker.py

import json
import logging
import signal
from google.cloud import pubsub_v1

logger = logging.getLogger(__name__)


def main():
    configure_app_context()
    start_csv_export_worker()


def start_csv_export_worker():
    subscriber = pubsub_v1.SubscriberClient()

    subscription_path = subscriber.subscription_path(
        settings.GCP_PROJECT_ID,
        settings.CSV_EXPORT_PUBSUB_SUBSCRIPTION,
    )

    flow_control = pubsub_v1.types.FlowControl(
        max_messages=settings.CSV_EXPORT_MAX_MESSAGES,
        max_bytes=100 * 1024 * 1024,
    )

    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=handle_pubsub_message,
        flow_control=flow_control,
    )

    logger.info("CSV export worker started", extra={
        "subscription": subscription_path,
        "max_messages": settings.CSV_EXPORT_MAX_MESSAGES,
    })

    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        streaming_pull_future.result(timeout=settings.CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS)


def handle_pubsub_message(message):
    try:
        payload = json.loads(message.data.decode("utf-8"))

        if payload.get("event_type") != "csv_export_requested":
            message.ack()
            return

        handle_csv_export_requested(payload)
        message.ack()

    except RetryableCSVExportError as exc:
        logger.warning("Retryable CSV export error", exc_info=exc)
        message.nack()

    except Exception as exc:
        logger.exception("Non retryable CSV export error")
        mark_export_as_failed_from_message(message=message, exc=exc)
        message.ack()


if __name__ == "__main__":
    main()
```

### 7.7 Handler applicativo

Il worker deve delegare la logica applicativa a un service testabile:

```python
def handle_csv_export_requested(payload: dict):
    export_id = payload["export_download_id"]
    export_type = payload["export_type"]

    export = acquire_export_lock(export_id)

    if export is None:
        return

    if export.export_type != export_type:
        raise NonRetryableCSVExportError(
            f"Export type mismatch: expected {export.export_type}, got {export_type}"
        )

    try:
        generate_csv_export(export)

    except RetryableCSVExportError:
        release_export_lock(export.id)
        raise

    except Exception as exc:
        mark_export_failed(export.id, exc)
        raise
```

### 7.8 Pseudocodice generazione CSV

```python
def generate_csv_export(export: ExportDownload) -> None:
    schema = CSVExportRegistry.get(export.export_type)

    context = ExportContext.from_export_download(export)
    schema.check_permissions(context)

    queryset = schema.get_queryset(context)

    total_rows = safe_count(queryset)
    export.total_rows = total_rows
    export.save(update_fields=["total_rows"])

    filename = schema.get_filename(context)
    temp_object_path = f"exports/tmp/{export.id}/{filename}"
    final_object_path = f"exports/{export.tenant_id}/{export.id}/{filename}"

    written_rows, file_size = generate_and_upload_csv_streaming(
        schema=schema,
        queryset=queryset,
        export=export,
        bucket_name=settings.CSV_EXPORT_BUCKET_NAME,
        object_path=temp_object_path,
    )

    finalize_gcs_object(
        bucket_name=settings.CSV_EXPORT_BUCKET_NAME,
        temp_object_path=temp_object_path,
        final_object_path=final_object_path,
    )

    export.status = ExportStatus.COMPLETED
    export.filename = filename
    export.gcs_bucket = settings.CSV_EXPORT_BUCKET_NAME
    export.gcs_object_path = final_object_path
    export.processed_rows = written_rows
    export.file_size_bytes = file_size
    export.completed_at = utcnow()
    export.save()

    send_export_ready_email(export)
```

### 7.9 Lock e idempotenza del worker

Pub/Sub può consegnare lo stesso messaggio più di una volta. Il worker deve quindi essere idempotente.

```python
def acquire_export_lock(export_id: UUID) -> ExportDownload | None:
    with db.transaction():
        export = ExportDownload.get_for_update(export_id)

        if export.status == ExportStatus.COMPLETED:
            return None

        if export.status == ExportStatus.RUNNING and not export.lock_is_expired():
            return None

        if export.status not in {
            ExportStatus.QUEUED,
            ExportStatus.FAILED,
        }:
            return None

        if export.attempts >= settings.CSV_EXPORT_MAX_ATTEMPTS:
            return None

        export.status = ExportStatus.RUNNING
        export.locked_at = utcnow()
        export.started_at = export.started_at or utcnow()
        export.attempts += 1
        export.save(update_fields=["status", "locked_at", "started_at", "attempts"])

        return export
```

Regole:

- `COMPLETED`: il worker non fa nulla e fa ack del messaggio;
- `RUNNING` con lock valido: il worker non fa nulla e fa ack del messaggio;
- `QUEUED`: il worker acquisisce il lock e processa;
- `FAILED` con attempts disponibili: può essere ritentato;
- attempts esauriti: il worker lascia il record in `FAILED` e fa ack.

### 7.10 Modifiche al Dockerfile

In genere non serve un Dockerfile separato. Il worker può usare la stessa immagine del backend Flask, cambiando solo il comando di avvio.

Esempio Dockerfile unico:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "app.main:create_app()", "--bind", "0.0.0.0:8000"]
```

Il servizio API userà il comando Gunicorn, mentre il worker userà:

```bash
python -m app.workers.csv_export_worker
```

### 7.11 Modifiche a Docker Compose

Aggiungere un servizio dedicato al worker.

Esempio:

```yaml
services:
  api:
    build: .
    command: gunicorn "app.main:create_app()" --bind 0.0.0.0:8000
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db

  csv-export-worker:
    build: .
    command: python -m app.workers.csv_export_worker
    env_file:
      - .env
    depends_on:
      - db
    restart: unless-stopped
```

Se in locale si usa il Pub/Sub emulator, aggiungere anche:

```yaml
  pubsub-emulator:
    image: google/cloud-sdk:latest
    command: >
      gcloud beta emulators pubsub start
      --host-port=0.0.0.0:8085
    ports:
      - "8085:8085"
```

E configurare nel `.env`:

```env
PUBSUB_EMULATOR_HOST=pubsub-emulator:8085
GCP_PROJECT_ID=local-project
CSV_EXPORT_PUBSUB_TOPIC=csv-export-requested
CSV_EXPORT_PUBSUB_SUBSCRIPTION=csv-export-requested-worker-sub
CSV_EXPORT_BUCKET_NAME=local-or-dev-export-bucket
CSV_EXPORT_MAX_CONCURRENT_WORKERS=2
CSV_EXPORT_MAX_MESSAGES=2
```

In locale può essere necessario creare topic e subscription all’avvio tramite script dedicato:

```bash
python -m scripts.setup_pubsub_local
```

### 7.12 Deployment in produzione

In produzione il worker deve essere deployato come servizio/processo separato dal backend API.

Opzioni possibili:

- container separato nello stesso cluster;
- deployment Kubernetes dedicato;
- servizio Cloud Run worker-like con processo long-running, se compatibile con il runtime scelto;
- VM o process manager dedicato, ad esempio systemd o supervisor.

Raccomandazioni:

- scalare il worker separatamente dall’API;
- impostare limiti CPU e RAM dedicati;
- partire con pochi worker concorrenti;
- aumentare `CSV_EXPORT_MAX_CONCURRENT_WORKERS` solo dopo test reali;
- monitorare durata export, memoria, errori, retry e dimensione della coda Pub/Sub.

### 7.13 Osservabilità

Il worker deve produrre log strutturati con almeno:

- `export_download_id`;
- `export_type`;
- `status`;
- `processed_rows`;
- `total_rows`;
- durata generazione;
- dimensione file;
- errore, se presente.

Metriche consigliate:

- numero export `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`;
- durata media export;
- righe processate al secondo;
- memoria massima usata dal worker;
- numero retry Pub/Sub;
- messaggi nella dead letter topic;
- lag della subscription.

## 8. Strategia efficiente per dataset grandi

### 8.1 Queryset da 100k righe: è pesante?

Dipende da cosa si intende per “ottenere il queryset”.

Non è un problema creare un oggetto queryset lazy che rappresenta la query. È invece un problema materializzarlo tutto in memoria, ad esempio con:

```python
rows = list(queryset)
```

oppure con pattern equivalenti che caricano 100k oggetti ORM contemporaneamente.

Per export grandi bisogna iterare a batch, mantenendo in memoria solo un blocco limitato di righe.

### 8.2 Count del queryset

Il `count()` può essere utile per mostrare avanzamento e stimare durata, ma non è sempre gratuito.

Su tabelle grandi, filtri complessi o join pesanti, `COUNT(*)` può essere costoso. Lo standard consigliato è:

- eseguire `count()` solo se ragionevolmente sostenibile;
- imporre timeout alla query di count, se supportato;
- consentire `total_rows = None` se il count fallisce o supera una soglia;
- non bloccare l’export solo perché il count non è disponibile.

```python
def safe_count(queryset) -> int | None:
    try:
        return queryset.count()
    except QueryTimeout:
        return None
```

### 8.3 Evitare offset pagination per export grandi

Evitare questo pattern per dataset grandi:

```python
for offset in range(0, total_rows, batch_size):
    batch = queryset[offset:offset + batch_size]
```

Su molte basi dati, offset grandi diventano progressivamente più lenti perché il database deve comunque scorrere le righe precedenti.

Preferire keyset pagination quando possibile:

```python
def iterate_queryset_by_pk(queryset, batch_size: int):
    last_pk = None

    while True:
        batch_qs = queryset.order_by("id")

        if last_pk is not None:
            batch_qs = batch_qs.filter(id__gt=last_pk)

        batch = list(batch_qs[:batch_size])

        if not batch:
            break

        for obj in batch:
            yield obj

        last_pk = batch[-1].id
```

Requisiti:

- ordinamento stabile;
- colonna indicizzata;
- preferibilmente primary key monotona;
- attenzione se l’export richiede un ordinamento business diverso.

### 8.4 Alternative: server-side cursor / iterator

Se il framework ORM lo supporta, si può usare un iterator/cursor lato database:

```python
for obj in queryset.iterator(chunk_size=schema.batch_size):
    yield obj
```

Questo pattern è spesso più semplice, ma dipende dal comportamento dell’ORM e dal driver DB.

Lo standard deve supportare entrambe le strategie:

- `keyset pagination` come default robusto;
- `server-side cursor` quando disponibile e testato.

### 8.5 Evitare N+1 query

Ogni schema deve ottimizzare la query usando strumenti equivalenti a:

- `select_related` per relazioni many-to-one / one-to-one;
- `prefetch_related` per relazioni one-to-many / many-to-many, con cautela;
- `only` / `defer` / projection per caricare solo i campi necessari;
- query annotate per valori calcolati lato DB.

Un export di 100k righe con N+1 query può diventare ingestibile anche se il CSV writer è efficiente.

## 9. Scrittura CSV e upload su GCS

### 9.1 Non aggiornare l’oggetto GCS a ogni batch

Google Cloud Storage è object storage: non va trattato come un filesystem append-only tradizionale.

L’approccio “creo un CSV vuoto e lo aggiorno sul bucket a ogni batch” non è consigliato, perché rischia di:

- generare molte operazioni remote;
- complicare retry e consistenza;
- aumentare latenza;
- non dare veri vantaggi sulla RAM.

Approcci consigliati:

1. scrittura streaming direttamente verso GCS, con buffer controllato;
2. scrittura su file temporaneo locale e upload finale;
3. per file enormi, chunk temporanei su GCS e compose finale, solo se davvero necessario.

Per 100k righe, di solito lo streaming diretto o il file temporaneo locale sono sufficienti.

### 9.2 Streaming diretto verso GCS

Pseudocodice:

```python
import csv
import io
from google.cloud import storage


def generate_and_upload_csv_streaming(schema, queryset, export, bucket_name, object_path):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)
    blob.content_type = "text/csv; charset=utf-8"

    written_rows = 0

    with blob.open("wb", chunk_size=8 * 1024 * 1024) as binary_stream:
        text_stream = io.TextIOWrapper(
            binary_stream,
            encoding=schema.encoding,
            newline="",
            write_through=True,
        )

        if schema.include_bom:
            text_stream.write("\ufeff")

        writer = csv.writer(
            text_stream,
            delimiter=schema.delimiter,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

        writer.writerow(schema.get_headers())

        for obj in iterate_export_queryset(queryset, schema.batch_size):
            writer.writerow(schema.serialize_row(obj))
            written_rows += 1

            if written_rows % schema.batch_size == 0:
                update_export_progress(export.id, written_rows)

        text_stream.flush()

    file_size = get_gcs_object_size(bucket_name, object_path)
    return written_rows, file_size
```

Questo approccio non mantiene il CSV completo in RAM.

### 9.3 File temporaneo locale

È un’alternativa valida se il worker dispone di disco temporaneo sufficiente.

```python
import csv
import tempfile


def generate_csv_to_tempfile_then_upload(schema, queryset, export):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", suffix=".csv") as tmp:
        writer = csv.writer(tmp, delimiter=schema.delimiter, lineterminator="\n")
        writer.writerow(schema.get_headers())

        written_rows = 0

        for obj in iterate_export_queryset(queryset, schema.batch_size):
            writer.writerow(schema.serialize_row(obj))
            written_rows += 1

            if written_rows % schema.batch_size == 0:
                update_export_progress(export.id, written_rows)

        tmp.flush()
        upload_file_to_gcs(tmp.name, bucket_name=EXPORT_BUCKET_NAME, object_path=final_object_path)

    return written_rows
```

Vantaggi:

- semplice da debuggare;
- upload atomico dopo generazione locale;
- retry più prevedibile.

Svantaggi:

- richiede spazio disco;
- meno adatto a file molto grandi.

### 9.4 Path temporaneo e finalizzazione

Scrivere prima su path temporaneo:

```text
exports/tmp/<export_id>/<filename>
```

Poi finalizzare su path definitivo:

```text
exports/<tenant_id>/<export_id>/<filename>
```

In GCS la “rename” è normalmente implementata come copia + delete.

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

Esempio:

```python
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

- permessi utente;
- isolamento tenant;
- filtri consentiti;
- row-level security applicativa;
- esclusione di campi sensibili non previsti.

Il worker deve ricostruire il contesto dell’utente dal record `ExportDownload` e rieseguire i controlli principali.

Non bisogna fidarsi del fatto che la view abbia già validato tutto.

## 11. Idempotenza e retry

Pub/Sub può consegnare lo stesso messaggio più di una volta. Il worker deve quindi essere idempotente.

Regole consigliate:

- se l’export è già `COMPLETED`, il worker esce senza fare nulla;
- se l’export è `RUNNING` con lock recente, il worker esce o rilascia retry;
- se l’export è `FAILED` ma ancora entro `max_attempts`, può essere ritentato;
- usare path GCS basati su `export_id`, non su timestamp casuali;
- inviare email solo dopo transizione effettiva a `COMPLETED`.

Esempio:

```python
def acquire_export_lock(export_id: UUID) -> ExportDownload | None:
    export = ExportDownload.get_for_update(export_id)

    if export.status == ExportStatus.COMPLETED:
        return None

    if export.status == ExportStatus.RUNNING and not export.lock_is_expired():
        return None

    export.status = ExportStatus.RUNNING
    export.locked_at = utcnow()
    export.attempts += 1
    export.save()

    return export
```

## 12. Limiti e policy

Definire limiti globali configurabili:

```python
CSV_EXPORT_DEFAULT_BATCH_SIZE = 2000
CSV_EXPORT_MAX_ROWS_SYNC_COUNT = 500000
CSV_EXPORT_MAX_ATTEMPTS = 3
CSV_EXPORT_SIGNED_URL_TTL_SECONDS = 300
CSV_EXPORT_MAX_CONCURRENT_WORKERS = 2
CSV_EXPORT_MAX_MESSAGES = CSV_EXPORT_MAX_CONCURRENT_WORKERS
CSV_EXPORT_PUBLISH_TIMEOUT_SECONDS = 10
CSV_EXPORT_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30
```

Policy consigliate:

- non consentire export illimitati senza filtri su tabelle enormi;
- imporre un limite massimo di righe per alcuni export;
- richiedere intervalli data per dataset storici;
- rate limit per utente/tenant;
- quota massima di export contemporanei per tenant;
- nessuna retention automatica in questa versione dello standard;
- i CSV generati restano disponibili permanentemente;
- un eventuale sistema di cleanup dei vecchi file potrà essere progettato successivamente.

## 13. Formattazione standard

Definire formatter riutilizzabili:

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
            validated["date_from"] = parse_date(filters["date_from"])

        if "date_to" in filters:
            validated["date_to"] = parse_date(filters["date_to"])

        if "status" in filters:
            validated["status"] = validate_choice(filters["status"], ["paid", "pending", "cancelled"])

        return validated

    def check_permissions(self, context: ExportContext) -> None:
        if not context.user.has_permission("orders.export_csv"):
            raise PermissionDenied("Missing permission: orders.export_csv")

    def get_queryset(self, context: ExportContext):
        qs = Order.objects.filter(tenant_id=context.tenant_id)

        if context.filters.get("date_from"):
            qs = qs.filter(created_at__gte=context.filters["date_from"])

        if context.filters.get("date_to"):
            qs = qs.filter(created_at__lt=context.filters["date_to"])

        if context.filters.get("status"):
            qs = qs.filter(status=context.filters["status"])

        return (
            qs
            .select_related("customer")
            .only("id", "created_at", "status", "total_amount", "customer__email")
            .order_by("id")
        )
```

## 15. Istruzioni operative per un agente AI

Quando viene richiesto di implementare un nuovo export CSV, l’agente deve seguire questi passaggi.

### 15.1 Creare lo schema

Creare una classe che estende `CSVExportSchema`.

La classe deve definire:

- `export_type` univoco;
- `filename_prefix`;
- `fields`;
- `validate_filters`;
- `check_permissions`;
- `get_queryset`.

### 15.2 Ottimizzare la query

La query deve:

- filtrare sempre per tenant o contesto applicativo equivalente;
- applicare solo filtri validati;
- ordinare per chiave stabile;
- evitare N+1 query;
- caricare solo i campi necessari;
- non materializzare l’intero dataset.

### 15.3 Registrare lo schema

Registrare la classe nel registry:

```python
@CSVExportRegistry.register
class MyExportSchema(CSVExportSchema):
    ...
```

### 15.4 Non creare endpoint custom se non necessario

L’export deve usare l’endpoint standard:

```http
POST /api/export-downloads/<export_type>
```

Creare endpoint custom solo se esistono requisiti business specifici non coperti dallo standard.

### 15.5 Non generare il CSV nella view

È vietato generare il CSV nella request HTTP.

La view deve solo creare il record e accodare il job.

### 15.6 Non salvare il CSV completo in memoria

È vietato usare pattern come:

```python
rows = list(queryset)
csv_content = "..."
```

oppure costruire l’intero CSV in una stringa unica.

Usare sempre streaming o file temporaneo.

## 16. Checklist finale per ogni export

Prima di considerare completo un export CSV verificare:

- [ ] esiste una classe `CSVExportSchema` dedicata;
- [ ] lo schema è registrato nel registry;
- [ ] i filtri sono validati;
- [ ] i permessi sono controllati;
- [ ] la query è tenant-safe;
- [ ] la query evita N+1;
- [ ] la query carica solo i campi necessari;
- [ ] l’iterazione avviene a batch;
- [ ] il CSV viene scritto in streaming o su tempfile;
- [ ] i valori sono protetti da CSV injection;
- [ ] il job è idempotente;
- [ ] il record `ExportDownload` viene aggiornato con progress e stato finale;
- [ ] il file viene caricato su GCS in path definitivo solo a generazione completata;
- [ ] viene inviata una notifica email a completamento;
- [ ] il download avviene tramite endpoint sicuro o signed URL;
- [ ] esistono test automatici.

## 17. Test consigliati

### 17.1 Unit test schema

- validazione filtri;
- headers CSV;
- serializzazione riga;
- formattazione valori nulli;
- sanitizzazione CSV injection.

### 17.2 Integration test worker

- export completato correttamente;
- export fallito con stato `FAILED`;
- retry idempotente;
- aggiornamento `processed_rows`;
- upload GCS mockato;
- email inviata una sola volta.

### 17.3 Performance test

Testare almeno:

- 10k righe;
- 100k righe;
- query con join;
- export con campi relazionali;
- memoria massima usata dal worker;
- tempo medio di generazione.

## 18. Raccomandazione finale

Il design consigliato è:

1. API Flask asincrona;
2. record `ExportDownload` persistito subito;
3. publish Pub/Sub diretto dalla API;
4. errore API se il publish Pub/Sub fallisce;
5. Pub/Sub con payload minimo;
6. worker pull dedicato e separato dal processo HTTP Flask;
7. concorrenza controllata tramite `CSV_EXPORT_MAX_CONCURRENT_WORKERS` e flow control Pub/Sub;
8. schema CSV per ogni export;
9. query lazy e iterata a batch;
10. streaming diretto verso GCS o tempfile locale;
11. update progressivo del record download;
12. finalizzazione atomica su path definitivo;
13. email di notifica a completamento;
14. disponibilità permanente del CSV generato, salvo futuri sistemi di cleanup espliciti.

Per il caso da 100k righe, non è necessario caricare tutto in memoria e non è consigliabile aggiornare il file remoto a ogni batch. È preferibile scrivere riga per riga su uno stream controllato, con flush/upload gestiti dal client GCS, aggiornando sul database solo il progresso logico dell’export.

La generazione deve essere eseguita da un worker dedicato, non da una push subscription HTTP, così il sistema può assorbire picchi di richieste mantenendo un numero massimo controllato di export concorrenti.

