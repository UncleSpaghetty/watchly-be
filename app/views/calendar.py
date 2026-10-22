from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.errors import ApiError
from app.schemas.calendar import CalendarItem, CalendarResponse
from app.schemas.episode import AvailabilityRead
from app.schemas.series import SeriesSummary
from app.services.calendar import MAX_RANGE_DAYS, build_calendar
from app.settings.security import CurrentUser, Db

router = APIRouter(prefix="/me", tags=["calendar"])


@router.get("/calendar", response_model=CalendarResponse)
def calendar(
    user: CurrentUser,
    db: Db,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    mode: Literal["all", "italy"] = "all",
    kind: Literal["anime", "tv"] | None = None,
    watched: bool | None = None,
) -> CalendarResponse:
    if end < start:
        raise ApiError(422, "invalid_range", "end precede start")
    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise ApiError(422, "range_too_large", f"Intervallo massimo {MAX_RANGE_DAYS} giorni")
    entries = build_calendar(db, user.id, start, end, mode=mode, kind=kind, watched=watched)
    return CalendarResponse(
        start=start,
        end=end,
        timezone="Europe/Rome",
        items=[
            CalendarItem(
                episode_id=e.episode.id,
                series=SeriesSummary.model_validate(e.series),
                season_number=e.episode.season_number,
                episode_number=e.episode.episode_number,
                title=e.episode.title,
                local_date=e.local_date,
                date_kind=e.date_kind,
                italy=AvailabilityRead(**vars(e.availability)),
                watched=e.watched,
            )
            for e in entries
        ],
    )
