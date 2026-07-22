// Domain types shared across the frontend. These mirror the backend Pydantic
// schemas exactly so the API contract is enforced at compile time.

export type VideoStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export type MotionAlgorithm = "mog2" | "frame_diff" | "optical_flow" | "auto";

export interface Video {
  id: number;
  filename: string;
  original_name: string;
  fps: number;
  duration: number;
  width: number;
  height: number;
  frame_count: number;
  size_bytes: number;
  status: VideoStatus;
  progress: number;
  status_message: string;
  motion_algorithm: string | null;
  created_at: string;
  updated_at: string;
  analyzed_at: string | null;
}

export interface ProcessingStats {
  events: number;
  samples: number;
  frames_processed: number;
  frames_with_errors: number;
  object_detection: boolean;
  resolved_motion_algorithm: string;
  motion_detection_seconds: number;
  motion_detection_throughput_fps: number;
  total_pipeline_seconds: number;
  object_detection_cache_hits: number;
  object_detection_cache_misses: number;
}

export interface VideoDetail extends Video {
  heatmap_path: string | null;
  thumbnail_path: string | null;
  error: string | null;
  event_count: number;
  processing_stats: ProcessingStats | null;
}

export interface ROI {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export interface Detection {
  id: number;
  label: string;
  confidence: number;
  timestamp: number;
  prohibited: boolean;
  /** True when `label` is only a heuristic proxy for a prohibited concept
   * the detector has no direct class for (e.g. "book" standing in for
   * "possible notes"), not a direct, reliable detection. */
  heuristic: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Severity = "critical" | "warning" | "normal";

export interface EventRecord {
  id: number;
  video_id: number;
  start_time: number;
  end_time: number;
  duration: number;
  motion_score: number;
  peak_motion_score: number;
  confidence: number;
  objects: string;
  clip_path: string | null;
  thumbnail_path: string | null;
  clip_url: string | null;
  thumbnail_url: string | null;
  rois: ROI[];
  detections: Detection[];
  severity: Severity;
}

export interface TimelinePoint {
  time: number;
  motion_score: number;
  active: boolean;
  objects: string[];
}

export interface EventMarker {
  id: number;
  start: number;
  end: number;
  motion_score: number;
  objects: string[];
  severity: Severity;
}

export interface Timeline {
  video_id: number;
  duration: number;
  fps: number;
  sample_interval: number;
  points: TimelinePoint[];
  event_markers: EventMarker[];
}

export interface HeatmapInfo {
  video_id: number;
  heatmap_url: string | null;
  width: number;
  height: number;
  generated: boolean;
}

export interface ObjectCount {
  label: string;
  count: number;
  prohibited: boolean;
}

export interface Analytics {
  video_id: number;
  total_events: number;
  total_motion_duration: number;
  motion_coverage: number;
  average_motion_score: number;
  peak_motion_score: number;
  peak_activity_time: number;
  longest_event_duration: number;
  longest_event_id: number | null;
  average_event_duration: number;
  total_roi_area_pixels: number;
  top_object: string | null;
  total_detections: number;
  prohibited_detections: number;
  object_counts: ObjectCount[];
  storage_bytes: number;
  compression_ratio: number | null;
}

export interface Clip {
  event_id: number;
  start_time: number;
  end_time: number;
  duration: number;
  motion_score: number;
  objects: string[];
  clip_url: string | null;
  thumbnail_url: string | null;
}

export interface AnalyzeRequest {
  motion_algorithm: MotionAlgorithm;
  enable_object_detection: boolean;
  frame_sample_step?: number | null;
  min_motion_area?: number | null;
  object_detection_confidence?: number | null;
  object_detection_classes?: string[] | null;
}

export interface ResourceUsage {
  cpu_percent: number | null;
  memory_percent: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  gpu_name: string | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
}

export interface SystemInfo {
  version: string;
  ffmpeg: boolean;
  cuda: boolean;
  object_detection: boolean;
  default_motion_algorithm: string;
  free_disk_bytes: number;
  allowed_extensions: string[];
  yolo_model: string;
  yolo_device: string;
  task_backend: string;
  resources: ResourceUsage;
}

export interface GlobalStats {
  total_videos: number;
  completed_videos: number;
  processing_videos: number;
  failed_videos: number;
  total_events: number;
  total_video_duration_seconds: number;
  free_disk_bytes: number;
}

/** Pagination metadata carried in X-Total-Count / X-Limit / X-Offset
 * response headers (additive, non-breaking — the JSON body stays a plain
 * array). See docs/API.md. */
export interface PageInfo {
  total: number;
  limit: number;
  offset: number;
}

export type UserRole = "admin" | "investigator" | "viewer";

export interface SystemCapabilities {
  yolo_model: string;
  yolo_device: string;
  task_backend: string;
  max_upload_mb: number;
  allowed_extensions: string[];
  auth_enabled: boolean;
  demo_mode_enabled: boolean;
}

export interface CurrentUser {
  username: string | null;
  role: UserRole;
  auth_enabled: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  username: string;
  role: UserRole;
}

export interface RuntimeConfig {
  default_motion_algorithm: string;
  motion_threshold: number;
  min_motion_area: number;
  frame_sample_step: number;
  yolo_confidence: number;
  enable_object_detection: boolean;
  updated_at: string;
  updated_by: string | null;
}

export interface RuntimeConfigUpdate {
  default_motion_algorithm?: string;
  motion_threshold?: number;
  min_motion_area?: number;
  frame_sample_step?: number;
  yolo_confidence?: number;
  enable_object_detection?: boolean;
}

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  username: string | null;
  action: string;
  resource: string | null;
  ip_address: string | null;
  detail: string | null;
  success: boolean;
}
