# Guida pratica: Schema e API nei microservizi

## Obiettivo

Questa guida definisce lo standard completo per implementare schema di serializzazione e endpoint API in un microservizio Python/Flask con dFlango, coprendo l'intero flusso: **Schema → View → URLs → Mapping Permessi**.

Il documento è agnostico rispetto al progetto specifico ed è applicabile a qualsiasi microservizio che segua lo stack descritto.

---

## Riepilogo convenzioni

| Aspetto | Convenzione |
| --- | --- |
| **Schema** | `app/schemas/<dominio>/<risorsa>.py`, tre schema per risorsa: `Create`, `Update`, `Read` |
| **View** | `app/views/<dominio>/<risorsa>.py`, una classe per azione CRUD, `PermissionsMixin` come primo parent |
| **URLs** | `app/urls.py`, `RouteRegistry` con `urlpatterns`, path al plurale |
| **Mapping permessi** | `app/config/permissions.py`, classe `ViewPermissions` con endpoint→metodo→ruoli, risolto automaticamente dal mixin |
| **Mixin permessi** | `from dflango.mixin import PermissionsMixin` — fornito da dFlango, risolve ruoli automaticamente da `ViewPermissions` |
| **Naming route** | `/<risorsa>/` (lista), `/<risorsa>/<uuid:resource_id>/` (dettaglio) |
| **Naming view** | `<Risorsa>ListCreateView`, `<Risorsa>DetailView`, `<Risorsa>SearchView` |
| **Dominio** | Raggruppamento logico di risorse correlate (es. `staff`, `invoice`, `payment`). Usato come sotto-directory in `schemas/` e `views/` |
| **Ordine import** | Built-in → Flask → dFlango → Third-party → Models → Schemas → Constants → Utils → Services |

---

## 1) Stack tecnologico

| Componente | Tecnologia | Scopo |
| --- | --- | --- |
| Linguaggio | Python 3.12 | Runtime dei microservizi |
| Framework | Flask + dFlango | Framework web e layer CRUD |
| ORM | SQLAlchemy (via Flask-SQLAlchemy) | Persistenza e relazioni |
| Serializzazione | Marshmallow (via dFlango schemas) | Validazione input e serializzazione output |
| Database | PostgreSQL 17.2 | Database relazionale |

---

## 2) Struttura file di progetto (schema e API)

```text
apps/<microservice>/
└── app/
    ├── urls.py                  # registrazione route
    ├── config/
    │   └── permissions.py       # mapping ruoli → endpoint
    ├── schemas/
    │   ├── __init__.py
    │   └── <dominio>/
    │       ├── <risorsa>_create.py
    │       ├── <risorsa>_update.py
    │       └── <risorsa>_read.py
    ├── services/
    │   └── internal/            # client per API internal di ALTRI microservizi (copiati dai loro vendors)
    │       ├── auth.py
    │       ├── uploads.py
    │       └── export_downloads.py
    ├── vendors/
    │   └── internal/            # client di riferimento per le API internal che QUESTO microservizio espone
    │       └── {service}.py
    └── views/
        ├── __init__.py
        ├── health.py
        ├── internal/            # endpoint internal esposti
        │   └── <risorsa>.py
        ├── export/              # view export CSV
        │   ├── base_export_request.py
        │   └── <risorsa>_export.py
        └── <dominio>/
            ├── <risorsa>_list.py
            ├── <risorsa>_detail.py
            ├── <risorsa>_search.py
            └── <risorsa>_<azione>.py
```

---

## 3) Schema — Serializzazione e validazione

### 3.1 Tipi di schema

| Tipo | Quando usarlo |
| --- | --- |
| `ModelSchema` | Schema legato direttamente a un model SQLAlchemy (CRUD) |
| `Schema` | Payload non legato a model (login, token, conferme) |

### 3.2 Tre schema per risorsa

Per ogni entità dominio creare sempre:

1. **`<Risorsa>CreateSchema`** — campi richiesti in input per la creazione
2. **`<Risorsa>UpdateSchema`** — campi opzionali, validazioni unique con `context`
3. **`<Risorsa>ReadSchema`** — tutti i campi `dump_only=True`, solo output

### 3.3 Template schema

```python
# app/schemas/<dominio>/<risorsa>_create.py

# dFlango
from dflango.schemas import ModelSchema

# Third-party
from marshmallow import fields, validates, ValidationError

# Models
from app.models.resource import Resource


class ResourceCreateSchema(ModelSchema):
    """Schema per la creazione di una risorsa."""

    name = fields.String(
        required=True,
        error_messages={"required": "Name is required"},
    )
    code = fields.String(
        required=True,
        error_messages={"required": "Code is required"},
    )

    @validates("name")
    def validate_name(self, value, **kwargs):
        if len(value.strip()) < 3:
            raise ValidationError("Name must be at least 3 characters long")

    @validates("code")
    def validate_code(self, value, **kwargs):
        if Resource.query.filter_by(code=value).first():
            raise ValidationError("Code already exists")

    class Meta:
        model = Resource
```

```python
# app/schemas/<dominio>/<risorsa>_update.py

# dFlango
from dflango.schemas import ModelSchema

# Third-party
from marshmallow import fields, validates_schema, ValidationError

# Models
from app.models.resource import Resource


class ResourceUpdateSchema(ModelSchema):
    """Schema per l'aggiornamento di una risorsa."""

    name = fields.String(required=False)
    code = fields.String(required=False)

    @validates_schema
    def validate_unique_fields(self, data, **kwargs):
        if "code" in data:
            existing = Resource.query.filter_by(code=data["code"]).first()
            if existing and str(existing.id) != str(self.context.get("resource_id")):
                raise ValidationError({"code": ["Code already exists"]})

    class Meta:
        model = Resource
```

```python
# app/schemas/<dominio>/<risorsa>_read.py

# dFlango
from dflango.schemas import ModelSchema

# Third-party
from marshmallow import fields

# Models
from app.models.resource import Resource


class ResourceReadSchema(ModelSchema):
    """Schema per la lettura di una risorsa."""

    id = fields.UUID(dump_only=True)
    name = fields.String(dump_only=True)
    code = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    class Meta:
        model = Resource
```

### 3.4 Regole obbligatorie

| Regola | Dettaglio |
| --- | --- |
| `Meta.model` | Sempre presente su `ModelSchema` |
| `required=True` | Solo su campi obbligatori in `Create` |
| `dump_only=True` | Su tutti i campi di `Read` |
| `load_only=True` | Su campi sensibili (password, secret) |
| `error_messages` | Definiti sui campi critici |
| `@validates` | Per validazione singolo campo |
| `@validates_schema` | Per validazione cross-field e unique in update |
| `context` | Usato in update per escludere il record corrente dalle check unique |

### 3.5 Enum negli schema

```python
# dFlango
from dflango.schemas import EnumField

# Constants
from app.constants.resource_status import ResourceStatus

status = EnumField(ResourceStatus, required=True)
```

### 3.6 Nested schema

```python
profile = fields.Nested(ProfileReadSchema, dump_only=True)
```

Usare nested solo quando necessario. Evitare payload troppo profondi.

### 3.7 Pre-load hooks

Per normalizzazioni leggere prima della validazione:

```python
# Third-party
from marshmallow import pre_load

@pre_load
def normalize_code(self, data, **kwargs):
    if "code" in data and data["code"]:
        data["code"] = data["code"].strip().upper()
    return data
```

---

## 4) View — Endpoint API

### 4.1 Classi view disponibili

| Classe | Import | Caso d'uso | Metodi tipici |
| --- | --- | --- | --- |
| `BaseView` | `from dflango.views import BaseView` | Endpoint custom/non-CRUD (login, conferme, azioni speciali) | Qualsiasi |
| `ListView` | `from dflango.views import ListView` | Listing + creazione su collezione | `GET`, `POST` |
| `GeneralListView` | `from dflango.views import GeneralListView` | Listing + creazione con filtri avanzati, validazione enum, colonne ARRAY | `GET`, `POST` |
| `DetailView` | `from dflango.views import DetailView` | Read/update/delete su singola risorsa | `GET`, `PUT`, `DELETE` |
| `SearchView` | `from dflango.views import SearchView` | Ricerca full-text su campi configurabili via parametro `query` | `GET` |
| `InternalView` | `from dflango.views import InternalView` | Endpoint inter-service (API interne) | Qualsiasi |
| `BaseExportRequestView` | `from dflango.views import BaseExportRequestView` | Richiesta export CSV asincrono (delega a uploads) | `POST` |
| `ConfigView` | `from dflango.views import ConfigView` | Risorsa singleton (configurazione) | `GET`, `PUT` |
| `StatisticView` | `from dflango.views import StatisticView` | KPI e statistiche aggregate | `GET` |

### 4.2 Attributi standard

```python
# dFlango
from dflango.views import ListView
from dflango.mixin import PermissionsMixin

# Models
from app.models.resource import Resource

# Schemas
from app.schemas.resource.resource_read import ResourceReadSchema
from app.schemas.resource.resource_create import ResourceCreateSchema


class ResourceListCreateView(PermissionsMixin, ListView):
    model = Resource
    read_schema = ResourceReadSchema
    write_schema = ResourceCreateSchema
    accepted_methods = ["GET", "POST"]
    only_authenticated = True
    sort_default = "-created_at"
```

| Attributo | Descrizione |
| --- | --- |
| `model` | Model SQLAlchemy (per `ListView`/`DetailView`) |
| `read_schema` | Schema di output |
| `write_schema` | Schema di input |
| `accepted_methods` | Metodi HTTP accettati |
| `only_authenticated` | `True` per endpoint protetti |
| `lookup_url_kwarg` | Parametro URL per `DetailView` (default: `id`) |
| `sort_default` | Ordinamento di default per `ListView` |

**Nota importante:** i ruoli vengono risolti automaticamente dal `PermissionsMixin` usando il nome dell'endpoint registrato in `urls.py` e il mapping in `ViewPermissions`. Non è necessario dichiarare `get_roles`, `post_roles`, ecc. manualmente nella view.

### 4.3 Pattern `ListView` (list + create)

#### `get_query()`

```python
def get_query(self):
    return Resource.query.filter_by(deleted_at=None).order_by(Resource.created_at.desc())
```

Con ricerca e filtri datetime:

```python
# Built-in
from datetime import datetime, timezone

# Flask
from flask import request

# dFlango
from dflango.db import db


def get_query(self):
    query = Resource.query.filter_by(deleted_at=None).order_by(Resource.created_at.desc())

    search_term = request.args.get("search")
    if search_term:
        query = query.filter(
            db.or_(
                Resource.name.ilike(f"%{search_term}%"),
                Resource.code.ilike(f"%{search_term}%"),
            )
        )

    # Filtri datetime: usare il pattern campo__gte / campo__lte
    created_at_gte = request.args.get("created_at__gte")
    if created_at_gte:
        query = query.filter(Resource.created_at >= datetime.fromisoformat(created_at_gte).replace(tzinfo=timezone.utc))

    created_at_lte = request.args.get("created_at__lte")
    if created_at_lte:
        query = query.filter(Resource.created_at <= datetime.fromisoformat(created_at_lte).replace(tzinfo=timezone.utc))

    return query
```

**Convenzione filtri datetime:** i parametri query per range di date seguono sempre il formato `<campo>__gte` (maggiore o uguale) e `<campo>__lte` (minore o uguale). Non usare nomi generici come `date_from` / `date_to`.

### 4.4 Pattern `GeneralListView` (list + create con filtri avanzati)

`GeneralListView` estende `ListView` aggiungendo:
- Validazione automatica dei valori enum (anche colonne `ARRAY(Enum)`)
- Gestione filtri su colonne ARRAY con operatore `.any()`
- Modifier expressions (es. cast a data con timezone)
- Lookup `exact` con valori multipli separati da virgola per colonne enum

```python
# dFlango
from dflango.views import GeneralListView
from dflango.mixin import PermissionsMixin

# Models
from app.models.lead.lead import Lead

# Schemas
from app.schemas.lead.lead_read import LeadReadSchema
from app.schemas.lead.lead_create import LeadCreateSchema


class LeadListCreateView(PermissionsMixin, GeneralListView):
    model = Lead
    read_schema = LeadReadSchema
    write_schema = LeadCreateSchema
    accepted_methods = ["GET", "POST"]
    only_authenticated = True
    sort_default = "-created_at"

    allowed_filters = {
        "status": ["exact"],
        "company_name": ["icontains"],
        "created_at": ["gte", "lte"],
        "source_id": ["exact"],
    }

    def get_query(self):
        return Lead.query.filter_by(deleted_at=None)
```

| Attributo | Descrizione |
| --- | --- |
| `allowed_filters` | Dict `{campo: [lookup_type, ...]}`. Lookup supportati: `exact`, `icontains`, `contains`, `gt`, `gte`, `lt`, `lte`, `in` |
| `validate_enum_value()` | Valida automaticamente i valori enum ricevuti nei filtri |
| `is_array_column()` | Rileva colonne `ARRAY` e applica `.any()` invece di `==` per il lookup `exact` |

**Quando usare `GeneralListView` vs `ListView`:**
- Usare `GeneralListView` quando la tabella ha colonne enum o ARRAY con filtri, o quando servono modifier expression
- Usare `ListView` per endpoint semplici senza queste necessità

### 4.5 Pattern `SearchView` (ricerca full-text)

`SearchView` eredita da `ListView` e aggiunge la ricerca full-text su campi configurabili. Il client invia il termine di ricerca tramite il parametro `query` nella query string.

```python
# dFlango
from dflango.views import SearchView
from dflango.mixin import PermissionsMixin

# Models
from app.models.lead.lead import Lead

# Schemas
from app.schemas.lead.lead_search_read import LeadSearchReadSchema


class LeadSearchView(PermissionsMixin, SearchView):
    model = Lead
    read_schema = LeadSearchReadSchema
    search_fields = ["company_name", "email", "contact_person"]

    def get_query(self):
        query = super().get_query()
        return query.filter(Lead.deleted_at.is_(None)).order_by(Lead.created_at.desc())
```

| Attributo | Descrizione |
| --- | --- |
| `search_fields` | Lista di nomi di campo del model su cui cercare. Campi non-stringa vengono castati automaticamente a `String` |
| `get_search_fields()` | Valida i campi dichiarati contro il model, scartando quelli inesistenti con warning |
| Parametro `query` | Il parametro GET usato dal client per inviare il termine di ricerca (es. `?query=acme`) |

**Comportamento:** la `SearchView` applica `ilike` (case-insensitive) su ciascun campo in `search_fields`, combinando le condizioni con `OR`. Se un campo non è di tipo stringa, viene automaticamente castato a `String`.

**Nota:** chiamare `super().get_query()` nel proprio override per mantenere la logica di ricerca, poi aggiungere filtri addizionali (soft delete, ordering, ecc.).

### 4.6 Pattern `DetailView` (detail + update)

```python
class ResourceDetailView(PermissionsMixin, DetailView):
    model = Resource
    read_schema = ResourceReadSchema
    write_schema = ResourceUpdateSchema
    lookup_url_kwarg = "resource_id"
    accepted_methods = ["GET", "PUT"]
    only_authenticated = True

    def get_query(self):
        return Resource.query.filter_by(deleted_at=None)

    def get_schema_context(self):
        instance = self.get_instance()
        return {"resource_id": str(instance.id) if instance else None}

    def post_edit(self, old_instance, instance):
        pass
```

| Metodo | Scopo |
| --- | --- |
| `get_query()` | Filtra dataset (soft delete) |
| `get_schema_context()` | Passa contesto allo schema (es. ID per validazione unique) |
| `post_edit()` | Side effect post-update (logging, audit) |

### 4.7 Pattern `BaseView` (endpoint custom)

```python
class ResourceArchiveView(PermissionsMixin, BaseView):
    accepted_methods = ["POST"]
    only_authenticated = True

    def post(self, resource_id):
        resource = Resource.query.filter_by(id=resource_id, deleted_at=None).first()
        if not resource:
            return jsonify({"error": "Resource not found", "code": ErrorCodes.NOT_FOUND}), 404

        resource.deleted_at = db.func.now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error archiving resource: {e}")
            return jsonify({"error": "Failed to archive resource", "code": ErrorCodes.INTERNAL_ERROR}), 400

        return jsonify({"message": "Resource archived successfully"}), 200
```

### 4.8 Pattern `InternalView` (inter-service)

```python
class InternalResourceView(InternalView):
    def get(self, resource_id):
        resource = Resource.query.filter_by(id=resource_id, deleted_at=None).first()
        if not resource:
            return jsonify({"error": "Resource not found", "code": ErrorCodes.NOT_FOUND}), 404

        result = InternalResourceReadSchema().dump(resource)
        return jsonify(result), 200
```

### 4.9 Pattern `ConfigView` (risorsa singleton)

`ConfigView` eredita da `BaseView` e gestisce risorse **singleton** — model con una sola riga in tabella (es. configurazione di sistema, impostazioni dispositivo). Espone solo `GET` e `PUT`: lettura e aggiornamento, senza creazione né eliminazione.

```python
# dFlango
from dflango.views import ConfigView
from dflango.mixin import PermissionsMixin

# Models
from app.models.settings.device_settings import DeviceSettings

# Schemas
from app.schemas.settings.device_settings_read import DeviceSettingsReadSchema
from app.schemas.settings.device_settings_update import DeviceSettingsUpdateSchema


class DeviceSettingsConfigView(PermissionsMixin, ConfigView):
    model = DeviceSettings
    read_schema = DeviceSettingsReadSchema
    write_schema = DeviceSettingsUpdateSchema
    accepted_methods = ["GET", "PUT"]
    only_authenticated = True
```

| Attributo | Descrizione |
| --- | --- |
| `model` | Model SQLAlchemy singleton |
| `read_schema` | Schema di output (`dump_only` fields) |
| `write_schema` | Schema di input per aggiornamento |
| `accepted_methods` | Sempre `["GET", "PUT"]` — no POST/DELETE |

**Comportamento:**
- `GET` → chiama `query.first()` e restituisce il record serializzato. Se non esiste, ritorna `404`.
- `PUT` → carica il record con `query.first()`, valida il payload con `write_schema`, salva e restituisce il record aggiornato.

**Hooks disponibili:**

| Metodo | Scopo |
| --- | --- |
| `pre_edit(instance)` | Chiamato prima del salvataggio. Può restituire un dict passato come `**kwargs` a `post_edit` |
| `post_edit(old_data, updated_instance, **kwargs)` | Chiamato dopo il salvataggio con i dati vecchi (serializzati) e l'istanza aggiornata |

**Schema:**
- Per il `ConfigView` servono solo **due schema**: `Read` e `Update`. Non serve `Create` perché il record singleton viene inserito via seed/migration.
- Il model singleton **non ha** `deleted_at` (no soft delete).

**Seed del record singleton:**
Il record deve essere inserito nel database prima dell'uso dell'endpoint, tramite fixture o migration:

```python
from app.models.settings.device_settings import DeviceSettings
from dflango.db import db

if not DeviceSettings.query.first():
    settings = DeviceSettings(json_settings={})
    db.session.add(settings)
    db.session.commit()
```

**URLs:**
```python
("/settings/device/", DeviceSettingsConfigView.as_view("device_settings_config")),
```

**Permessi:**
```python
device_settings_config = EndpointPermission(
    get={"description": "Lettura configurazione dispositivo", "roles": [UserTypes.ADMIN]},
    put={"description": "Modifica configurazione dispositivo", "roles": [UserTypes.ADMIN]},
)
```

### 4.10 Error handling e transazioni

Ogni operazione di scrittura su DB deve:
1. Avvolgere in `try/except`
2. Eseguire `db.session.rollback()` in caso di errore
3. Ritornare errore JSON consistente con `ErrorCodes`
4. Loggare l'eccezione lato server

### 4.11 Status code

| Codice | Significato |
| --- | --- |
| `200` | Operazione riuscita |
| `201` | Creazione riuscita |
| `400` | Errore di validazione / business |
| `401` | Non autenticato |
| `403` | Autenticato ma non autorizzato |
| `404` | Risorsa non trovata |
| `409` | Conflitto (dato duplicato) |
| `422` | Errore semantico di validazione |

---

## 5) URLs — Registrazione route

### 5.1 Struttura `urls.py`

```python
# Flask
from flask import Blueprint

# dFlango
from dflango.routes import RouteRegistry

# Views
from .views.health import HealthCheckView
from .views.resource.resource_list import ResourceListCreateView
from .views.resource.resource_detail import ResourceDetailView

# Internal Views
from .views.internal.resource import InternalResourceView


class ServiceRouteRegistry(RouteRegistry):
    blueprint = Blueprint("api", __name__, url_prefix="/api/<service>")
    urlpatterns = [
        # Health Check
        ("/health/", HealthCheckView.as_view("healthcheck")),

        # Resources
        ("/resources/", ResourceListCreateView.as_view("resource_list_create")),
        ("/resources/<uuid:resource_id>/", ResourceDetailView.as_view("resource_detail")),

        # Internal
        ("/internal/resources/<uuid:resource_id>/", InternalResourceView.as_view("internal_resource_detail")),
    ]
```

### 5.2 Convenzioni di naming

| Elemento | Regola | Esempio |
| --- | --- | --- |
| Path risorsa | Plurale, snake_case con trattini | `/resources/`, `/payment-terms/` |
| Parametro URL | `<uuid:resource_id>` | `/resources/<uuid:resource_id>/` |
| Nome endpoint | Descrittivo, snake_case | `"resource_list_create"`, `"resource_detail"` |
| Azioni custom | Sotto-path della risorsa | `/resources/<uuid:resource_id>/archive/` |
| API interne | Prefisso `/internal/` | `/internal/resources/<uuid:resource_id>/` |

### 5.3 Regola critica — Coerenza URL

Il path registrato in `urls.py` deve corrispondere **esattamente** all'URL definito nel JSON API (campo `endpoint`, escluso il prefisso `/api/<service>`). Non è mai lecito abbreviare, omettere o ristrutturare il path rispetto a quanto specificato.

**Esempio corretto:** se il JSON specifica `"endpoint": "/api/crm/sources/@minimal"`, il path registrato deve essere `/sources/@minimal` (con il suffisso `/@minimal` incluso).

**Esempio errato:** registrare `/sources/` omettendo `/@minimal` è un errore — l'endpoint risultante sarebbe `/api/crm/sources/` invece di `/api/crm/sources/@minimal`.

---

## 6) Mapping permessi

### 6.1 Scopo

Il file `app/config/permissions.py` centralizza il mapping tra **ruoli utente** e **view autorizzate**. È l'unico punto di verità per i permessi dell'intero microservizio.

### 6.2 Regole

1. **Completezza**: una entry per OGNI view del microservizio, nessuna esclusa
2. **Aggiornamento**: ogni nuova view aggiunta al mapping PRIMA della PR
3. **Coerenza**: le view importano i ruoli da questo file, mai dichiararli direttamente
4. **Ruoli dall'enum**: il file importa i ruoli da `app/constants/user_types.py`

### 6.3 Template `app/config/permissions.py`

```python
# Constants
from app.constants.user_types import UserTypes


class MethodPermission(list):
    def __init__(self, roles, description=""):
        super().__init__(roles)
        self.description = description


class EndpointPermission:
    def __init__(self, **methods):
        for method_name, config in methods.items():
            setattr(self, method_name, MethodPermission(
                roles=config["roles"],
                description=config["description"],
            ))


class ViewPermissions:
    """
    Mapping centralizzato dei permessi.
    Il nome di ogni attributo deve corrispondere ESATTAMENTE al nome
    dell'endpoint passato a as_view("...") in urls.py.
    """

    resource_list_create = EndpointPermission(
        get={"description": "Lista risorse", "roles": [UserTypes.STAFF, UserTypes.ADMIN]},
        post={"description": "Creazione risorsa", "roles": [UserTypes.ADMIN]},
    )
    resource_detail = EndpointPermission(
        get={"description": "Dettaglio risorsa", "roles": [UserTypes.STAFF, UserTypes.ADMIN]},
        put={"description": "Aggiornamento risorsa", "roles": [UserTypes.ADMIN]},
    )
```

### 6.4 PermissionsMixin — Risoluzione automatica (da dFlango)

Il `PermissionsMixin` è fornito da dFlango (`from dflango.mixin import PermissionsMixin`) e risolve i ruoli a runtime usando `request.endpoint`:

1. Flask memorizza il nome dell'endpoint quando la route viene registrata con `as_view("...")`
2. A runtime, `request.endpoint` restituisce `"<blueprint>.<endpoint_name>"`
3. Il mixin rimuove il prefisso del blueprint e cerca l'attributo su `ViewPermissions`

**Contratto vincolante:** il nome passato a `as_view("...")` in `urls.py` deve corrispondere esattamente all'attributo su `ViewPermissions`. Questo è il contratto tra routing e permessi.

#### Import

```python
# dFlango
from dflango.mixin import PermissionsMixin
```

#### Priorità di risoluzione della classe permessi

Il `PermissionsMixin` di dFlango risolve la `permissions_class` secondo questa priorità:

1. **Attributo di classe sulla view** — se impostato esplicitamente (es. `permissions_class = ViewPermissions`)
2. **Flask config** — `DFLANGO_PERMISSIONS_CLASS` (stringa dotted path o classe diretta)
3. **DFlangoConfig default** — `None` (nessun controllo ruoli)

#### Configurazione consigliata

Il modo più pulito è configurare la classe permessi globalmente in `app/config.py`:

```python
# app/config.py

class Config:
    # ...
    DFLANGO_PERMISSIONS_CLASS = "app.config.permissions.ViewPermissions"
```

In questo modo, tutte le view che usano `PermissionsMixin` risolvono automaticamente i ruoli da `ViewPermissions` senza bisogno di dichiarare `permissions_class` su ogni view.

#### Endpoint pubblici

Per view senza controllo ruoli:

```python
class PublicResourceView(PermissionsMixin, ListView):
    permissions_class = None
    only_authenticated = False
```

#### Come funziona `has_roles()`

Il metodo `has_roles()` del `PermissionsMixin`:

1. Ottiene il nome dell'endpoint dalla request corrente (`request.endpoint`)
2. Rimuove il prefisso del blueprint (es. `"api.resource_list_create"` → `"resource_list_create"`)
3. Cerca l'attributo corrispondente su `ViewPermissions`
4. Mappa il metodo HTTP al sotto-attributo (`GET` → `.get`, `POST` → `.post`, `PATCH` → `.put`)
5. Ottiene i ruoli richiesti e li confronta con quelli dell'utente corrente
6. Supporta ruoli come `Enum`, stringhe e liste (normalizza tutto a lowercase)

#### Esempio di utilizzo in una view

```python
# dFlango
from dflango.views import ListView
from dflango.mixin import PermissionsMixin


class ResourceListCreateView(PermissionsMixin, ListView):
    model = Resource
    read_schema = ResourceReadSchema
    write_schema = ResourceCreateSchema
    accepted_methods = ["GET", "POST"]
    only_authenticated = True
```

Il mixin deve apparire **prima** della classe view dFlango nella lista di ereditarietà, in modo che il suo `has_roles` abbia priorità nel MRO.

---

## 7) Configurazione

### 7.1 `app/__init__.py` — Factory

```python
# Flask
from flask import Flask

# dFlango
from dflango import DFlango

# Models
from .models import *

# Config
from .config import Config

# URLs
from .urls import ServiceRouteRegistry


def create_app():
    app = Flask(__name__)
    dflango = DFlango()
    dflango.init_app(app, Config, ServiceRouteRegistry)
    return app
```

### 7.2 `app/config.py` — Configurazione

```python
# Built-in
import os

# Third-party
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URI")
    SECRET_KEY = os.getenv("SECRET_KEY")

    # dFlango
    DFLANGO_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
    DFLANGO_CORS_ALLOW_HEADERS = os.getenv("CORS_ALLOW_HEADERS", "").split(",")
    DFLANGO_CORS_SUPPORTS_CREDENTIALS = os.getenv(
        "CORS_SUPPORTS_CREDENTIALS", "false"
    ).lower() in ("true", "1", "yes")
    DFLANGO_USER_DATA_SOURCE = "DB"
    DFLANGO_USER_MODEL = "app.models.User"
    DFLANGO_USER_SCHEMA = "app.schemas.<auth_schema_path>"
    DFLANGO_ACCESS_FIELD_NAME = "user_types"

    # Internal API
    INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET")
```

**Note:**

- `DFLANGO_ACCESS_FIELD_NAME` indica il campo del model usato per il controllo dei ruoli
- `DFLANGO_USER_MODEL` e `DFLANGO_USER_SCHEMA` vengono configurati in base al microservizio

### 7.3 Enum ruoli (`app/constants/user_types.py`)

```python
# dFlango
from dflango.enum import Enum


class UserTypes(Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    SUPERADMIN = "SUPERADMIN"
```

Questo file definisce i ruoli disponibili. Le view non importano direttamente da qui ma referenziano i ruoli tramite `app/config/permissions.py`.

### 7.4 Codici errore (`app/constants/error_codes.py`)

```python
# dFlango
from dflango.enum import Enum


class ErrorCodes(Enum):
    # Generali
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Autenticazione
    INVALID_TOKEN = "INVALID_TOKEN"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

    # Risorse (aggiungere specifici per dominio)
    RESOURCE_CREATION_FAILED = "RESOURCE_CREATION_FAILED"
```

---

## 8) Workflow completo — Passo per passo

Quando devi implementare una nuova entità dominio, segui questi step in ordine:

### Step 1 — Enum e costanti

- Definisci eventuali enum in `app/constants/`
- Aggiungi codici errore specifici in `error_codes.py`

### Step 2 — Model

- Crea `app/models/<risorsa>.py`
- Implementa campi, timestamp, soft delete, relazioni
- Aggiorna `app/models/__init__.py`

### Step 3 — Schema

- Crea `<risorsa>_create.py`, `<risorsa>_update.py`, `<risorsa>_read.py` in `app/schemas/<dominio>/`
- Implementa validazioni, enum field, nested se necessario

### Step 4 — View

- Crea `<risorsa>_list.py` e `<risorsa>_detail.py` in `app/views/<dominio>/`
- Eredita da `PermissionsMixin` come primo parent (es. `class ResourceListCreateView(PermissionsMixin, ListView)`)
- Imposta attributi standard (`model`, `read_schema`, `write_schema`, `accepted_methods`, `only_authenticated`)
- Implementa `get_query()`, create custom se necessario

### Step 5 — URLs

- Registra endpoint in `app/urls.py`
- Rispetta le convenzioni di naming

### Step 6 — Mapping permessi

- Aggiungi le nuove entry in `app/config/permissions.py`
- Verifica che il nome dell'endpoint in `urls.py` corrisponda all'attributo su `ViewPermissions`

### Step 7 — Migration

- `flask db migrate -m "add_<risorsa>"`
- `flask db upgrade`
- Verifica migration

### Step 8 — Test

- Crea `tests/test_<risorsa>.py`
- Implementa scenari minimi per ogni endpoint
- Esegui test con `make test`

---

## 9) Vendors — Internal Clients di riferimento

### 9.1 Principio

Ogni microservizio che espone endpoint `InternalView` mantiene nella cartella `app/vendors/internal/` il **client di riferimento** per quelle API. Questo client:

- **NON viene utilizzato** all'interno del microservizio stesso
- Serve come **sorgente canonica** da copiare in `app/services/internal/` degli altri microservizi
- Viene **aggiornato** quando gli endpoint internal del microservizio cambiano

### 9.2 Struttura

| Cartella | Contenuto | Direzione |
| --- | --- | --- |
| `app/vendors/internal/` | Client per le API internal che **questo** microservizio espone | Da copiare negli altri |
| `app/services/internal/` | Client per le API internal di **altri** microservizi (copiati dai loro vendors) | Copiati da altri |

### 9.3 Pattern del client

```python
# Built-in
import logging

# Third-party
import requests

# Flask
from flask import current_app


class {Service}InternalClient:
    """Client for calling internal {Service} API endpoints."""

    def __init__(self):
        self.base_url = current_app.config.get("{SERVICE}_INTERNAL_API_URL")
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
            logging.error(f"{Service} internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"{Service} internal API unreachable: {e}")
            return None

    def _post(self, url, json=None, timeout=10):
        try:
            response = requests.post(url, json=json, headers=self._headers, timeout=timeout)
            if response.status_code in (200, 201, 202):
                return response.json()
            logging.error(f"{Service} internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"{Service} internal API unreachable: {e}")
            return None

    def _put(self, url, json=None, timeout=10):
        try:
            response = requests.put(url, json=json, headers=self._headers, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            logging.error(f"{Service} internal API error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"{Service} internal API unreachable: {e}")
            return None

    def method_name(self, param):
        """Descrizione dell'operazione."""
        return self._get(f"{self.base_url}/internal/endpoint/{param}/")
```

**Struttura obbligatoria della classe:**

1. `__init__` — inizializza `base_url` e `secret` da `current_app.config`
2. `_headers` — property che ritorna il dict con `X-Internal-Token`
3. `_get`, `_post`, `_put` — metodi base che gestiscono try/except, status code e logging
4. Metodi pubblici — definiscono solo l'URL e i parametri, delegando ai metodi base

### 9.4 Header istruzioni

Ogni vendor client deve avere un commento header con:
- Descrizione del file e del suo scopo
- Istruzioni per copiarlo nel microservizio target
- Variabili di configurazione richieste nel `config.py` del consumer
- Env vars da aggiungere nel `docker-compose.yml`

### 9.5 Come usare un vendor client in un altro microservizio

1. Copiare il file da `apps/{source}/app/vendors/internal/{client}.py` a `apps/{target}/app/services/internal/{client}.py`
2. Aggiungere le variabili di configurazione nel `config.py` del microservizio target
3. Aggiungere le env vars corrispondenti nel `docker-compose.yml`

### 9.6 Quando creare un vendor client

Ogni volta che si aggiunge un nuovo endpoint `InternalView` a un microservizio, l'agent DEVE:

1. Verificare se esiste già un vendor client in `app/vendors/internal/`
2. Se non esiste, creare la cartella `app/vendors/internal/` con `__init__.py`
3. Creare o aggiornare il file `app/vendors/internal/{service}.py` con il metodo corrispondente al nuovo endpoint
4. Includere l'header con le istruzioni per la copia

### 9.7 Autenticazione

Tutti gli endpoint internal sono protetti dal header `X-Internal-Token`, validato dalla classe `InternalView` di dFlango. Il token è condiviso tra tutti i microservizi tramite la env var `INTERNAL_API_SECRET`.
