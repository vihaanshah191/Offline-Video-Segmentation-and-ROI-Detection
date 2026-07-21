import { Cpu, HardDrive, Video as VideoIcon, Zap } from "lucide-react";

import { StatCard } from "@/components/StatCard";
import { VideoCard } from "@/components/VideoCard";
import { VideoUpload } from "@/components/VideoUpload";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSystemInfo, useVideos } from "@/hooks/useVideos";
import { formatBytes } from "@/lib/utils";

export function DashboardPage() {
  const { data: videos = [], isLoading } = useVideos();
  const { data: system } = useSystemInfo();

  const completed = videos.filter((v) => v.status === "completed").length;
  const processing = videos.filter((v) => v.status === "processing" || v.status === "queued").length;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Upload examination-hall recordings for offline motion, ROI and object analysis.
        </p>
      </section>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Videos" value={videos.length} icon={VideoIcon} accent="primary" />
        <StatCard label="Analyzed" value={completed} icon={Zap} accent="emerald" />
        <StatCard label="Processing" value={processing} icon={Cpu} accent="amber" />
        <StatCard
          label="Free storage"
          value={system ? formatBytes(system.free_disk_bytes) : "—"}
          icon={HardDrive}
          hint={system ? (system.cuda ? "CUDA available" : "CPU mode") : undefined}
          accent="violet"
        />
      </div>

      <VideoUpload />

      <section className="space-y-4">
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
    </div>
  );
}
