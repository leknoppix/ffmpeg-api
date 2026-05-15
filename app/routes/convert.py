import asyncio
import hashlib
import os
from fastapi import APIRouter, Header, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.routes.formats import SUPPORTED_INPUTS, SUPPORTED_OUTPUTS
from app.services.storage import job_manager
from app.services.converter import convert_audio
from app.services.monitoring import metrics
from app.utils.crypto import compute_file_hash
from app.services.job import JobStatus

router = APIRouter()
security = HTTPBasic()


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    username = os.environ.get("AUTH_USERNAME", "admin")
    password = os.environ.get("AUTH_PASSWORD", "changeme")

    if credentials.username != username or credentials.password != password:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class UploadResponse(BaseModel):
    """Response after successful file upload."""
    job_id: str
    input_hash: str
    message: str


class StatusResponse(BaseModel):
    """Job status information."""
    job_id: str
    status: str
    input_format: str
    output_format: str
    input_hash: str | None
    output_hash: str | None
    output_size: int | None
    created_at: str
    completed_at: str | None
    error_message: str | None = None


class DeleteResponse(BaseModel):
    """Response after job deletion."""
    message: str
    deleted: bool
    hash_verified: bool | None = None


class DownloadDeleteResponse(BaseModel):
    """
    Response for download-and-delete operation.

    - success=True: fichier téléchargé et supprimé avec succès
    - success=False: hash mismatch, fichier conservé, job_id retourné pour retry
    """
    success: bool
    message: str
    job_id: str
    hash_verified: bool | None = None


class MetricsResponse(BaseModel):
    jobs_created: int
    jobs_completed: int
    jobs_failed: int
    jobs_pending: int
    total_bytes_processed: int
    conversions_by_format: dict[str, int]
    cleanup_runs: int
    cleanup_files_removed: int
    cleanup_bytes_freed: int


@router.post(
    "/upload/{input_format}",
    response_model=UploadResponse,
    summary="Upload and convert",
    description="Upload an audio file. Conversion starts automatically. Returns a job_id for tracking.",
)
async def upload_file(
    input_format: str,
    output_format: str,
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    input_format = input_format.lower()
    output_format = output_format.lower()

    if input_format not in SUPPORTED_INPUTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported input format: {input_format}. Supported: {', '.join(SUPPORTED_INPUTS)}",
        )

    if output_format not in SUPPORTED_OUTPUTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported output format: {output_format}. Supported: {', '.join(SUPPORTED_OUTPUTS)}",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    input_hash = compute_file_hash(contents)
    job = job_manager.create_job(input_format, output_format, file.filename or "unknown")
    job_manager.update_job(job.job_id, input_hash=input_hash)

    metrics.increment_created()

    output_path = job_manager.get_output_path(job.job_id, output_format)

    asyncio.create_task(
        convert_audio(job.job_id, contents, output_path, output_format)
    )

    return UploadResponse(
        job_id=job.job_id,
        input_hash=input_hash,
        message=f"File uploaded. Conversion {input_format} → {output_format} started.",
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="API monitoring metrics",
    description="Get conversion statistics and job counts.",
)
async def get_metrics(username: str = Depends(get_current_user)):
    """Return current API metrics."""
    return MetricsResponse(**metrics.to_dict())


@router.get(
    "/{job_id}",
    response_model=StatusResponse,
    summary="Get job status",
    description="Check the status of a conversion job.",
)
async def get_status(job_id: str, username: str = Depends(get_current_user)):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        input_format=job.input_format,
        output_format=job.output_format,
        input_hash=job.input_hash,
        output_hash=job.output_hash,
        output_size=job.output_size,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message,
    )


@router.get(
    "/{job_id}/download",
    summary="Download converted file",
    description="Download the converted audio file.",
)
async def download_file(job_id: str, username: str = Depends(get_current_user)):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not ready. Current status: {job.status.value}",
        )

    output_path = job_manager.get_output_path(job.job_id, job.output_format)

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type="application/octet-stream",
    )


@router.post(
    "/{job_id}/download-delete",
    response_model=DownloadDeleteResponse,
    summary="Download and delete with hash verification",
    description="""
    Download the converted file, verify its hash, and delete it.

    **Workflow:**
    1. Download the file locally
    2. Compute MD5 hash of downloaded file
    3. Call this endpoint with `X-Content-Hash` header
    4. If hash matches → file deleted, returns `success: true`
    5. If hash mismatch → file kept, returns `success: false` with job_id for retry
    """,
)
async def download_and_delete(
    job_id: str,
    x_content_hash: str | None = Header(None, alias="X-Content-Hash"),
    username: str = Depends(get_current_user),
):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not ready. Current status: {job.status.value}",
        )

    output_path = job_manager.get_output_path(job.job_id, job.output_format)

    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    with open(output_path, "rb") as f:
        file_content = f.read()
    actual_hash = hashlib.md5(file_content).hexdigest()

    if x_content_hash:
        if actual_hash.lower() != x_content_hash.lower():
            return DownloadDeleteResponse(
                success=False,
                message=f"Hash mismatch! Expected: {x_content_hash}, Got: {actual_hash}. File NOT deleted.",
                job_id=job_id,
                hash_verified=False,
            )

    output_path.unlink()
    job_manager.delete_job(job_id)

    return DownloadDeleteResponse(
        success=True,
        message="File downloaded and deleted successfully. Hash verified.",
        job_id=job_id,
        hash_verified=x_content_hash is not None,
    )


@router.delete(
    "/{job_id}",
    response_model=DeleteResponse,
    summary="Delete job and files",
    description="""
    Delete a conversion job and its output file.

    **Optional hash verification:**
    - Without header: deletes file unconditionally
    - With `X-Content-Hash` header: verifies hash first, returns error if mismatch

    Returns 409 Conflict if hash mismatch, 404 if job not found.
    """,
)
async def delete_job(
    job_id: str,
    x_content_hash: str | None = Header(None, alias="X-Content-Hash"),
    username: str = Depends(get_current_user),
):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete incomplete job. Current status: {job.status.value}",
        )

    output_path = job_manager.get_output_path(job.job_id, job.output_format)

    if x_content_hash:
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="Output file not found")

        with open(output_path, "rb") as f:
            actual_hash = compute_file_hash(f.read())

        if actual_hash.lower() != x_content_hash.lower():
            raise HTTPException(
                status_code=409,
                detail=f"Hash mismatch! Expected: {x_content_hash}, Got: {actual_hash}",
            )
        hash_verified = True
    else:
        hash_verified = None

    if output_path.exists():
        output_path.unlink()

    job_manager.delete_job(job_id)

    return DeleteResponse(
        message="Job deleted successfully",
        deleted=True,
        hash_verified=hash_verified,
    )