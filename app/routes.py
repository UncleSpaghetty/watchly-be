from typing import Any

from dflango.routes import RouteRegistry
from flask import Blueprint

from app.views.auth import LoginView, LogoutView, MeView
from app.views.calendar import CalendarView
from app.views.catalog import CatalogSearchView
from app.views.episode import WatchedView
from app.views.following import FollowingDetailView, FollowingListView
from app.views.health import LiveView, ReadyView
from app.views.news import NewsView
from app.views.push import PushSubscriptionDetailView, PushSubscriptionsView, VapidKeyView
from app.views.series import SeriesDetailView, SeriesEpisodesView, SeriesRefreshView
from app.views.sync import JobView, SyncView
from app.views.user_settings import UserSettingsView


class WatchlyRoutes(RouteRegistry):
    blueprint: Any = Blueprint("watchly", __name__)
    urlpatterns = [
        ("/health/live", LiveView.as_view("health_live")),
        ("/health/ready", ReadyView.as_view("health_ready")),
        ("/api/v1/auth/login", LoginView.as_view("auth_login")),
        ("/api/v1/auth/logout", LogoutView.as_view("auth_logout")),
        ("/api/v1/me", MeView.as_view("me")),
        ("/api/v1/catalog/search", CatalogSearchView.as_view("catalog_search")),
        ("/api/v1/me/calendar", CalendarView.as_view("calendar")),
        ("/api/v1/me/following", FollowingListView.as_view("following_list")),
        (
            "/api/v1/me/following/<uuid:series_id>",
            FollowingDetailView.as_view("following_detail"),
        ),
        (
            "/api/v1/me/episodes/<uuid:episode_id>/watched",
            WatchedView.as_view("episode_watched"),
        ),
        ("/api/v1/news", NewsView.as_view("news")),
        ("/api/v1/push/vapid-public-key", VapidKeyView.as_view("vapid_key")),
        (
            "/api/v1/me/push-subscriptions",
            PushSubscriptionsView.as_view("push_subscriptions"),
        ),
        (
            "/api/v1/me/push-subscriptions/<uuid:subscription_id>",
            PushSubscriptionDetailView.as_view("push_subscription_detail"),
        ),
        ("/api/v1/series/<uuid:series_id>", SeriesDetailView.as_view("series_detail")),
        (
            "/api/v1/series/<uuid:series_id>/episodes",
            SeriesEpisodesView.as_view("series_episodes"),
        ),
        (
            "/api/v1/series/<uuid:series_id>/refresh",
            SeriesRefreshView.as_view("series_refresh"),
        ),
        ("/api/v1/me/sync", SyncView.as_view("sync")),
        ("/api/v1/jobs/<uuid:job_id>", JobView.as_view("job")),
        ("/api/v1/me/settings", UserSettingsView.as_view("user_settings")),
    ]
