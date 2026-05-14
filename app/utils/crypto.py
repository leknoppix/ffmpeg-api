import hashlib
import secrets


def generate_job_id() -> str:
    """Generate a cryptographically secure job ID."""
    return secrets.token_urlsafe(32)


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute MD5 hash of file content."""
    return hashlib.md5(file_bytes).hexdigest()


def verify_file_integrity(file_bytes: bytes, expected_hash: str | None) -> tuple[bool, str]:
    """Verify file integrity against expected hash."""
    if not expected_hash:
        return True, ""

    actual_hash = compute_file_hash(file_bytes)
    matches = actual_hash.lower() == expected_hash.lower()

    if not matches:
        return False, f"Hash mismatch: expected {expected_hash}, got {actual_hash}"

    return True, ""