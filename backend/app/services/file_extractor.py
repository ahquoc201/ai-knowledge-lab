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
    ".md",
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


def _extract_md(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileExtractionError(
            "Markdown file must be UTF-8 encoded"
        ) from exc


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, Exception) as exc:
        raise FileExtractionError(
            "Unable to read PDF file"
        ) from exc

    if reader.is_encrypted:
        raise FileExtractionError(
            "Encrypted PDF files are not supported"
        )

    pages: list[str] = []

    for page in reader.pages:
        try:
            page_text = page.extract_text()
        except Exception as exc:
            raise FileExtractionError(
                "Unable to extract text from PDF page"
            ) from exc

        if page_text and page_text.strip():
            pages.append(page_text.strip())

    text = "\n\n".join(pages).strip()
    if not text:
        raise FileExtractionError(
            "PDF file contains no extractable text"
        )

    return text


def _extract_docx(data: bytes) -> str:
    try:
        document = DocxDocument(BytesIO(data))
    except (PackageNotFoundError, BadZipFile, ValueError, Exception) as exc:
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
    elif extension == ".md":
        text = _extract_md(data)
    elif extension == ".pdf":
        text = _extract_pdf(data)
    elif extension == ".docx":
        text = _extract_docx(data)
    else:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {extension or 'unknown'}"
        )

    text = text.strip()

    if not text:
        raise FileExtractionError(
            "Extracted text is empty"
        )

    return text