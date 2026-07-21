// Domain types shared across the frontend. These mirror the backend Pydantic
// schemas exactly so the API contract is enforced at compile time.

export type VideoStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "completed"
  | "failed";

export type MotionAlgorithm = "mog2" | "frame_diff" | "optical_flow";

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

export interface VideoDetail extends Video {
  heatmap_path: string | null;
  thumbnail_path: string | null;
  error: string | null;
  event_count: number;
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
  x: number;
  y: number;
  w: number;
  h: number;
}

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
  rois: ROI[];
  detections: Detection[];
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
  total_detections: number;
  prohibited_detections: number;
  object_counts: ObjectCount[];
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
}

export interface SystemInfo {
  version: string;
  ffmpeg: boolean;
  cuda: boolean;
  object_detection: boolean;
  default_motion_algorithm: string;
  free_disk_bytes: number;
  allowed_extensions: string[];
}
