"""Worker: esegue i job di sync in coda, il refresh periodico, le news e le notifiche push."""

import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from types import FrameType

from sqlalchemy import select, update

from app.models.session import get_session_factory
from app.models.sync_run import SyncRun
from app.services.bootstrap import bootstrap
from app.services.news import refresh_news
from app.services.notifications import send_due_notifications
from app.services.sync import claim_run, enqueue_run, execute_run, last_run_at
from app.settings.config import Settings, get_settings
from app.settings.logging import configure_logging

logger = logging.getLogger("app.worker")
STALE_RUNNING = timedelta(minutes=30)
_stop = False


def _handle_stop(signum: int, frame: FrameType | None) -> None:
    global _stop
    _stop = True


def recover_stale_runs() -> None:
    """Job rimasti «running» per un crash del worker vengono chiusi come falliti."""
    with get_session_factory()() as db:
        db.execute(
            update(SyncRun)
            .where(
                SyncRun.status == "running", SyncRun.started_at < datetime.now(UTC) - STALE_RUNNING
            )
            .values(
                status="failed",
                error="Interrotto (worker riavviato)",
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()


def tick(settings: Settings) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)

    with factory() as db:
        for kind, interval in (
            ("scheduled", timedelta(hours=settings.sync_interval_hours)),
            ("news", timedelta(minutes=settings.news_refresh_minutes)),
        ):
            if kind == "news" and not settings.news_feed_urls:
                continue
            latest = last_run_at(db, kind)
            if latest is None or now - latest >= interval:
                enqueue_run(db, kind)

        pending = db.scalars(
            select(SyncRun)
            .where(SyncRun.status == "pending")
            .order_by(SyncRun.created_at)
            .limit(20)
        ).all()
        run_ids = [r.id for r in pending]

    for run_id in run_ids:
        with factory() as db:
            if not claim_run(db, run_id):
                continue
            run = db.get(SyncRun, run_id)
            if run is None:
                continue
            try:
                if run.kind == "news":
                    errors = refresh_news(db, settings.news_feed_urls)
                    run.status = "partial" if errors else "succeeded"
                    run.details = {"errors": errors}
                    run.completed_at = datetime.now(UTC)
                    db.commit()
                else:
                    execute_run(db, run)
            except Exception:
                db.rollback()
                logger.exception("run %s crashed", run_id)
                run = db.get(SyncRun, run_id)
                if run:
                    run.status, run.error = "failed", "Errore interno"
                    run.completed_at = datetime.now(UTC)
                    db.commit()

    with factory() as db:
        try:
            send_due_notifications(db, settings)
        except Exception:
            db.rollback()
            logger.exception("notification dispatch failed")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    with get_session_factory()() as db:
        bootstrap(db, settings)
    recover_stale_runs()
    logger.info("worker started")
    while not _stop:
        try:
            tick(settings)
        except Exception:
            logger.exception("worker tick failed")
        for _ in range(settings.worker_tick_seconds):
            if _stop:
                break
            time.sleep(1)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
