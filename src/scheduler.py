import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings

logger = logging.getLogger(__name__)


def start_scheduler(settings: Settings) -> None:
    """Start APScheduler v3 BlockingScheduler with daily cron job."""
    scheduler = BlockingScheduler(timezone=settings.timezone)

    trigger = CronTrigger(
        hour=settings.schedule_hour,
        minute=settings.schedule_minute,
        timezone=settings.timezone,
    )

    def job() -> None:
        from src.pipeline import run_daily
        logger.info("Scheduled job starting")
        try:
            asyncio.run(run_daily(settings))
        except Exception as e:
            # Pipeline already finalizes run on error; just log here
            logger.error("Scheduled job failed: %s", e)

    scheduler.add_job(job, trigger=trigger)
    logger.info(
        "Scheduler started. Next run at %s:%02d %s",
        settings.schedule_hour,
        settings.schedule_minute,
        settings.timezone,
    )
    scheduler.start()
