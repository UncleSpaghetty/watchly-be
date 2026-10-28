# Guida pratica: Audit Logging sulle operazioni di scrittura a DB

## Obiettivo

Questa guida definisce lo standard per integrare il logging strutturato (audit log) via Pub/Sub su tutte le operazioni di scrittura a database nei microservizi Python/Flask con dFlango.

Lo scopo è garantire la **tracciabilità completa** di ogni mutazione di stato nel sistema, sia nei casi di successo che di errore.

---

## Riepilogo convenzioni

| Aspetto | Convenzione |
| --- | --- |
| **Funzione di log** | `publish_log(event_type, user=None, meta=None)` |
| **Posizione servizio** | `app/services/pubsub/logs.py` |
| **Quando loggare** | Ogni operazione di scrittura a DB (create, update, delete, soft-delete, cambio stato) |
| **Eccezioni** | Login e logout sono esclusi dal logging |
| **Contesto utente** | Passare sempre `user=self.get_current_user()` quando l'endpoint è autenticato |
| **Naming event_type** | `<entità>_<azione>` per successo, `<entità>_<azione>_failed` per errore |

---

## 1) Quando aggiungere `publish_log`

`publish_log` deve essere chiamato in **tutti** gli endpoint che scrivono a database:

- **Scritture dirette**: `db.session.add()`, `db.session.commit()`, `db.session.delete()`
- **Scritture indirette**: chiamate a funzioni utility che internamente scrivono a DB (es. `reset_user_password()`, `send_password_reset_email()`)
- **Scritture implicite**: view che usano i metodi CRUD di dFlango (`post_create`, `post_edit`, `post_delete`)

### Eccezioni

- **Login e logout**: esclusi dal logging via `publish_log`
- **Operazioni di sola lettura**: non richiedono `publish_log`

---

## 2) Dove posizionare `publish_log` nel codice

### Caso successo — Scrittura diretta con try/except

```python
try:
    db.session.add(instance)
    db.session.commit()
except Exception as e:
    db.session.rollback()
    logging.error(f"Error creating resource: {e}")
    publish_log(
        event_type="resource_create_failed",
        user=current_user,
        meta={"error": str(e)}
    )
    return jsonify({"error": "Failed to create resource"}), 400

publish_log(
    event_type="resource_created",
    user=current_user,
    meta={"resource_id": str(instance.id)}
)
return jsonify(schema.dump(instance)), 201
```

**Regole di posizionamento:**
- Il log di **successo** va subito **dopo** il `db.session.commit()` (o dopo il blocco try/except)
- Il log di **errore** va dentro il blocco `except`, **dopo** il `db.session.rollback()` e il `logging.error()`

### Caso successo — Scrittura indiretta (utility function)

```python
try:
    some_utility_function(params)
except Exception as e:
    logging.error(f"Error: {e}")
    publish_log(
        event_type="action_failed",
        user=current_user,
        meta={"error": str(e)}
    )
    return jsonify({"error": "Operation failed"}), 400

publish_log(
    event_type="action_completed",
    user=current_user,
    meta={"relevant_field": value}
)
return jsonify({"message": "Success"}), 200
```

### Caso successo — Hook dFlango (`post_create`, `post_edit`, `post_delete`)

```python
def post_edit(self, old_instance, instance):
    logging.info(f"Resource updated: {instance.id}")
    current_user = self.get_current_user()
    publish_log(
        event_type="resource_updated",
        user=current_user,
        meta={"resource_id": str(instance.id)}
    )
```

---

## 3) Convenzioni di naming per `event_type`

Il formato standard è: `<entità>_<azione>` per successo, `<entità>_<azione>_failed` per errore.

### Esempi

| Operazione | event_type successo | event_type errore |
| --- | --- | --- |
| Creazione utente | `user_created` | `user_create_failed` |
| Aggiornamento utente | `user_updated` | `user_update_failed` |
| Soft delete utente | `user_account_deleted` | `user_account_delete_failed` |
| Blocco utente | `user_blocked` | `user_block_failed` |
| Sblocco utente | `user_unblocked` | `user_unblock_failed` |
| Cambio ruolo | `user_role_changed` | `user_role_change_failed` |
| Cambio password | `password_changed` | `password_change_failed` |
| Reset password | `password_reset_success` | `password_reset_failed` |
| Richiesta reset password | `forgot_password_requested` | `forgot_password_failed` |
| Richiesta cambio email | `email_change_requested` | `email_change_request_failed` |
| Conferma cambio email | `email_change_confirmed` | `email_change_confirm_failed` |

---

## 4) Parametri di `publish_log`

```python
publish_log(event_type, user=None, meta=None)
```

| Parametro | Tipo | Obbligatorio | Descrizione |
| --- | --- | --- | --- |
| `event_type` | `str` | Sì | Identificativo univoco dell'evento (vedi naming sopra) |
| `user` | `dict` | No | Dizionario con dati dell'utente che ha eseguito l'azione. Ottenuto da `self.get_current_user()`. Contiene: `id`, `email`, `username`, `first_name`, `last_name` |
| `meta` | `dict` | No | Metadati aggiuntivi specifici dell'evento |

### Contenuto di `meta`

Il campo `meta` deve includere informazioni utili per l'audit trail:

**Per operazioni su risorse proprie:**
```python
meta={"field_changed": "new_value"}
```

**Per operazioni su risorse altrui (admin action):**
```python
meta={
    "target_user_id": str(user.id),
    "target_user_email": user.email,
    "old_roles": old_roles,       # solo se pertinente
    "new_roles": new_roles,       # solo se pertinente
}
```

**Per errori:**
```python
meta={"error": str(e)}
```

### Regole su `user`

- Passare sempre `user=self.get_current_user()` per endpoint autenticati
- Per endpoint non autenticati (es. `forgot_password`, `reset_password`) omettere `user` o passare `None`
- Non loggare mai **dati sensibili** (password, token) nel campo `meta`

---

## 5) Import necessari

Aggiungere nella sezione `# Services` degli import in cima al file:

```python
# Services
from app.services.pubsub.logs import publish_log
```

L'ordine import segue la convenzione standard:
```
Built-in → Flask → dFlango → Third-party → Models → Schemas → Constants → Utils → Services
```

---

## 6) Checklist per endpoint con scrittura a DB

- [ ] Import di `publish_log` aggiunto in cima al file
- [ ] `current_user = self.get_current_user()` recuperato prima del blocco try/except (se endpoint autenticato)
- [ ] `publish_log` con event_type di **successo** aggiunto dopo il commit/operazione riuscita
- [ ] `publish_log` con event_type `_failed` aggiunto in ogni blocco `except`
- [ ] `meta` contiene informazioni utili per l'audit (ID risorsa, email, campi modificati)
- [ ] Nessun dato sensibile nel `meta` (password, token, secret)
- [ ] L'endpoint non è login o logout
