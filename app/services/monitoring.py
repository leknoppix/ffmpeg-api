from datetime import datetime, timezone
from dataclasses import dataclass, field
import threading


@dataclass
class Metrics:
    jobs_created: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    total_bytes_processed: int = 0
    conversions_by_format: dict[str, int] = field(default_factory=dict)
    cleanup_runs: int = 0
    cleanup_files_removed: int = 0
    cleanup_bytes_freed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def increment_created(self):
        with self._lock:
            self.jobs_created += 1

    def increment_completed(self, output_format: str, bytes_processed: int = 0):
        with self._lock:
            self.jobs_completed += 1
            self.total_bytes_processed += bytes_processed
            self.conversions_by_format[output_format] = self.conversions_by_format.get(output_format, 0) + 1

    def increment_failed(self):
        with self._lock:
            self.jobs_failed += 1

    def add_cleanup_stats(self, files_removed: int, bytes_freed: int):
        with self._lock:
            self.cleanup_runs += 1
            self.cleanup_files_removed += files_removed
            self.cleanup_bytes_freed += bytes_freed

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "jobs_created": self.jobs_created,
                "jobs_completed": self.jobs_completed,
                "jobs_failed": self.jobs_failed,
                "jobs_pending": self.jobs_created - self.jobs_completed - self.jobs_failed,
                "total_bytes_processed": self.total_bytes_processed,
                "conversions_by_format": dict(self.conversions_by_format),
                "cleanup_runs": self.cleanup_runs,
                "cleanup_files_removed": self.cleanup_files_removed,
                "cleanup_bytes_freed": self.cleanup_bytes_freed,
            }


metrics = Metrics()
