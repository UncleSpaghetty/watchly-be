from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter

from app.errors import ApiError
from app.models.episode import Episode
from app.models.watched_episode import WatchedEpisode
from app.schemas.episode import WatchedRead
from app.settings.security import CurrentUser, Db

router = APIRouter(prefix="/me/episodes", tags=["episodes"])


def _ensure_episode(db: Db, episode_id: UUID) -> None:
    if db.get(Episode, episode_id) is None:
        raise ApiError(404, "episode_not_found", "Episodio non trovato")


@router.put("/{episode_id}/watched", response_model=WatchedRead)
def mark_watched(episode_id: UUID, user: CurrentUser, db: Db) -> WatchedRead:
    _ensure_episode(db, episode_id)
    row = db.get(WatchedEpisode, (user.id, episode_id))
    if row is None:
        row = WatchedEpisode(user_id=user.id, episode_id=episode_id, watched_at=datetime.now(UTC))
        db.add(row)
        db.commit()
    return WatchedRead(episode_id=episode_id, watched=True, watched_at=row.watched_at)


@router.delete("/{episode_id}/watched", response_model=WatchedRead)
def unmark_watched(episode_id: UUID, user: CurrentUser, db: Db) -> WatchedRead:
    _ensure_episode(db, episode_id)
    row = db.get(WatchedEpisode, (user.id, episode_id))
    if row is not None:
        db.delete(row)
        db.commit()
    return WatchedRead(episode_id=episode_id, watched=False, watched_at=None)
