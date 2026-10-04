from types import SimpleNamespace

from app.services.file_storage import (
    delete_upload_file,
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