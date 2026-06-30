"""APScheduler wiring for the strategy loop and weekly suggestion engine."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from models import SystemState
import strategy
import suggestions

logger = logging.getLogger("scheduler")
_scheduler = None


def _strategy_job():
    db = SessionLocal()
    try:
        state = db.query(SystemState).get(1)
        if state and not state.scheduler_enabled:
            return
        result = strategy.run_strategy(db, manual=False)
        logger.info("scheduled strategy run: %s", result)
    except Exception as e:
        logger.exception("strategy job failed: %s", e)
    finally:
        db.close()


def _suggestion_job():
    db = SessionLocal()
    try:
        n = suggestions.generate_all(db)
        logger.info("scheduled suggestion run created %s suggestions", n)
    except Exception as e:
        logger.exception("suggestion job failed: %s", e)
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    # strategy every 20 minutes
    _scheduler.add_job(_strategy_job, "interval", minutes=20, id="strategy",
                       max_instances=1, coalesce=True)
    # suggestions weekly (Sunday 00:00 UTC)
    _scheduler.add_job(_suggestion_job, "cron", day_of_week="sun", hour=0, minute=0,
                       id="suggestions", max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info("scheduler started")
    return _scheduler
