import { AlertTriangle, Cpu, HardDrive, Video as VideoIcon, Zap } from "lucide-react";

import { QueuePanel } from "@/components/QueuePanel";
import { StatCard } from "@/components/StatCard";
import { SystemPanel } from "@/components/SystemPanel";
import { VideoCard } from "@/components/VideoCard";
import { VideoUpload } from "@/components/VideoUpload";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGlobalStats, useSystemInfo, useVideos } from "@/hooks/useVideos";
import { formatBytes, formatDuration } from "@/lib/utils";

export function DashboardPage() {
  const { data: videoPage, isLoading } = useVideos({ limit: 100 });
  const { data: system } = useSystemInfo();
  const { data: stats } = useGlobalStats();
  const videos = videoPage?.items ?? [];

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Upload examination-hall recordings for offline motion, ROI and object analysis.
        </p>
      </section>

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
          <SystemPanel system={system} />
        </aside>
      </div>
    </div>
  );
}
