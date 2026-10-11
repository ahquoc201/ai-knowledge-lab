from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.file_storage import (
    InvalidStorageKeyError,
    delete_stored_file,
    delete_upload_file,
    read_stored_file,
    resolve_storage_path,
    save_upload_file,
)


def test_save_upload_file_uses_uuid_name_and_preserves_extension(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    stored_path = save_upload_file(
        filename="../../Knowledge.PDF",
        data=b"pdf bytes",
    )

    assert stored_path.parent == tmp_path
    assert stored_path.suffix == ".pdf"
    assert stored_path.name != "Knowledge.PDF"
    assert stored_path.read_bytes() == b"pdf bytes"


def test_delete_upload_file_removes_file(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=b"knowledge",
    )

    assert stored_path.exists()

    delete_upload_file(stored_path)

    assert not stored_path.exists()


def test_delete_upload_file_ignores_missing_file(
    tmp_path,
):
    missing_path = tmp_path / "missing.txt"

    delete_upload_file(missing_path)

    assert not missing_path.exists()

def test_persistent_file_can_be_read_and_deleted(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    content = b"Persistent PostgreSQL knowledge"

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=content,
    )

    storage_key = stored_path.name

    assert resolve_storage_path(storage_key) == stored_path
    assert read_stored_file(storage_key) == content

    delete_stored_file(storage_key)

    assert not stored_path.exists()


@pytest.mark.parametrize(
    "storage_key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "knowledge.txt",
        "../knowledge.txt",
        "invalid-key",
        "",
    ],
)
def test_persistent_storage_rejects_invalid_keys(
    monkeypatch,
    tmp_path,
    storage_key,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    with pytest.raises(InvalidStorageKeyError):
        resolve_storage_path(storage_key)

    with pytest.raises(InvalidStorageKeyError):
        delete_stored_file(storage_key)


def test_persistent_storage_rejects_symlinks(
    monkeypatch,
    tmp_path,
):
    storage_dir = tmp_path / "uploads"

    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=storage_dir,
        ),
    )

    outside_file = tmp_path / "private.txt"
    outside_file.write_bytes(b"Private data")

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=b"Knowledge",
    )

    storage_key = stored_path.name

    stored_path.unlink()
    stored_path.symlink_to(outside_file)

    with pytest.raises(InvalidStorageKeyError):
        read_stored_file(storage_key)

    with pytest.raises(InvalidStorageKeyError):
        delete_stored_file(storage_key)

    assert outside_file.read_bytes() == b"Private data"


def test_delete_stored_file_ignores_missing_file(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    storage_key = f"{uuid4()}.txt"

    delete_stored_file(storage_key)

    assert not resolve_storage_path(storage_key).exists()