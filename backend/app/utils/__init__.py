"""Utility helpers: geometry, video I/O, filesystem and upload validation."""
from app.utils.files import (
    extension_of,
    sanitize_filename,
    to_relative_url,
    unique_filename,
)
from app.utils.geometry import Box, clamp_box, iou, merge_boxes, union_box
from app.utils.validation import sniff_container_family, validate_video_signature
from app.utils.video_io import (
    VideoMetadata,
    cut_clip,
    extract_thumbnail,
    ffmpeg_available,
    probe_metadata,
)

__all__ = [
    "Box",
    "VideoMetadata",
    "clamp_box",
    "cut_clip",
    "extension_of",
    "extract_thumbnail",
    "ffmpeg_available",
    "iou",
    "merge_boxes",
    "probe_metadata",
    "sanitize_filename",
    "sniff_container_family",
    "to_relative_url",
    "union_box",
    "unique_filename",
    "validate_video_signature",
]
