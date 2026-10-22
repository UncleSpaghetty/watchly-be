from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.models.episode_availability import EpisodeAvailability
from app.models.service import Service
from app.services.timeutil import to_local_date

# Priorità per riassumere più evidenze sullo stesso episodio.
STATUS_RANK = {"confirmed": 0, "estimated": 1, "disputed": 2, "withdrawn": 3, "unknown": 4}


class AvailabilityError(ValueError):
    pass


def is_effective(row: EpisodeAvailability, source: DataSource | None) -> bool:
    """Una conferma vale solo se non invalidata e supportata da una fonte validata."""
    if row.status != "confirmed":
        return True
    return (
        row.invalidated_at is None
        and source is not None
        and source.italy_episode_availability_validated
        and source.validated_at is not None
    )


def record_availability(
    db: Session,
    *,
    episode_id: object,
    service_id: str,
    source_id: str,
    status: str,
    evidence_type: str | None,
    source_record_id: str | None = None,
    source_url: str | None = None,
    available_at_utc: datetime | None = None,
    available_local_date: date | None = None,
    now: datetime | None = None,
) -> EpisodeAvailability:
    """Registra un'evidenza di disponibilità italiana, applicando le regole di correttezza:
    `confirmed` richiede fonte validata, piattaforma, tipo di evidenza e precisione."""
    now = now or datetime.now(UTC)
    if status not in STATUS_RANK:
        raise AvailabilityError(f"Stato non valido: {status}")
    source = db.get(DataSource, source_id)
    if source is None or db.get(Service, service_id) is None:
        raise AvailabilityError("Fonte o piattaforma sconosciuta")

    if available_at_utc is not None:
        precision: str | None = "timestamp"
        available_local_date = to_local_date(available_at_utc)
    elif available_local_date is not None:
        precision = "date"
    else:
        precision = None

    if status == "confirmed":
        if not (source.italy_episode_availability_validated and source.validated_at):
            raise AvailabilityError("Fonte non validata per la disponibilità italiana")
        if not evidence_type or precision is None:
            raise AvailabilityError("Una conferma richiede evidenza e data")

    row = None
    if source_record_id:
        row = db.scalar(
            select(EpisodeAvailability).where(
                EpisodeAvailability.source_id == source_id,
                EpisodeAvailability.source_record_id == source_record_id,
            )
        )
    if row is None:
        row = EpisodeAvailability(
            episode_id=episode_id, country_code="IT", observed_at=now, source_id=source_id
        )
        db.add(row)
    row.service_id = service_id
    row.status = status
    row.precision = precision
    row.available_at_utc = available_at_utc
    row.available_local_date = available_local_date
    row.evidence_type = evidence_type
    row.source_record_id = source_record_id
    row.source_url = source_url
    row.last_verified_at = now
    row.invalidated_at = None if status != "withdrawn" else now
    db.flush()
    return row
