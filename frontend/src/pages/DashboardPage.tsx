import { useNavigate } from "react-router-dom";
import { AlertTriangle, Cpu, HardDrive, Loader2, Sparkles, Video as VideoIcon, Zap } from "lucide-react";

import { QueuePanel } from "@/components/QueuePanel";
import { RecentAnalyses } from "@/components/RecentAnalyses";
import { StatCard } from "@/components/StatCard";
import { SystemPanel } from "@/components/SystemPanel";
import { VideoCard } from "@/components/VideoCard";
import { VideoUpload } from "@/components/VideoUpload";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGlobalStats, useLoadDemoSample, useSystemInfo, useVideos } from "@/hooks/useVideos";
import { formatBytes, formatDuration } from "@/lib/utils";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: videoPage, isLoading } = useVideos({ limit: 100 });
  const { data: system } = useSystemInfo();
  const { data: stats } = useGlobalStats();
  const demo = useLoadDemoSample();
  const videos = videoPage?.items ?? [];

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Upload examination-hall recordings for offline motion, ROI and object analysis.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => demo.mutate(undefined, { onSuccess: (video) => navigate(`/videos/${video.id}`) })}
          disabled={demo.isPending}
          title="Load the bundled sample video and analyze it automatically"
        >
          {demo.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Try demo
        </Button>
      </section>
      {demo.isError ? (
        <p className="text-sm text-destructive">
          {(demo.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Failed to load the demo sample."}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Videos" value={stats?.total_videos ?? videos.length} icon={VideoIcon} accent="primary" />
        <StatCard label="Analyzed" value={stats?.completed_videos ?? 0} icon={Zap} accent="emerald" />
        <StatCard label="Processing" value={stats?.processing_videos ?? 0} icon={Cpu} accent="amber" />
        {stats && stats.failed_videos > 0 ? (
          <StatCard label="Failed" value={stats.failed_videos} icon={AlertTriangle} accent="rose" />
        ) : (
          <StatCard
            label="Total footage"
            value={stats ? formatDuration(stats.total_video_duration_seconds) : "—"}
            icon={VideoIcon}
            accent="violet"
          />
        )}
        <StatCard
          label="Free storage"
          value={system ? formatBytes(system.free_disk_bytes) : "—"}
          icon={HardDrive}
          hint={system ? (system.cuda ? "CUDA available" : "CPU mode") : undefined}
          accent="violet"
        />
      </div>

      <VideoUpload />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="space-y-4 xl:col-span-2">
          <h2 className="text-lg font-semibold">Your videos</h2>
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-64 w-full rounded-xl" />
              ))}
            </div>
          ) : videos.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-14 text-center text-muted-foreground">
                <VideoIcon className="h-10 w-10 opacity-40" />
                <p>No videos yet. Upload one above to get started.</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {videos.map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <QueuePanel />
          <RecentAnalyses videos={videos} />
          <SystemPanel system={system} />
        </aside>
      </div>
    </div>
  );
}
