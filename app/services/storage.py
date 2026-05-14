import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.job import JobStatus
from app.utils.crypto import generate_job_id


class Job:
    def __init__(
        self,
        job_id: str,
        input_format: str,
        output_format: str,
        original_filename: str,
        status: JobStatus = JobStatus.UPLOADED,
    ):
        self.job_id = job_id
        self.input_format = input_format
        self.output_format = output_format
        self.original_filename = original_filename
        self.status = status
        self.created_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.input_hash: Optional[str] = None
        self.output_hash: Optional[str] = None
        self.output_size: Optional[int] = None

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "input_format": self.input_format,
            "output_format": self.output_format,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "output_size": self.output_size,
        }


class JobManager:
    def __init__(self, storage_dir: str = "/tmp/convert"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir = self.storage_dir / "input"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}

    def create_job(self, input_format: str, output_format: str, filename: str) -> Job:
        job_id = generate_job_id()
        job = Job(job_id, input_format, output_format, filename)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        input_hash: Optional[str] = None,
        output_hash: Optional[str] = None,
        output_size: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        job = self.jobs.get(job_id)
        if not job:
            return

        if status:
            job.status = status
        if input_hash:
            job.input_hash = input_hash
        if output_hash:
            job.output_hash = output_hash
        if output_size is not None:
            job.output_size = output_size
        if error_message:
            job.error_message = error_message

        if status in (JobStatus.DONE, JobStatus.FAILED):
            job.completed_at = datetime.now(timezone.utc)

    def get_input_path(self, job_id: str) -> Path:
        return self.input_dir / job_id

    def get_output_path(self, job_id: str, extension: str) -> Path:
        job = self.get_job(job_id)
        if job:
            base_name = Path(job.original_filename).stem
            # Use input hash for unique naming since output hash isn't available yet
            hash_part = job.input_hash[:8] if job.input_hash else job_id[:8]
            return self.storage_dir / f"{base_name}_{hash_part}.{extension}"
        return self.storage_dir / f"output_{job_id[:8]}.{extension}"

    def delete_job(self, job_id: str) -> bool:
        job = self.jobs.pop(job_id, None)
        if not job:
            return False

        input_path = self.get_input_path(job_id)
        if input_path.exists():
            input_path.unlink()

        return True

    def cleanup_stale_inputs(self):
        """Remove input files for completed jobs."""
        for job_id, job in list(self.jobs.items()):
            if job.status in (JobStatus.DONE, JobStatus.FAILED):
                input_path = self.get_input_path(job_id)
                if input_path.exists():
                    input_path.unlink()


job_manager = JobManager()