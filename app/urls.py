# Built-in
from typing import Any

# dFlango
from dflango.routes import RouteRegistry

# Flask
from flask import Blueprint

# Views
from app.views.auth.google_login import GoogleLoginView
from app.views.auth.login import LoginView
from app.views.auth.logout import LogoutView
from app.views.auth.me import MeView
from app.views.calendar.calendar_list import CalendarView
from app.views.catalog.catalog_search import CatalogSearchView
from app.views.dashboard.dashboard_detail import DashboardView
from app.views.episode.watched_detail import WatchedView
from app.views.following.following_detail import FollowingDetailView
from app.views.following.following_list import FollowingListView
from app.views.health import LiveView, ReadyView
from app.views.news.news_list import NewsView
from app.views.news.news_state_detail import NewsStateView
from app.views.push.push_subscription_detail import PushSubscriptionDetailView
from app.views.push.push_subscription_list import PushSubscriptionsView
from app.views.push.vapid_key_detail import VapidKeyView
from app.views.series.series_detail import SeriesDetailView
from app.views.series.series_episode_list import SeriesEpisodesView
from app.views.series.series_refresh import SeriesRefreshView
from app.views.series.series_watched_detail import SeriesWatchedView
from app.views.sync.job_detail import JobView
from app.views.sync.sync_create import SyncView
from app.views.user_settings.user_settings_detail import UserSettingsView


class WatchlyRoutes(RouteRegistry):
    blueprint: Any = Blueprint("watchly", __name__)
    urlpatterns = [
        ("/health/live", LiveView.as_view("health_live")),
        ("/health/ready", ReadyView.as_view("health_ready")),
        ("/api/v1/auth/login", LoginView.as_view("auth_login")),
        ("/api/v1/auth/google", GoogleLoginView.as_view("auth_google")),
        ("/api/v1/auth/logout", LogoutView.as_view("auth_logout")),
        ("/api/v1/me", MeView.as_view("me")),
        ("/api/v1/catalog/search", CatalogSearchView.as_view("catalog_search")),
        ("/api/v1/me/calendar", CalendarView.as_view("calendar")),
        ("/api/v1/me/dashboard", DashboardView.as_view("dashboard")),
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
        ("/api/v1/me/news/<uuid:news_id>", NewsStateView.as_view("news_state")),
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
        (
            "/api/v1/me/series/<uuid:series_id>/watched",
            SeriesWatchedView.as_view("series_watched"),
        ),
        ("/api/v1/me/sync", SyncView.as_view("sync")),
        ("/api/v1/jobs/<uuid:job_id>", JobView.as_view("job")),
        ("/api/v1/me/settings", UserSettingsView.as_view("user_settings")),
    ]
