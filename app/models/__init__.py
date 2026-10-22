"""Importa tutti i modelli perché Alembic/Base.metadata li veda."""

from app.models.auth_session import AuthSession
from app.models.base import Base
from app.models.data_source import DataSource
from app.models.episode import Episode
from app.models.episode_availability import EpisodeAvailability
from app.models.episode_date_change import EpisodeDateChange
from app.models.following import Following
from app.models.news_article import NewsArticle
from app.models.news_series_link import NewsSeriesLink
from app.models.notification_delivery import NotificationDelivery
from app.models.provider_cache import ProviderCache
from app.models.push_subscription import PushSubscription
from app.models.series import Series
from app.models.series_external_id import SeriesExternalId
from app.models.service import Service
from app.models.sync_run import SyncRun
from app.models.user import User
from app.models.watched_episode import WatchedEpisode

__all__ = [
    "AuthSession",
    "Base",
    "DataSource",
    "Episode",
    "EpisodeAvailability",
    "EpisodeDateChange",
    "Following",
    "NewsArticle",
    "NewsSeriesLink",
    "NotificationDelivery",
    "ProviderCache",
    "PushSubscription",
    "Series",
    "SeriesExternalId",
    "Service",
    "SyncRun",
    "User",
    "WatchedEpisode",
]
