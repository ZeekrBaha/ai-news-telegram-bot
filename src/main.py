import argparse
import asyncio
import logging

from src.config import Settings


def setup_logging(level: str) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # basicConfig is a no-op if handlers are already set; explicitly set the level
    logging.getLogger().setLevel(log_level)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Aggregator Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Run without publishing to Telegram")
    args = parser.parse_args()

    settings = Settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    if args.once or args.dry_run:
        logger.info("Running once (dry_run=%s)", args.dry_run)
        from src.pipeline import run_daily
        asyncio.run(run_daily(settings, dry_run=args.dry_run))
    else:
        logger.info("Starting scheduler")
        from src.scheduler import start_scheduler
        start_scheduler(settings)


if __name__ == "__main__":
    main()
