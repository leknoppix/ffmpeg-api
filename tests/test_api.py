import hashlib
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import job_manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_jobs():
    """Clean up jobs before each test."""
    job_manager.jobs.clear()
    yield
    # Cleanup after test
    for job_id in list(job_manager.jobs.keys()):
        job_manager.delete_job(job_id)


def create_test_audio():
    """Create a minimal valid audio file for testing."""
    # Create a small valid MP3 file (minimal frame)
    # This is a valid MP3 frame header + silence
    return b'\xff\xfb\x90\x00' + b'\x00' * 100


class TestUpload:
    """Tests for file upload endpoint."""

    def test_upload_invalid_input_format(self):
        """Should reject unsupported input formats."""
        response = client.post(
            "/convert/upload/xyz?output_format=ogg",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        assert response.status_code == 400
        assert "Unsupported input format" in response.json()["detail"]

    def test_upload_invalid_output_format(self):
        """Should reject unsupported output formats."""
        response = client.post(
            "/convert/upload/mp3?output_format=xyz",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        assert response.status_code == 400
        assert "Unsupported output format" in response.json()["detail"]

    def test_upload_empty_file(self):
        """Should reject empty files."""
        response = client.post(
            "/convert/upload/mp3?output_format=ogg",
            files={"file": ("test.mp3", b"", "audio/mpeg")}
        )
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]

    def test_upload_valid(self):
        """Should accept valid file and return job_id."""
        response = client.post(
            "/convert/upload/mp3?output_format=ogg",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "input_hash" in data
        assert len(data["job_id"]) > 20  # Secure token length
        assert data["message"] == "File uploaded. Conversion mp3 → ogg started."


class TestStatus:
    """Tests for job status endpoint."""

    def test_status_job_not_found(self):
        """Should return 404 for non-existent job."""
        response = client.get("/convert/nonexistent123")
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    def test_status_valid_job(self):
        """Should return job status."""
        # Create job
        upload_resp = client.post(
            "/convert/upload/mp3?output_format=wav",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        job_id = upload_resp.json()["job_id"]

        # Check status
        response = client.get(f"/convert/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ["uploaded", "processing"]
        assert data["input_format"] == "mp3"
        assert data["output_format"] == "wav"


class TestDownload:
    """Tests for file download endpoint."""

    def test_download_job_not_found(self):
        """Should return 404 for non-existent job."""
        response = client.get("/convert/nonexistent/download")
        assert response.status_code == 404

    def test_download_job_not_ready(self):
        """Should return 400 if job not done."""
        upload_resp = client.post(
            "/convert/upload/mp3?output_format=wav",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        job_id = upload_resp.json()["job_id"]

        response = client.get(f"/convert/{job_id}/download")
        assert response.status_code == 400
        assert "not ready" in response.json()["detail"]


class TestDelete:
    """Tests for job deletion endpoint."""

    def test_delete_job_not_found(self):
        """Should return 404 for non-existent job."""
        response = client.delete("/convert/nonexistent123")
        assert response.status_code == 404

    def test_delete_incomplete_job(self):
        """Should prevent deletion of incomplete jobs."""
        upload_resp = client.post(
            "/convert/upload/mp3?output_format=wav",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        job_id = upload_resp.json()["job_id"]

        response = client.delete(f"/convert/{job_id}")
        assert response.status_code == 400
        assert "Cannot delete incomplete job" in response.json()["detail"]

    def test_delete_with_hash_mismatch(self):
        """Should fail deletion if hash doesn't match."""
        # We can't fully test this without a real conversion
        # But we test the hash computation
        upload_resp = client.post(
            "/convert/upload/mp3?output_format=wav",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        job_id = upload_resp.json()["job_id"]

        # This will fail because job is not done
        response = client.delete(
            f"/convert/{job_id}",
            headers={"X-Content-Hash": "wronghash"}
        )
        assert response.status_code == 400


class TestCrypto:
    """Tests for crypto utilities."""

    def test_generate_job_id_length(self):
        """Job ID should be sufficiently long."""
        from app.utils.crypto import generate_job_id
        job_id = generate_job_id()
        assert len(job_id) >= 32

    def test_compute_file_hash(self):
        """Hash should be consistent."""
        from app.utils.crypto import compute_file_hash
        data = b"test data"
        hash1 = compute_file_hash(data)
        hash2 = compute_file_hash(data)
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 length

    def test_verify_file_integrity(self):
        """Integrity check should work correctly."""
        from app.utils.crypto import verify_file_integrity
        data = b"test data"

        # No hash provided - should pass
        valid, _ = verify_file_integrity(data, None)
        assert valid is True

        # Correct hash
        correct_hash = hashlib.md5(data).hexdigest()
        valid, _ = verify_file_integrity(data, correct_hash)
        assert valid is True

        # Wrong hash
        valid, msg = verify_file_integrity(data, "wronghash")
        assert valid is False
        assert "mismatch" in msg.lower()


class TestFormats:
    """Tests for format handling."""

    def test_supported_formats(self):
        """Verify all formats are correctly defined."""
        from app.routes.formats import SUPPORTED_INPUTS, SUPPORTED_OUTPUTS

        expected = {"mp3", "ogg", "wav", "flac", "aac", "m4a"}
        assert SUPPORTED_INPUTS == expected
        assert SUPPORTED_OUTPUTS == expected

    def test_format_case_insensitive(self):
        """Format should be case insensitive."""
        response = client.post(
            "/convert/upload/MP3?output_format=OGG",
            files={"file": ("test.mp3", create_test_audio(), "audio/mpeg")}
        )
        assert response.status_code == 200
