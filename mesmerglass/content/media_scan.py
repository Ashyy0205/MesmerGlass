"""Media directory scanning helpers with case-insensitive suffix matching."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
)
DEFAULT_VIDEO_EXTENSIONS: tuple[str, ...] = (
    ".mp4",
    ".webm",
    ".mkv",
    ".avi",
)
DEFAULT_FONT_EXTENSIONS: tuple[str, ...] = (
    ".ttf",
    ".otf",
    ".ttc",
)


def _normalize_extensions(exts: Iterable[str]) -> set[str]:
    """Normalize extension strings to the canonical lowercase '.ext' form."""
    normalized: set[str] = set()
    for ext in exts:
        if not ext:
            continue
        ext = ext.lower()
        if not ext.startswith('.'):  # guard against bare "jpg"
            ext = f".{ext}"
        normalized.add(ext)
    return normalized


def scan_media_directory(
    root: Path | str,
    *,
    image_exts: Sequence[str] | None = None,
    video_exts: Sequence[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return lists of image and video files under *root*.

    The search is case-insensitive and walks the directory tree once, avoiding
    multiple rglob() passes. Paths are returned as absolute strings so callers
    can store them safely regardless of the current working directory.
    """
    root_path = Path(root)
    if not root_path.exists():  # Nothing to scan
        return [], []

    image_suffixes = _normalize_extensions(image_exts or DEFAULT_IMAGE_EXTENSIONS)
    video_suffixes = _normalize_extensions(video_exts or DEFAULT_VIDEO_EXTENSIONS)

    images: list[str] = []
    videos: list[str] = []

    for path in root_path.rglob('*'):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in image_suffixes:
            images.append(str(path.resolve(strict=False)))
        elif suffix in video_suffixes:
            videos.append(str(path.resolve(strict=False)))

    return images, videos


def scan_font_directory(
    root: Path | str,
    *,
    font_exts: Sequence[str] | None = None,
) -> list[str]:
    """Return list of font files under *root*.

    Args:
        root: Directory to scan recursively
        font_exts: Optional iterable of extensions to match

    Returns:
        List of absolute font file paths
    """
    root_path = Path(root)
    if not root_path.exists():
        return []

    font_suffixes = _normalize_extensions(font_exts or DEFAULT_FONT_EXTENSIONS)
    fonts: list[str] = []

    for path in root_path.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() in font_suffixes:
            fonts.append(str(path.resolve(strict=False)))

    return fonts
