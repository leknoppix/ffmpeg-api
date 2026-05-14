import asyncio
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.job import JobStatus
from app.services.storage import job_manager
from app.services.monitoring import metrics

_FFMPEG_EXECUTOR = ThreadPoolExecutor(max_workers=2)


async def convert_audio(
    job_id: str,
    input_bytes: bytes,
    output_path: Path,
    output_format: str,
) -> tuple[bool, str]:
    """Convert audio file using ffmpeg."""
    job_manager.update_job(job_id, status=JobStatus.PROCESSING)

    codec_map = {
        "mp3": "libmp3lame",
        "ogg": "libvorbis",
        "wav": "pcm_s16le",
    }

    quality_args = ["-q:a", "2"] if output_format in ("mp3", "ogg") else []

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{output_format}") as tmp_input:
        tmp_input.write(input_bytes)
        tmp_input_path = tmp_input.name

    try:
        command = [
            "ffmpeg",
            "-y",
            "-i", tmp_input_path,
        ]

        if output_format in codec_map:
            command.extend(["-acodec", codec_map[output_format]])

        command.extend(quality_args)
        command.append(str(output_path))

        def _run_ffmpeg():
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )
            return process.returncode, process.stderr

        loop = asyncio.get_event_loop()
        returncode, error_msg = await loop.run_in_executor(
            _FFMPEG_EXECUTOR, _run_ffmpeg
        )

        if returncode != 0:
            job_manager.update_job(
                job_id,
                status=JobStatus.FAILED,
                error_message=f"FFmpeg error: {error_msg[:500]}" if error_msg else "Unknown error",
            )
            metrics.increment_failed()
            return False, error_msg or "Unknown error"

        output_size = output_path.stat().st_size
        with open(output_path, "rb") as f:
            output_hash = hashlib.md5(f.read()).hexdigest()

        job_manager.update_job(
            job_id,
            status=JobStatus.DONE,
            output_hash=output_hash,
            output_size=output_size,
        )
        metrics.increment_completed(output_format, output_size)
        return True, ""

    finally:
        Path(tmp_input_path).unlink(missing_ok=True)


def get_audio_info(path: Path) -> dict:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    except Exception:
        return {}
