import { apiClient, API_BASE } from "./client";
import type {
  Analytics,
  AnalyzeRequest,
  Clip,
  EventRecord,
  HeatmapInfo,
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
}

export const videosApi = {
  async list(): Promise<Video[]> {
    const { data } = await apiClient.get<Video[]>("/videos");
    return data;
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

  async events(id: number, query: EventQuery = {}): Promise<EventRecord[]> {
    const { data } = await apiClient.get<EventRecord[]>(`/events/${id}`, { params: query });
    return data;
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

  // Absolute URLs for download/streaming (used in <a href> / <video src>).
  clipDownloadUrl: (videoId: number, eventId: number) =>
    `${API_BASE}/clips/${videoId}/${eventId}/download`,
  heatmapDownloadUrl: (videoId: number) => `${API_BASE}/heatmap/${videoId}/download`,
  csvUrl: (videoId: number) => `${API_BASE}/report/${videoId}/csv`,
  pdfUrl: (videoId: number) => `${API_BASE}/report/${videoId}/pdf`,
};
