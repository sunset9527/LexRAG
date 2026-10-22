"""Bounded file writes and lightweight PDF/DOCX validation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from config import Settings
from config import settings as default_settings
from src.ingestion.rich_document_parser import ParsedDocument

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UploadValidationError(ValueError):
    """Uploaded bytes violate a size, type, or archive-safety boundary."""


@dataclass(frozen=True)
class UploadArtifact:
    path: Path
    original_filename: str
    size_bytes: int
    sha256: str
    media_type: str


def validate_parsed_document_limits(
    document: ParsedDocument,
    *,
    max_pages: int,
    max_characters: int,
) -> None:
    """Reject parsed output before it is persisted or sent to an indexer."""

    if len(document.pages) > max_pages:
        raise UploadValidationError("PDF 页数超过限制")
    extracted_characters = sum(len(page.raw_text) for page in document.pages)
    if extracted_characters > max_characters:
        raise UploadValidationError("文档抽取字符数超过限制")


def sanitize_filename(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "upload")
    basename = normalized.replace("\\", "/").split("/")[-1].strip()
    stem = _UNSAFE_FILENAME.sub("_", Path(basename).stem).strip("._") or "upload"
    suffix = _UNSAFE_FILENAME.sub("", Path(basename).suffix.lower())[:16]
    return f"{stem[:96]}{suffix}"


def build_isolated_upload_path(
    root: str | Path,
    *,
    organization_id: int,
    knowledge_base_slug: str,
    original_filename: str | None,
) -> Path:
    if organization_id <= 0 or not _SLUG.fullmatch(knowledge_base_slug):
        raise UploadValidationError("上传作用域无效")
    filename = sanitize_filename(original_filename)
    suffix = Path(filename).suffix
    directory = (
        Path(root).resolve()
        / f"org-{organization_id}"
        / f"kb-{knowledge_base_slug}"
        / ".incoming"
    )
    directory.mkdir(parents=True, exist_ok=True)
    destination = (directory / f"{uuid.uuid4().hex}{suffix}").resolve()
    if not destination.is_relative_to(Path(root).resolve()):
        raise UploadValidationError("上传路径无效")
    return destination


class SecureUploadWriter:
    """Write chunks under a hard byte ceiling, then validate their real type."""

    def __init__(
        self,
        destination: str | Path,
        *,
        max_bytes: int,
        settings: Settings = default_settings,
    ) -> None:
        if max_bytes <= 0:
            raise UploadValidationError("上传大小限制无效")
        self.destination = Path(destination)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.settings = settings
        self.size_bytes = 0
        self._hash = hashlib.sha256()
        self._head = bytearray()
        self._stream = self.destination.open("xb")
        self._closed = False

    def feed(self, chunk: bytes) -> None:
        if self._closed:
            raise UploadValidationError("上传写入器已关闭")
        if not isinstance(chunk, bytes):
            raise UploadValidationError("上传数据格式无效")
        next_size = self.size_bytes + len(chunk)
        if next_size > self.max_bytes:
            raise UploadValidationError("上传文件超过大小限制")
        if len(self._head) < 16:
            self._head.extend(chunk[: 16 - len(self._head)])
        self._stream.write(chunk)
        self._hash.update(chunk)
        self.size_bytes = next_size

    def finish(self, *, original_filename: str, content_type: str | None) -> UploadArtifact:
        if not self._closed:
            self._stream.flush()
            self._stream.close()
            self._closed = True
        safe_name = sanitize_filename(original_filename)
        suffix = Path(safe_name).suffix.lower()
        declared = (content_type or "").split(";", 1)[0].strip().lower()

        if suffix == ".pdf":
            if declared != _PDF_MIME or not bytes(self._head).startswith(b"%PDF-"):
                raise UploadValidationError("PDF 扩展名、MIME 与文件内容不一致")
            media_type = _PDF_MIME
        elif suffix == ".docx":
            if declared != _DOCX_MIME or not bytes(self._head).startswith(b"PK"):
                raise UploadValidationError("DOCX 扩展名、MIME 与文件内容不一致")
            self._validate_docx()
            media_type = _DOCX_MIME
        else:
            raise UploadValidationError("仅支持 PDF 或 DOCX 文件")

        return UploadArtifact(
            path=self.destination,
            original_filename=safe_name,
            size_bytes=self.size_bytes,
            sha256=self._hash.hexdigest(),
            media_type=media_type,
        )

    def abort(self) -> None:
        if not self._closed:
            self._stream.close()
            self._closed = True
        self.destination.unlink(missing_ok=True)

    def _validate_docx(self) -> None:
        try:
            with zipfile.ZipFile(self.destination) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise UploadValidationError("DOCX 文件结构无效")
                if len(entries) > self.settings.upload_docx_max_entries:
                    raise UploadValidationError("DOCX 解压条目超过限制")
                total = 0
                for entry in entries:
                    total += entry.file_size
                    if entry.file_size > self.settings.upload_docx_max_entry_bytes:
                        raise UploadValidationError("DOCX 单项解压大小超过限制")
                    if entry.compress_size == 0 and entry.file_size > 0:
                        raise UploadValidationError("DOCX 解压比例异常")
                    if entry.compress_size and entry.file_size / entry.compress_size > 1000:
                        raise UploadValidationError("DOCX 解压比例异常")
                if total > self.settings.upload_docx_max_uncompressed_bytes:
                    raise UploadValidationError("DOCX 总解压大小超过限制")
        except zipfile.BadZipFile as exc:
            raise UploadValidationError("DOCX 压缩结构无效") from exc


async def save_upload_file(
    upload,
    destination: str | Path,
    *,
    max_bytes: int,
    settings: Settings = default_settings,
    chunk_bytes: int = 64 * 1024,
) -> UploadArtifact:
    """Consume a Starlette UploadFile incrementally through the secure writer."""

    writer = SecureUploadWriter(destination, max_bytes=max_bytes, settings=settings)
    try:
        while True:
            chunk = await upload.read(chunk_bytes)
            if not chunk:
                break
            writer.feed(chunk)
        return writer.finish(
            original_filename=upload.filename or "upload",
            content_type=upload.content_type,
        )
    except Exception:
        writer.abort()
        raise
