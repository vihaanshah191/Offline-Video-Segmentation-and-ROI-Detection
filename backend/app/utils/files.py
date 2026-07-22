"""Filesystem helpers for safe storage of uploads and artefacts."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe version of ``name``."""
    name = Path(name).name  # strip any path components
    cleaned = _SAFE_RE.sub("_", name).strip("._") or "file"
    return cleaned[:200]


def unique_filename(original: str) -> str:
    """Return a collision-resistant filename preserving the extension."""
    safe = sanitize_filename(original)
    stem = Path(safe).stem
    ext = Path(safe).suffix.lower()
    return f"{stem}_{uuid.uuid4().hex[:12]}{ext}"


def extension_of(name: str) -> str:
    """Return the lowercase extension (without dot) of a filename."""
    return Path(name).suffix.lower().lstrip(".")


def to_relative_url(path: str | Path | None, storage_root: Path, mount: str = "/storage") -> str | None:
    """Convert an absolute storage path to a served URL path.

    Returns ``None`` if ``path`` is falsy (including ``None`` — every
    caller passes an optional DB column straight through, so accepting
    ``None`` here is the actual contract, not just a defensive check).
    """
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.relative_to(storage_root)
    except ValueError:
        rel = Path(p.name)
    return f"{mount}/{rel.as_posix()}"
