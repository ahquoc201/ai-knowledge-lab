from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedFileTypeError(ValueError):
    pass


class FileExtractionError(ValueError):
    pass


SUPPORTED_FILE_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".docx",
}


def validate_supported_file_type(filename: str) -> None:
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_FILE_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {extension or 'unknown'}"
        )


def _extract_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileExtractionError(
            "Text file must be UTF-8 encoded"
        ) from exc


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise FileExtractionError(
            "Unable to read PDF file"
        ) from exc

    if reader.is_encrypted:
        raise FileExtractionError(
            "Encrypted PDF files are not supported"
        )

    pages: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            pages.append(page_text.strip())

    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    try:
        document = DocxDocument(BytesIO(data))
    except (PackageNotFoundError, BadZipFile, ValueError) as exc:
        raise FileExtractionError(
            "Unable to read DOCX file"
        ) from exc

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n\n".join(paragraphs)


def extract_text(
    *,
    filename: str,
    data: bytes,
) -> str:
    validate_supported_file_type(filename)

    extension = Path(filename).suffix.lower()

    if extension == ".txt":
        text = _extract_txt(data)
    elif extension == ".pdf":
        text = _extract_pdf(data)
    else:
        text = _extract_docx(data)

    text = text.strip()

    if not text:
        raise FileExtractionError(
            "Extracted text is empty"
        )

    return text