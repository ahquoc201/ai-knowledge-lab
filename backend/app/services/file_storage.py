import re
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings

_STORAGE_KEY_PATTERN = re.compile(
    r"[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{4}-"
    r"[0-9a-f]{12}"
    r"\.[a-z0-9]{1,10}"
)


class InvalidStorageKeyError(ValueError):
    pass


def get_storage_directory() -> Path:
    settings = get_settings()

    return settings.upload_storage_dir.resolve()


def save_upload_file(
    *,
    filename: str,
    data: bytes,
) -> Path:
    storage_dir = get_storage_directory()

    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    extension = Path(filename).suffix.lower()
    storage_key = f"{uuid4()}{extension}"

    stored_path = storage_dir / storage_key

    with stored_path.open("xb") as file:
        file.write(data)

    return stored_path


def resolve_storage_path(
    storage_key: str,
) -> Path:
    if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise InvalidStorageKeyError(
            "Invalid storage key"
        )

    storage_dir = get_storage_directory()
    stored_path = storage_dir / storage_key

    if (
        stored_path.is_symlink()
        or not stored_path.resolve().is_relative_to(storage_dir)
    ):
        raise InvalidStorageKeyError(
            "Storage path is not allowed"
        )

    return stored_path


def read_stored_file(
    storage_key: str,
) -> bytes:
    stored_path = resolve_storage_path(
        storage_key,
    )

    return stored_path.read_bytes()


def delete_stored_file(
    storage_key: str,
) -> None:
    stored_path = resolve_storage_path(
        storage_key,
    )

    stored_path.unlink(
        missing_ok=True,
    )


def delete_upload_file(
    file_path: Path,
) -> None:
    """Legacy cleanup helper for the existing ingestion flow."""
    file_path.unlink(
        missing_ok=True,
    )