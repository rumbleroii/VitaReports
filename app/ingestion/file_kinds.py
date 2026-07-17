"""File-type routing helpers for extract uploads."""

from __future__ import annotations

from pathlib import Path

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

PDF_CONTENT_TYPES = {"application/pdf"}
IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/tiff",
    "image/tif",
}


def detect_file_kind(filename: str | None, content_type: str | None) -> str:
    """Return 'pdf', 'image', or 'unsupported'."""
    ext = Path(filename or "").suffix.lower()
    ctype = (content_type or "").split(";")[0].strip().lower()

    if ext in PDF_EXTENSIONS or ctype in PDF_CONTENT_TYPES:
        return "pdf"
    if ext in IMAGE_EXTENSIONS or ctype in IMAGE_CONTENT_TYPES:
        return "image"
    return "unsupported"
