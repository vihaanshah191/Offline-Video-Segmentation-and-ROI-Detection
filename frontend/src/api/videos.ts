import { apiClient, API_BASE } from "./client";
import type {
  Analytics,
  AnalyzeRequest,
  Clip,
  EventRecord,
  GlobalStats,
  HeatmapInfo,
  PageInfo,
  SystemInfo,
  Timeline,
  Video,
  VideoDetail,
} from "@/types";

/** Query parameters accepted by the event-log endpoint. */
export interface EventQuery {
  search?: string;
  prohibited_only?: boolean;
  min_score?: number;
  sort_by?: "start_time" | "duration" | "motion_score" | "confidence";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface VideoListQuery {
  limit?: number;
  offset?: number;
}

/** A paginated result: items plus metadata parsed from the response headers. */
export interface Page<T> {
  items: T[];
  pageInfo: PageInfo;
}

function extractPageInfo(headers: Record<string, unknown>, fallbackLimit: number): PageInfo {
  const total = Number(headers["x-total-count"] ?? 0);
  const limit = Number(headers["x-limit"] ?? fallbackLimit);
  const offset = Number(headers["x-offset"] ?? 0);
  return { total, limit, offset };
}

export const videosApi = {
  async list(query: VideoListQuery = {}): Promise<Page<Video>> {
    const limit = query.limit ?? 100;
    const { data, headers } = await apiClient.get<Video[]>("/videos", {
      params: { limit, offset: query.offset ?? 0 },
    });
    return { items: data, pageInfo: extractPageInfo(headers, limit) };
  },

  async get(id: number): Promise<VideoDetail> {
    const { data } = await apiClient.get<VideoDetail>(`/video/${id}`);
    return data;
  },

  async upload(file: File, onProgress?: (pct: number) => void): Promise<VideoDetail> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await apiClient.post<VideoDetail>("/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return data;
  },

  async analyze(id: number, req: AnalyzeRequest): Promise<VideoDetail> {
    const { data } = await apiClient.post<VideoDetail>(`/analyze/${id}`, req);
    return data;
  },

  async remove(id: number): Promise<void> {
    await apiClient.delete(`/video/${id}`);
  },

  async cancel(id: number): Promise<void> {
    await apiClient.post(`/video/${id}/cancel`);
  },

  async events(id: number, query: EventQuery = {}): Promise<Page<EventRecord>> {
    const limit = query.limit ?? 200;
    const { data, headers } = await apiClient.get<EventRecord[]>(`/events/${id}`, {
      params: { ...query, limit },
    });
    return { items: data, pageInfo: extractPageInfo(headers, limit) };
  },

  async clips(id: number): Promise<Clip[]> {
    const { data } = await apiClient.get<Clip[]>(`/clips/${id}`);
    return data;
  },

  async timeline(id: number): Promise<Timeline> {
    const { data } = await apiClient.get<Timeline>(`/timeline/${id}`);
    return data;
  },

  async analytics(id: number): Promise<Analytics> {
    const { data } = await apiClient.get<Analytics>(`/analytics/${id}`);
    return data;
  },

  async heatmap(id: number): Promise<HeatmapInfo> {
    const { data } = await apiClient.get<HeatmapInfo>(`/heatmap/${id}`);
    return data;
  },

  async system(): Promise<SystemInfo> {
    const { data } = await apiClient.get<SystemInfo>("/system");
    return data;
  },

  async globalStats(): Promise<GlobalStats> {
    const { data } = await apiClient.get<GlobalStats>("/stats");
    return data;
  },

  async queue(): Promise<Video[]> {
    const { data } = await apiClient.get<Video[]>("/queue");
    return data;
  },

  async loadDemoSample(): Promise<VideoDetail> {
    const { data } = await apiClient.post<VideoDetail>("/demo/load-sample");
    return data;
  },

  // Absolute URLs for download/streaming (used in <a href> / <video src>).
  clipDownloadUrl: (videoId: number, eventId: number) =>
    `${API_BASE}/clips/${videoId}/${eventId}/download`,
  heatmapDownloadUrl: (videoId: number) => `${API_BASE}/heatmap/${videoId}/download`,
  csvUrl: (videoId: number) => `${API_BASE}/report/${videoId}/csv`,
  pdfUrl: (videoId: number) => `${API_BASE}/report/${videoId}/pdf`,
};
