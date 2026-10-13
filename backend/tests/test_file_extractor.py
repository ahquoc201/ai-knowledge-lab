from io import BytesIO

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter
from pypdf.generic import (
    DictionaryObject,
    NameObject,
    StreamObject,
)

from app.services.file_extractor import (
    FileExtractionError,
    UnsupportedFileTypeError,
    extract_text,
)


def test_extract_text_from_utf8_txt():
    text = extract_text(
        filename="knowledge.txt",
        data="PostgreSQL hỗ trợ transaction.".encode(),
    )

    assert text == "PostgreSQL hỗ trợ transaction."


def test_extract_text_rejects_empty_file():
    with pytest.raises(
        FileExtractionError,
        match="Extracted text is empty",
    ):
        extract_text(
            filename="empty.txt",
            data=b"   \n\t",
        )


def test_extract_text_rejects_invalid_utf8():
    with pytest.raises(
        FileExtractionError,
        match="Text file must be UTF-8 encoded",
    ):
        extract_text(
            filename="invalid.txt",
            data=b"\xff\xfe\xfa",
        )


def test_extract_text_rejects_unsupported_file_type():
    with pytest.raises(
        UnsupportedFileTypeError,
        match="Unsupported file type",
    ):
        extract_text(
            filename="document.rtf",
            data=b"fake rtf content",
        )

def build_pdf_with_text(text: str) -> bytes:
    output = BytesIO()
    writer = PdfWriter()

    page = writer.add_blank_page(
        width=612,
        height=792,
    )

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)

    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): font_reference,
                }
            )
        }
    )

    content = StreamObject()
    content.set_data(
        (
            "BT "
            "/F1 12 Tf "
            "72 720 Td "
            f"({text}) Tj "
            "ET"
        ).encode("ascii")
    )

    page[NameObject("/Contents")] = writer._add_object(content)

    writer.write(output)

    return output.getvalue()


def test_extract_text_from_pdf():
    data = build_pdf_with_text(
        "PostgreSQL supports transactions"
    )

    text = extract_text(
        filename="knowledge.pdf",
        data=data,
    )

    assert "PostgreSQL supports transactions" in text


def test_extract_text_rejects_invalid_pdf():
    with pytest.raises(
        FileExtractionError,
        match="Unable to read PDF file",
    ):
        extract_text(
            filename="broken.pdf",
            data=b"%PDF broken",
        )

def build_docx_with_text(text: str) -> bytes:
    output = BytesIO()
    document = DocxDocument()
    document.add_paragraph(text)
    document.save(output)

    return output.getvalue()


def test_extract_text_from_docx():
    data = build_docx_with_text(
        "Odoo uses PostgreSQL as its database"
    )

    text = extract_text(
        filename="knowledge.docx",
        data=data,
    )

    assert "Odoo uses PostgreSQL as its database" in text


def test_extract_text_rejects_invalid_docx():
    with pytest.raises(
        FileExtractionError,
        match="Unable to read DOCX file",
    ):
        extract_text(
            filename="broken.docx",
            data=b"not a valid docx",
        )


def test_extract_text_from_markdown():
    md_content = "# Knowledge Base\n\n- Point 1: Fast retrieval\n- Point 2: Accurate citation"
    text = extract_text(
        filename="notes.md",
        data=md_content.encode("utf-8"),
    )
    assert "# Knowledge Base" in text
    assert "Accurate citation" in text


def test_extract_text_rejects_markdown_invalid_utf8():
    with pytest.raises(
        FileExtractionError,
        match="Markdown file must be UTF-8 encoded",
    ):
        extract_text(
            filename="notes.md",
            data=b"\xff\xfe\xfd invalid",
        )


def build_blank_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def test_extract_text_rejects_empty_scanned_pdf():
    data = build_blank_pdf()
    with pytest.raises(
        FileExtractionError,
        match="PDF file contains no extractable text",
    ):
        extract_text(
            filename="scanned_doc.pdf",
            data=data,
        )


def test_extract_text_rejects_encrypted_pdf():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("user_password")
    writer.write(output)
    data = output.getvalue()

    with pytest.raises(
        FileExtractionError,
        match="Encrypted PDF files are not supported",
    ):
        extract_text(
            filename="secret.pdf",
            data=data,
        )