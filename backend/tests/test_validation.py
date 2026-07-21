"""Tests for upload content validation and filename sanitisation (security)."""
from __future__ import annotations

from pathlib import Path

from app.utils.files import sanitize_filename, unique_filename
from app.utils.validation import sniff_container_family, validate_video_signature


# --------------------------------------------------------------------- sniff
def test_sniff_isobmff_ftyp() -> None:
    header = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
    assert sniff_container_family(header) == "isobmff"


def test_sniff_isobmff_moov_atom() -> None:
    header = b"\x00\x00\x00\x08moov" + b"\x00" * 16
    assert sniff_container_family(header) == "isobmff"


def test_sniff_riff_avi() -> None:
    header = b"RIFF\x00\x00\x00\x00AVI LIST"
    assert sniff_container_family(header) == "riff-avi"


def test_sniff_riff_but_not_avi_is_unrecognised() -> None:
    # RIFF is also used by WAV, WEBP, etc. — only "AVI " at offset 8 counts.
    header = b"RIFF\x00\x00\x00\x00WAVEfmt "
    assert sniff_container_family(header) is None


def test_sniff_ebml_mkv() -> None:
    header = b"\x1a\x45\xdf\xa3" + b"\x00" * 16
    assert sniff_container_family(header) == "ebml"


def test_sniff_plain_text_is_unrecognised() -> None:
    assert sniff_container_family(b"This is not a video, just text data.") is None


def test_sniff_short_header_is_unrecognised() -> None:
    assert sniff_container_family(b"\x00\x00") is None


# --------------------------------------------------------- validate_signature
def test_validate_video_signature_matching(tmp_path: Path) -> None:
    path = tmp_path / "real.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
    ok, reason = validate_video_signature(path, "mp4")
    assert ok is True
    assert reason is None


def test_validate_video_signature_mov_accepts_isobmff(tmp_path: Path) -> None:
    """MOV and MP4 share the ISO-BMFF family — a valid ftyp atom should pass
    validation for a .mov extension too."""
    path = tmp_path / "real.mov"
    path.write_bytes(b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 100)
    ok, reason = validate_video_signature(path, "mov")
    assert ok is True


def test_validate_video_signature_mismatched_family(tmp_path: Path) -> None:
    """An AVI file renamed to .mp4 must be rejected with a clear reason."""
    path = tmp_path / "renamed.mp4"
    path.write_bytes(b"RIFF\x00\x00\x00\x00AVI LIST" + b"\x00" * 100)
    ok, reason = validate_video_signature(path, "mp4")
    assert ok is False
    assert "does not match" in reason


def test_validate_video_signature_non_video_content(tmp_path: Path) -> None:
    path = tmp_path / "fake.mp4"
    path.write_bytes(b"Not a video at all, just some plain bytes for testing.")
    ok, reason = validate_video_signature(path, "mp4")
    assert ok is False
    assert reason is not None


def test_validate_video_signature_unrecognised_extension(tmp_path: Path) -> None:
    path = tmp_path / "file.xyz"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    ok, reason = validate_video_signature(path, "xyz")
    assert ok is False


# ------------------------------------------------------- filename sanitising
def test_sanitize_filename_strips_directory_components() -> None:
    assert sanitize_filename("../../etc/passwd.mp4") == "passwd.mp4"


def test_sanitize_filename_strips_absolute_path() -> None:
    assert sanitize_filename("/etc/passwd.mp4") == "passwd.mp4"


def test_sanitize_filename_handles_windows_style_traversal() -> None:
    # Backslashes are not path separators on POSIX, so Path().name alone
    # would not strip them — the character allow-list regex must.
    result = sanitize_filename("..\\..\\evil.mp4")
    assert "\\" not in result
    assert ".." not in result
    assert result.endswith("evil.mp4")


def test_sanitize_filename_replaces_illegal_characters() -> None:
    result = sanitize_filename("my video!@#$.mp4")
    assert result.replace("_", "").isalnum() or "." in result
    assert " " not in result
    assert "!" not in result


def test_sanitize_filename_empty_after_cleaning_gets_fallback() -> None:
    assert sanitize_filename("....") == "file"


def test_sanitize_filename_null_byte_removed() -> None:
    result = sanitize_filename("evil\x00.mp4")
    assert "\x00" not in result


def test_unique_filename_preserves_extension_and_is_collision_resistant() -> None:
    a = unique_filename("video.mp4")
    b = unique_filename("video.mp4")
    assert a != b
    assert a.endswith(".mp4")
    assert b.endswith(".mp4")


def test_unique_filename_sanitises_traversal_attempt() -> None:
    result = unique_filename("../../../etc/passwd.mp4")
    assert ".." not in result
    assert "/" not in result
