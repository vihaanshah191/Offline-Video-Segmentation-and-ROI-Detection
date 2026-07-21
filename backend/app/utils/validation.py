"""Upload content validation: magic-byte container sniffing.

The upload endpoint previously trusted the client-supplied filename extension
alone to decide whether a file was an acceptable video — a file named
``payload.mp4`` containing arbitrary (e.g. executable) bytes would pass that
check and only get rejected later, indirectly, when OpenCV failed to open it
(and even then, some malformed inputs can produce confusing partial-open
states rather than a clean failure).

This module sniffs the actual container signature from the first bytes of the
file — the same technique browsers and ``file(1)`` use — so uploads are
rejected immediately and precisely if their content doesn't match a real video
container, before any further (more expensive) processing happens.
"""
from __future__ import annotations

from pathlib import Path

# Each supported extension maps to a "family" of container signatures that are
# considered valid for it. MP4 and MOV share the ISO Base Media File Format
# (both use ``ftyp``/``moov``/... top-level atoms), so either is accepted for
# both extensions — QuickTime and MP4 are close relatives and this avoids
# false rejections of legitimately-interchangeable files.
_ISOBMFF_ATOMS = (b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot")
_RIFF_SIGNATURE = b"RIFF"
_AVI_TAG = b"AVI "
_EBML_SIGNATURE = b"\x1a\x45\xdf\xa3"

_EXTENSION_FAMILIES: dict[str, str] = {
    "mp4": "isobmff",
    "mov": "isobmff",
    "avi": "riff-avi",
    "mkv": "ebml",
}

_SNIFF_BYTES = 32


def sniff_container_family(header: bytes) -> str | None:
    """Identify the container family from a file's leading bytes.

    Args:
        header: The first ``_SNIFF_BYTES`` (or more) bytes of the file.

    Returns:
        ``"isobmff"``, ``"riff-avi"``, ``"ebml"``, or ``None`` if unrecognised.
    """
    if len(header) >= 8 and header[4:8] in _ISOBMFF_ATOMS:
        return "isobmff"
    if len(header) >= 12 and header[0:4] == _RIFF_SIGNATURE and header[8:12] == _AVI_TAG:
        return "riff-avi"
    if len(header) >= 4 and header[0:4] == _EBML_SIGNATURE:
        return "ebml"
    return None


def validate_video_signature(path: str | Path, extension: str) -> tuple[bool, str | None]:
    """Check that a file's actual content matches its claimed extension.

    Args:
        path: Path to the (already-written-to-disk) uploaded file.
        extension: The lowercase extension without a leading dot (e.g. ``"mp4"``).

    Returns:
        ``(True, None)`` if the content signature matches; otherwise
        ``(False, <human-readable reason>)``.
    """
    expected_family = _EXTENSION_FAMILIES.get(extension)
    if expected_family is None:
        # Extension itself isn't one we recognise at all — the caller's
        # extension allow-list check should already have rejected this, but
        # fail safe here too rather than assume.
        return False, f"Unrecognised extension '.{extension}'."

    try:
        with open(path, "rb") as fh:
            header = fh.read(_SNIFF_BYTES)
    except OSError as exc:
        return False, f"Could not read file to validate its content: {exc}"

    detected_family = sniff_container_family(header)
    if detected_family is None:
        return False, (
            f"File content does not match a recognised video container "
            f"(expected {expected_family} for '.{extension}'). The file may be "
            f"corrupt, empty, or not actually a video."
        )
    if detected_family != expected_family:
        return False, (
            f"File extension '.{extension}' does not match its actual content "
            f"(detected {detected_family}, expected {expected_family}). "
            f"Rename the file to match its real format, or re-export it."
        )
    return True, None
