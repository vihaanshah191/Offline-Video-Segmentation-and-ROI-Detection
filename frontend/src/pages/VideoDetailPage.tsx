import { useCallback, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, FileText, Loader2 } from "lucide-react";

import { resolveStorageUrl } from "@/api/client";
import { videosApi } from "@/api/videos";
import { AnalyticsPanel } from "@/components/AnalyticsPanel";
import { AnalyzeDialog } from "@/components/AnalyzeDialog";
import { ClipGallery } from "@/components/ClipGallery";
import { EventTable } from "@/components/EventTable";
import { HeatmapView } from "@/components/HeatmapView";
import { MotionTimeline } from "@/components/MotionTimeline";
import { ProcessingStatsPanel } from "@/components/ProcessingStatsPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { VideoPlayer } from "@/components/VideoPlayer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAnalytics, useEvents, useTimeline, useVideo } from "@/hooks/useVideos";
import { formatDuration } from "@/lib/utils";

export function VideoDetailPage() {
  const params = useParams();
  const videoId = Number(params.id);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const { data: video, isLoading } = useVideo(videoId);
  const completed = video?.status === "completed";
  const { data: eventsPage } = useEvents(videoId, { limit: 1000 }, completed);
  const events = eventsPage?.items ?? [];
  const { data: timeline } = useTimeline(videoId, completed);
  const { data: analytics } = useAnalytics(videoId, completed);

  const seekTo = useCallback((time: number) => {
    const el = videoRef.current;
    if (el) {
      el.currentTime = time;
      void el.play().catch(() => undefined);
    }
    setCurrentTime(time);
  }, []);

  if (isLoading || !video) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  const videoUrl = resolveStorageUrl(`/storage/videos/${video.filename}`) ?? "";
  const processing = video.status === "processing" || video.status === "queued";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="icon">
            <Link to="/" aria-label="Back to dashboard">
              <ArrowLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-bold tracking-tight">{video.original_name}</h1>
            <p className="text-sm text-muted-foreground">
              {video.width}×{video.height} · {video.fps.toFixed(0)} fps · {formatDuration(video.duration)}
              {video.motion_algorithm ? ` · ${video.motion_algorithm}` : ""}
            </p>
          </div>
          <StatusBadge status={video.status} />
        </div>
        <div className="flex items-center gap-2">
          {completed ? (
            <>
              <Button asChild variant="outline" size="sm">
                <a href={videosApi.pdfUrl(video.id)} target="_blank" rel="noreferrer">
                  <FileText className="h-4 w-4" />
                  PDF report
                </a>
              </Button>
              <AnalyzeDialog videoId={video.id} label="Re-analyze" variant="outline" />
            </>
          ) : !processing ? (
            <AnalyzeDialog videoId={video.id} label="Analyze" />
          ) : null}
        </div>
      </div>

      {video.status === "failed" ? (
        <Card>
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            <div>
              <p className="font-medium">Analysis failed</p>
              <p className="text-sm text-muted-foreground">{video.error ?? "Unknown error"}</p>
            </div>
            <div className="ml-auto">
              <AnalyzeDialog videoId={video.id} label="Retry" variant="outline" />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {processing ? (
        <Card>
          <CardContent className="space-y-3 py-8">
            <div className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <p className="font-medium">{video.status_message || "Processing"}</p>
              <span className="ml-auto font-mono text-sm">{video.progress.toFixed(0)}%</span>
            </div>
            <Progress value={video.progress} />
            <p className="text-sm text-muted-foreground">
              Analysis runs offline; this page updates automatically.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {completed ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
          <div className="space-y-4 xl:col-span-3">
            <VideoPlayer
              ref={videoRef}
              src={videoUrl}
              nativeWidth={video.width}
              nativeHeight={video.height}
              fps={video.fps}
              events={events}
              currentTime={currentTime}
              onTimeUpdate={setCurrentTime}
              onSeek={seekTo}
            />
            {timeline ? (
              <MotionTimeline timeline={timeline} currentTime={currentTime} onSeek={seekTo} />
            ) : null}
          </div>
          <div className="xl:col-span-2">
            <HeatmapView videoId={video.id} />
          </div>
        </div>
      ) : null}

      {completed ? (
        <Tabs defaultValue="analytics">
          <TabsList>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="clips">Clips</TabsTrigger>
            <TabsTrigger value="performance">Performance</TabsTrigger>
          </TabsList>
          <TabsContent value="analytics">
            {analytics ? (
              <AnalyticsPanel analytics={analytics} />
            ) : (
              <Skeleton className="h-64 w-full rounded-xl" />
            )}
          </TabsContent>
          <TabsContent value="events">
            <EventTable videoId={video.id} onSeek={seekTo} />
          </TabsContent>
          <TabsContent value="clips">
            <ClipGallery videoId={video.id} onSeek={seekTo} />
          </TabsContent>
          <TabsContent value="performance">
            <ProcessingStatsPanel stats={video.processing_stats} />
          </TabsContent>
        </Tabs>
      ) : null}
    </div>
  );
}
