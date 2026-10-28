# Guida allo Sviluppo Model — Istruzioni per Agent AI

## Obiettivo

Questo documento definisce il flusso operativo che un agent AI deve seguire per implementare model entità completi e validati. Il flusso è sequenziale: ogni model deve essere creato, migrato e verificato prima di passare al successivo.

---

## Documenti di Riferimento

Questo documento viene sempre fornito insieme a:

1. **`input.json`** — File JSON contenente la lista completa dei model da implementare con tutte le specifiche (tablename, fields, relationships, enums, ecc.)
2. **`model-spec-kit.md`** — Standard tecnici per Model, Enum, Relazioni, Export

L'agent DEVE leggere e rispettare integralmente `model-spec-kit.md` per ogni aspetto implementativo.

---

## Struttura del JSON Model

Ogni oggetto nel file JSON rappresenta un singolo model da implementare. I campi rilevanti sono:

| Campo | Significato |
| --- | --- |
| `id` | Identificativo univoco, determina l'ordine di implementazione |
| `entity` | Nome della classe Python (es. `Resource`, `Category`) |
| `tablename` | Nome della tabella PostgreSQL in snake_case singolare |
| `domain` | Dominio logico (usato come riferimento per schemas/views) |
| `microservice` | Microservizio di appartenenza |
| `fields` | Array di campi del model con tipo, nullable, unique, index, default |
| `relationships` | Array di relazioni con altri model (tipo, target, back_populates) |
| `enums` | Array di enum richiesti dal model (nome, valori) |
| `soft_delete` | Se il model supporta soft delete con `deleted_at` |
| `sensitive_fields` | Campi sensibili da gestire con property + hash (es. `password`) |
| `file_fields` | Campi file (nome logico, obbligatorio) — vedi `file-management-spec-kit.md` |
| `implemented` | `false` se da implementare, `true` se già implementato |
| `notes` | Note aggiuntive per lo sviluppo |

---

## Flusso di Sviluppo per Singolo Model

Per OGNI model nel JSON con `implemented: false`, eseguire i seguenti step in ordine:

### Step 1 — Enum

Per ogni enum richiesto dal model:
1. Creare il file `app/constants/<nome_enum>.py` seguendo il template in `model-spec-kit.md` sezione 3.4
2. Aggiornare `app/constants/__init__.py` se necessario

### Step 2 — Model

1. Creare il file `app/models/<risorsa>.py` seguendo il template in `model-spec-kit.md` sezione 3.3
2. Implementare tutti i campi del JSON:
   - Tipi SQLAlchemy corretti (String, Integer, Boolean, DateTime, UUID, Enum, JSON, Text, ecc.)
   - `nullable`, `unique`, `index`, `default` come specificato
   - Timestamps standard (`created_at`, `updated_at`, `deleted_at` se `soft_delete: true`)
3. Implementare campi sensibili con il pattern property + hash (sezione 3.5) se presenti in `sensitive_fields`
4. Implementare campi file (sezione 3.6 e `file-management-spec-kit.md`) se presenti in `file_fields`
5. Implementare relazioni (sezione 3.6) se presenti in `relationships`
6. Aggiungere `__repr__` utile per debugging

### Step 3 — Export

Aggiornare `app/models/__init__.py` aggiungendo il nuovo model (sezione 3.7).

### Step 4 — Verifica import

Verificare che:
- Tutti gli import siano in cima al file nel corretto ordine (sezione 3.2)
- Non ci siano import non utilizzati

### Step 5 — Marcatura Completamento

Aggiornare il campo `implemented: true` nel file JSON per il model appena completato.

---

## Condizioni di BLOCCO

Il flusso NON può passare al model successivo se:

- Il model non è importato in `app/models/__init__.py`
- Ci sono import non utilizzati o in ordine errato
- I campi sensibili non usano il pattern property + hash
- Le relazioni non hanno `back_populates` su entrambi i lati

---

## Checklist per Model Completato

- [ ] Enum creati in `app/constants/` (se necessari)
- [ ] File model creato in `app/models/<risorsa>.py`
- [ ] Tutti i campi implementati con tipi e constraint corretti
- [ ] Timestamps standard presenti
- [ ] Soft delete con `deleted_at` (se `soft_delete: true`)
- [ ] Campi sensibili con property + hash (se presenti)
- [ ] Relazioni con `back_populates` su entrambi i lati (se presenti)
- [ ] `__repr__` definito
- [ ] `app/models/__init__.py` aggiornato
- [ ] Import in ordine corretto, nessun import inutilizzato
- [ ] Campo `implemented: true` nel JSON
