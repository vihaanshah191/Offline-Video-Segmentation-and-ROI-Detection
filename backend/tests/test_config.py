"""Tests for Settings validation: a misconfigured environment should fail
fast at startup with a clear error, not cause silent, hard-to-diagnose
behaviour deep inside the CV pipeline at analysis time."""
from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def _settings(**overrides) -> Settings:
    # Bypass the .env file / real environment entirely for these tests.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_default_settings_are_valid() -> None:
    settings = _settings()
    assert settings.default_motion_algorithm == "mog2"


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("motion_threshold", -0.1),
        ("motion_threshold", 1.5),
        ("yolo_confidence", 1.1),
        ("yolo_iou", -0.1),
        ("roi_merge_iou", 2.0),
        ("motion_hysteresis_ratio", -1.0),
        ("roi_min_area_fraction", 1.5),
    ],
)
def test_out_of_range_fraction_fields_rejected(field: str, bad_value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: bad_value})


def test_frame_sample_step_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(frame_sample_step=0)


def test_frame_sample_step_upper_bound_enforced() -> None:
    with pytest.raises(ValidationError):
        _settings(frame_sample_step=1000)


def test_max_upload_mb_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(max_upload_mb=0)


def test_unknown_motion_algorithm_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(default_motion_algorithm="not_a_real_algorithm")


def test_auto_is_a_valid_default_motion_algorithm() -> None:
    settings = _settings(default_motion_algorithm="auto")
    assert settings.default_motion_algorithm == "auto"


def test_unknown_task_backend_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(task_backend="not_a_real_backend")


def test_unknown_log_format_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(log_format="xml")


def test_cors_wildcard_mixed_with_explicit_origins_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(cors_origins="*,http://localhost:5173")


def test_cors_wildcard_alone_is_allowed() -> None:
    settings = _settings(cors_origins="*")
    assert settings.cors_origin_list == ["*"]


def test_cors_explicit_list_parsed() -> None:
    settings = _settings(cors_origins="http://a.com, http://b.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


def test_max_upload_bytes_derived_correctly() -> None:
    settings = _settings(max_upload_mb=10)
    assert settings.max_upload_bytes == 10 * 1024 * 1024


def test_allowed_extension_set_normalises_case_and_dots() -> None:
    settings = _settings(allowed_extensions=".MP4, Avi, .mkv")
    assert settings.allowed_extension_set == {"mp4", "avi", "mkv"}


def test_rate_limit_fields_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(upload_rate_limit_per_minute=0)


def test_ensure_directories_resolves_database_url_outside_storage(tmp_path) -> None:
    # database_url must be explicitly cleared here: conftest.py sets
    # DATABASE_URL process-wide for the whole test session (for test
    # isolation), and Settings(_env_file=None) only disables the .env FILE,
    # not real environment variables — so without this override we'd just
    # observe the test-session DB path rather than the "unset" resolution
    # behaviour this test exists to check.
    settings = _settings(
        database_url="",
        storage_dir=tmp_path / "storage",
        videos_dir=tmp_path / "storage" / "videos",
        clips_dir=tmp_path / "storage" / "clips",
        heatmaps_dir=tmp_path / "storage" / "heatmaps",
        thumbnails_dir=tmp_path / "storage" / "thumbnails",
        reports_dir=tmp_path / "storage" / "reports",
        data_dir=tmp_path / "data",
    )
    settings.ensure_directories()
    assert str(settings.data_dir) in settings.database_url
    # The critical security property: the resolved DB path must NOT live
    # under storage_dir (which is served publicly) or any of its subdirs.
    assert str(settings.storage_dir) not in settings.database_url
