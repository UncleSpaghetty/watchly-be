# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class DashboardKpisSchema(Schema):
    followed_series = fields.Integer(dump_only=True)
    watched_episodes = fields.Integer(dump_only=True)
    aired_episodes = fields.Integer(dump_only=True)
    completion_percentage = fields.Integer(dump_only=True)
    backlog_episodes = fields.Integer(dump_only=True)
    upcoming_7_days = fields.Integer(dump_only=True)
    upcoming_30_days = fields.Integer(dump_only=True)
    estimated_watch_minutes = fields.Integer(dump_only=True)
    duration_coverage_percentage = fields.Integer(dump_only=True)
    average_provider_rating = fields.Float(dump_only=True, allow_none=True)
    rated_series = fields.Integer(dump_only=True)
    current_activity_streak = fields.Integer(dump_only=True)
    longest_activity_streak = fields.Integer(dump_only=True)


class ActivityPointSchema(Schema):
    period_start = fields.Date(dump_only=True)
    watched_count = fields.Integer(dump_only=True)


class WatchlistBreakdownSchema(Schema):
    anime = fields.Integer(dump_only=True)
    tv = fields.Integer(dump_only=True)


class GenreItemSchema(Schema):
    name = fields.String(dump_only=True)
    count = fields.Integer(dump_only=True)


class GenreBreakdownSchema(Schema):
    basis = fields.String(dump_only=True)
    items = fields.List(fields.Nested(GenreItemSchema), dump_only=True)


class SeriesProgressSchema(Schema):
    series_id = fields.UUID(dump_only=True)
    title = fields.String(dump_only=True)
    poster_url = fields.String(dump_only=True, allow_none=True)
    kind = fields.String(dump_only=True)
    watched = fields.Integer(dump_only=True)
    aired = fields.Integer(dump_only=True)
    percentage = fields.Integer(dump_only=True)
    backlog = fields.Integer(dump_only=True)
    average_rating = fields.Float(dump_only=True, allow_none=True)


class TopSeriesSchema(Schema):
    series_id = fields.UUID(dump_only=True)
    title = fields.String(dump_only=True)
    poster_url = fields.String(dump_only=True, allow_none=True)
    watched = fields.Integer(dump_only=True)
    estimated_minutes = fields.Integer(dump_only=True)


class DashboardResponseSchema(Schema):
    generated_at = UtcDateTimeField(dump_only=True)
    timezone = fields.String(dump_only=True)
    period_weeks = fields.Integer(dump_only=True)
    kpis = fields.Nested(DashboardKpisSchema, dump_only=True)
    activity = fields.List(fields.Nested(ActivityPointSchema), dump_only=True)
    watchlist_breakdown = fields.Nested(WatchlistBreakdownSchema, dump_only=True)
    genres = fields.Nested(GenreBreakdownSchema, dump_only=True)
    series_progress = fields.List(fields.Nested(SeriesProgressSchema), dump_only=True)
    top_series = fields.List(fields.Nested(TopSeriesSchema), dump_only=True)
