from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings


def save_upload_file(
    *,
    filename: str,
    data: bytes,
) -> Path:
    settings = get_settings()
    storage_dir = settings.upload_storage_dir

    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    extension = Path(filename).suffix.lower()
    stored_path = storage_dir / f"{uuid4()}{extension}"

    stored_path.write_bytes(data)

    return stored_path


def delete_upload_file(file_path: Path) -> None:
    file_path.unlink(missing_ok=True)