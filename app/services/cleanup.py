import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.services.storage import job_manager
from app.services.monitoring import metrics

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 3600
MAX_FILE_AGE = timedelta(hours=12)


async def cleanup_old_files():
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)

            storage_dir = job_manager.storage_dir
            input_dir = job_manager.input_dir
            cutoff_time = datetime.now(timezone.utc) - MAX_FILE_AGE

            cleaned_count = 0
            freed_bytes = 0

            for file_path in storage_dir.iterdir():
                if file_path.is_file() and file_path.suffix in {'.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a'}:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff_time:
                        size = file_path.stat().st_size
                        file_path.unlink()
                        cleaned_count += 1
                        freed_bytes += size
                        logger.info(f"Cleaned output: {file_path.name} ({size} bytes)")

            if input_dir.exists():
                for file_path in input_dir.iterdir():
                    if file_path.is_file():
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                        if mtime < cutoff_time:
                            size = file_path.stat().st_size
                            file_path.unlink()
                            cleaned_count += 1
                            freed_bytes += size
                            logger.info(f"Cleaned input: {file_path.name}")

            if cleaned_count > 0:
                metrics.add_cleanup_stats(cleaned_count, freed_bytes)
                logger.info(f"Cleanup: {cleaned_count} files, {freed_bytes} bytes freed")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


def start_cleanup_task():
    task = asyncio.create_task(cleanup_old_files())
    return task
