from datetime import timedelta

from flask import request

from app.errors import ApiError
from app.schemas.calendar import CalendarItem
from app.services.calendar import MAX_RANGE_DAYS, build_calendar
from app.views.base import WatchlyView, query_bool, query_date


class CalendarView(WatchlyView):
    accepted_methods = ["GET"]

    def get(self):
        start, end = query_date("start"), query_date("end")
        kind = request.args.get("kind")
        watched = query_bool("watched")
        if end < start:
            raise ApiError(422, "invalid_range", "end precede start")
        if end - start > timedelta(days=MAX_RANGE_DAYS):
            raise ApiError(422, "range_too_large", f"Intervallo massimo {MAX_RANGE_DAYS} giorni")
        if kind not in {None, "anime", "tv"}:
            raise ApiError(422, "validation_error", "Filtro calendario non valido")
        entries = build_calendar(self.session, self.user.id, start, end, kind=kind, watched=watched)
        items = [
            CalendarItem().dump(
                {
                    "episode_id": entry.episode.id,
                    "series": entry.series,
                    "season_number": entry.episode.season_number,
                    "episode_number": entry.episode.episode_number,
                    "title": entry.episode.title,
                    "air_date": entry.air_date,
                    "source": entry.episode.source,
                    "watched": entry.watched,
                }
            )
            for entry in entries
        ]
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": "Europe/Rome",
            "items": items,
        }
