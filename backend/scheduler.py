"""APScheduler: daily/weekly strategy run (before US open) + quarterly suggestion engine."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal
from models import SystemState
import strategy
import suggestions

logger = logging.getLogger("scheduler")
_scheduler = None

# ~09:00 ET before market open ≈ 13:00 UTC (DST-approximate; fine for daily cadence)
RUN_HOUR_UTC = 13
RUN_MINUTE_UTC = 0


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


def _strategy_trigger(frequency):
    if frequency == "weekly":
        return CronTrigger(day_of_week="mon", hour=RUN_HOUR_UTC, minute=RUN_MINUTE_UTC, timezone="UTC")
    return CronTrigger(day_of_week="mon-fri", hour=RUN_HOUR_UTC, minute=RUN_MINUTE_UTC, timezone="UTC")


def reschedule_strategy(frequency):
    """Re-arm the strategy job when the cadence setting changes."""
    if not _scheduler:
        return
    _scheduler.add_job(_strategy_job, _strategy_trigger(frequency), id="strategy",
                       max_instances=1, coalesce=True, replace_existing=True)
    logger.info("strategy job rescheduled: %s", frequency)


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    db = SessionLocal()
    try:
        state = db.query(SystemState).get(1)
        freq = state.schedule_frequency if state else "daily"
    finally:
        db.close()
    _scheduler.add_job(_strategy_job, _strategy_trigger(freq), id="strategy",
                       max_instances=1, coalesce=True, replace_existing=True)
    # suggestions quarterly (1st of Jan/Apr/Jul/Oct), gated by sample size inside the engine
    _scheduler.add_job(_suggestion_job, CronTrigger(month="1,4,7,10", day=1, hour=0, minute=0,
                       timezone="UTC"), id="suggestions", max_instances=1,
                       coalesce=True, replace_existing=True)
    _scheduler.start()
    logger.info("scheduler started (strategy=%s)", freq)
    return _scheduler
