# Guida pratica: Model nei microservizi

## Obiettivo

Questa guida definisce lo standard completo per implementare model entità in un microservizio Python/Flask con dFlango, coprendo la definizione del model SQLAlchemy, enum, campi sensibili, relazioni e registrazione.

Il documento è agnostico rispetto al progetto specifico ed è applicabile a qualsiasi microservizio che segua lo stack descritto.

---

## Riepilogo convenzioni

| Aspetto | Convenzione |
| --- | --- |
| **Model** | `app/models/<risorsa>.py`, classe `db.Model`, PK UUID, soft delete con `deleted_at` |
| **Tablename** | `__tablename__` in snake_case singolare |
| **Primary key** | `UUID(as_uuid=True)` con `default=uuid.uuid4` |
| **Timestamp** | `created_at` (`server_default`), `updated_at` (`onupdate`), `deleted_at` (nullable) |
| **Relazioni** | `db.relationship(..., back_populates=..., lazy="selectin")` |
| **`__repr__`** | Stringa utile per debugging |
| **Enum** | `app/constants/<nome>.py` con `dflango.enum.Enum`, mappato nel model con `db.Enum(EnumClass)` |
| **Soft delete** | `deleted_at` filtrato in `get_query()`, mai delete fisico |
| **Ordine import** | Built-in → Flask → dFlango → Third-party → Models → Schemas → Constants → Utils → Services |
| **Export model** | `app/models/__init__.py` aggiornato con ogni nuovo model |

---

## 1) Stack tecnologico

| Componente | Tecnologia | Scopo |
| --- | --- | --- |
| Linguaggio | Python 3.12 | Runtime dei microservizi |
| Framework | Flask + dFlango | Framework web e layer CRUD |
| ORM | SQLAlchemy (via Flask-SQLAlchemy) | Persistenza e relazioni |
| Migrazioni | Alembic (via Flask-Migrate) | Versionamento schema DB |
| Database | PostgreSQL 17.2 | Database relazionale |

---

## 2) Struttura file di progetto (model)

```text
apps/<microservice>/
└── app/
    ├── models/
    │   ├── __init__.py          # export di tutti i model
    │   ├── <risorsa_a>.py
    │   └── <risorsa_b>.py
    └── constants/
        ├── __init__.py
        ├── user_types.py        # enum ruoli utente
        ├── error_codes.py       # enum codici errore
        └── <nome_enum>.py       # enum applicativi custom
```

---

## 3) Model — Definizione entità

### 3.1 Convenzioni base

| Aspetto | Regola |
| --- | --- |
| Classe base | `class X(db.Model)` |
| Tablename | `__tablename__` in snake_case singolare |
| Primary key | `UUID(as_uuid=True)` con `default=uuid.uuid4` |
| Timestamp | `created_at` (`server_default`), `updated_at` (`onupdate`), `deleted_at` (nullable) |
| Relazioni | `db.relationship(..., back_populates=..., lazy="selectin")` |
| `__repr__` | stringa utile per debugging |

### 3.2 Ordine degli import

Tutti i file Python del progetto devono seguire quest'ordine di import, separando ogni gruppo con una riga vuota e precedendolo da un commento descrittivo:

1. **Built-in** — moduli della libreria standard Python
2. **Flask** — import dal framework Flask
3. **dFlango** — import dal framework dFlango
4. **Third-party** — librerie esterne (SQLAlchemy, Marshmallow, ecc.)
5. **Models** — model SQLAlchemy dell'app
6. **Schemas** — schema Marshmallow dell'app
7. **Constants** — enum e costanti dell'app
8. **Utils** — utility e helper dell'app
9. **Services** — servizi inter-service, pubsub, ecc.

**Regola:** tutti gli import devono partire da `app.` (mai da percorsi esterni), poiché i microservizi sono dockerizzati e il codice sorgente viene montato come volume alla root del container.

**Posizione degli import:** tutti gli import vanno dichiarati **in cima al file**, prima di qualsiasi definizione di classe o funzione. L'unica eccezione è l'import all'interno di una funzione o metodo quando è strettamente necessario per evitare **import circolari**: in tal caso va accompagnato da un commento esplicativo.

**Import non utilizzati:** prima di finalizzare qualsiasi file, verificare che ogni import dichiarato sia effettivamente utilizzato nel codice. Gli import non utilizzati devono essere rimossi.

### 3.3 Template model

```python
# Built-in
import uuid

# dFlango
from dflango.db import db

# Third-party
from sqlalchemy.dialects.postgresql import UUID


class Resource(db.Model):
    __tablename__ = "resource"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, index=True)
    code = db.Column(db.String(100), unique=True, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    def __repr__(self):
        return f"<Resource {self.id} {self.name}>"
```

### 3.4 Enum

Definisci gli enum applicativi in `app/constants/` usando `dflango.enum.Enum`:

```python
# app/constants/resource_status.py

# dFlango
from dflango.enum import Enum


class ResourceStatus(Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
```

Nel model, mappali usando `db.Enum()` direttamente:

```python
# Constants
from app.constants.resource_status import ResourceStatus

status = db.Column(db.Enum(ResourceStatus), nullable=False, index=True, default=ResourceStatus.ACTIVE)
```

**Nota:** Alembic gestisce automaticamente la creazione dell'enum PostgreSQL durante la migration.

### 3.5 Campi sensibili

Per campi come password o secret, applica il pattern property + hash:

```python
_password = db.Column("password", db.String(255), nullable=True)

@property
def password(self):
    raise AttributeError("password is not a readable attribute")

@password.setter
def password(self, value):
    from werkzeug.security import generate_password_hash
    self._password = generate_password_hash(value) if value is not None else None

def verify_password(self, value):
    from werkzeug.security import check_password_hash
    if self._password is None:
        return False
    return check_password_hash(self._password, value)
```

### 3.6 Relazioni

| Cardinalità | Pattern |
| --- | --- |
| One-to-one | FK con `unique=True`, relazione con `uselist=False` |
| One-to-many | FK indicizzata sul figlio, `back_populates` su entrambi |

```python
# One-to-one (lato figlio)
user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("user.id", ondelete="CASCADE"), unique=True, nullable=False)
user = db.relationship("User", back_populates="profile", uselist=False, lazy="selectin")
```

```python
# One-to-many (lato padre)
items = db.relationship("Item", back_populates="order", lazy="selectin")

# One-to-many (lato figlio)
order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("order.id"), nullable=False, index=True)
order = db.relationship("Order", back_populates="items", lazy="selectin")
```

### 3.7 Export model

Aggiorna `app/models/__init__.py` con ogni nuovo model:

```python
from .resource import Resource
from .category import Category

__all__ = ["Resource", "Category"]
```

---

## 4) Migrazioni

Dopo aver creato o modificato un model, generare e applicare la migration:

```bash
# Genera la migration
flask db migrate -m "add resource table"

# Applica la migration
flask db upgrade
```

**Regole:**

- Ogni model deve avere una migration dedicata
- Non modificare mai migration già applicate in produzione
- Verificare sempre il file di migration generato prima di applicarlo
- Usare nomi descrittivi per le migration (es. `add_resource_table`, `add_status_to_resource`)

**Checklist migration:**

- [ ] Enum creati correttamente (Alembic gestisce `db.Enum()` automaticamente)
- [ ] FK e indici dichiarati
- [ ] Vincoli unique rispettati
- [ ] `upgrade()` e `downgrade()` coerenti
