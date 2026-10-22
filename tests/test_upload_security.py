"""Bounded and organization-isolated upload contracts."""

import io
import zipfile

import pytest

from config import Settings


def _pdf_bytes() -> bytes:
    return b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"


def _docx_bytes(*, oversized_entry: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "x" * (5000 if oversized_entry else 20))
    return buffer.getvalue()


def test_filename_and_storage_path_cannot_escape_organization(tmp_path):
    from app.security.uploads import build_isolated_upload_path, sanitize_filename

    assert sanitize_filename("../..\\private contract.pdf") == "private_contract.pdf"
    destination = build_isolated_upload_path(
        tmp_path,
        organization_id=7,
        knowledge_base_slug="contracts",
        original_filename="../private contract.pdf",
    )

    assert destination.is_relative_to(tmp_path.resolve())
    assert destination.parent == (tmp_path / "org-7" / "kb-contracts" / ".incoming").resolve()
    assert destination.suffix == ".pdf"


def test_writer_rejects_oversize_during_feed_and_removes_partial_file(tmp_path):
    from app.security.uploads import SecureUploadWriter, UploadValidationError

    destination = tmp_path / "upload.pdf"
    writer = SecureUploadWriter(destination, max_bytes=8)
    writer.feed(b"%PDF-")

    with pytest.raises(UploadValidationError, match="大小"):
        writer.feed(b"1234")

    writer.abort()
    assert not destination.exists()


@pytest.mark.parametrize(
    ("filename", "content_type", "payload"),
    [
        ("fake.pdf", "application/pdf", b"not-a-pdf"),
        (
            "fake.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _pdf_bytes(),
        ),
        ("real.pdf", "text/plain", _pdf_bytes()),
    ],
)
def test_extension_mime_and_magic_must_agree(tmp_path, filename, content_type, payload):
    from app.security.uploads import SecureUploadWriter, UploadValidationError

    writer = SecureUploadWriter(tmp_path / filename, max_bytes=1024 * 1024)
    writer.feed(payload)

    with pytest.raises(UploadValidationError):
        writer.finish(original_filename=filename, content_type=content_type)
    writer.abort()


def test_docx_archive_limits_block_zip_bombs(tmp_path):
    from app.security.uploads import SecureUploadWriter, UploadValidationError

    settings = Settings(_env_file=None, upload_docx_max_entry_bytes=100)
    destination = tmp_path / "bomb.docx"
    writer = SecureUploadWriter(destination, max_bytes=1024 * 1024, settings=settings)
    writer.feed(_docx_bytes(oversized_entry=True))

    with pytest.raises(UploadValidationError, match="解压"):
        writer.finish(
            original_filename="bomb.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    writer.abort()


def test_valid_pdf_and_docx_are_accepted(tmp_path):
    from app.security.uploads import SecureUploadWriter

    samples = [
        ("law.pdf", "application/pdf", _pdf_bytes()),
        (
            "contract.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx_bytes(),
        ),
    ]
    for filename, content_type, payload in samples:
        writer = SecureUploadWriter(tmp_path / filename, max_bytes=1024 * 1024)
        writer.feed(payload)
        artifact = writer.finish(original_filename=filename, content_type=content_type)
        assert artifact.path.exists()
        assert artifact.size_bytes == len(payload)


def test_parsed_document_limits_reject_excess_pages_and_characters():
    from app.security.uploads import UploadValidationError, validate_parsed_document_limits
    from src.ingestion.rich_document_parser import ParsedDocument, ParsedPage

    pages = [
        ParsedPage(
            page_number=number,
            raw_text="x" * 8,
            search_text="x" * 8,
            source="text",
        )
        for number in range(1, 4)
    ]
    document = ParsedDocument(pages=pages)

    with pytest.raises(UploadValidationError, match="页数"):
        validate_parsed_document_limits(document, max_pages=2, max_characters=100)
    with pytest.raises(UploadValidationError, match="字符"):
        validate_parsed_document_limits(document, max_pages=5, max_characters=20)
