import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { videosApi, type EventQuery, type Page, type VideoListQuery } from "@/api/videos";
import type {
  Analytics,
  AnalyzeRequest,
  Clip,
  EventRecord,
  GlobalStats,
  HeatmapInfo,
  SystemInfo,
  Timeline,
  Video,
  VideoDetail,
} from "@/types";

export const queryKeys = {
  videos: (q: VideoListQuery = {}) => ["videos", q] as const,
  video: (id: number) => ["video", id] as const,
  events: (id: number, q: EventQuery) => ["events", id, q] as const,
  clips: (id: number) => ["clips", id] as const,
  timeline: (id: number) => ["timeline", id] as const,
  analytics: (id: number) => ["analytics", id] as const,
  heatmap: (id: number) => ["heatmap", id] as const,
  system: ["system"] as const,
  globalStats: ["globalStats"] as const,
};

const ACTIVE = new Set(["queued", "processing"]);

export function useVideos(query: VideoListQuery = {}): UseQueryResult<Page<Video>> {
  return useQuery({
    queryKey: queryKeys.videos(query),
    queryFn: () => videosApi.list(query),
    // Refetch while any video on the current page is still processing.
    refetchInterval: (q) =>
      (q.state.data?.items ?? []).some((v) => ACTIVE.has(v.status)) ? 2000 : false,
  });
}

export function useVideo(id: number): UseQueryResult<VideoDetail> {
  return useQuery({
    queryKey: queryKeys.video(id),
    queryFn: () => videosApi.get(id),
    refetchInterval: (query) => (query.state.data && ACTIVE.has(query.state.data.status) ? 1500 : false),
  });
}

export function useSystemInfo(): UseQueryResult<SystemInfo> {
  return useQuery({ queryKey: queryKeys.system, queryFn: videosApi.system, staleTime: 60_000 });
}

export function useGlobalStats(): UseQueryResult<GlobalStats> {
  return useQuery({
    queryKey: queryKeys.globalStats,
    queryFn: videosApi.globalStats,
    refetchInterval: 5000,
  });
}

export function useEvents(
  id: number,
  query: EventQuery,
  enabled = true,
): UseQueryResult<Page<EventRecord>> {
  return useQuery({
    queryKey: queryKeys.events(id, query),
    queryFn: () => videosApi.events(id, query),
    enabled,
  });
}

export function useClips(id: number, enabled = true): UseQueryResult<Clip[]> {
  return useQuery({ queryKey: queryKeys.clips(id), queryFn: () => videosApi.clips(id), enabled });
}

export function useTimeline(id: number, enabled = true): UseQueryResult<Timeline> {
  return useQuery({ queryKey: queryKeys.timeline(id), queryFn: () => videosApi.timeline(id), enabled });
}

export function useAnalytics(id: number, enabled = true): UseQueryResult<Analytics> {
  return useQuery({ queryKey: queryKeys.analytics(id), queryFn: () => videosApi.analytics(id), enabled });
}

export function useHeatmap(id: number, enabled = true): UseQueryResult<HeatmapInfo> {
  return useQuery({ queryKey: queryKeys.heatmap(id), queryFn: () => videosApi.heatmap(id), enabled });
}

export function useUploadVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress?: (p: number) => void }) =>
      videosApi.upload(file, onProgress),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: queryKeys.globalStats });
    },
  });
}

export function useAnalyzeVideo(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: AnalyzeRequest) => videosApi.analyze(id, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.video(id) });
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: queryKeys.globalStats });
    },
  });
}

export function useCancelVideo(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => videosApi.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.video(id) });
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: queryKeys.globalStats });
    },
  });
}

export function useDeleteVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => videosApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: queryKeys.globalStats });
    },
  });
}
