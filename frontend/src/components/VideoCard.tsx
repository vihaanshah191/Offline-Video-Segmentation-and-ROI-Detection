import { Link } from "react-router-dom";
import { Clock, Film, Layers, Loader2, Trash2 } from "lucide-react";

import { AnalyzeDialog } from "@/components/AnalyzeDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useDeleteVideo } from "@/hooks/useVideos";
import { formatBytes, formatDuration } from "@/lib/utils";
import type { Video } from "@/types";

export function VideoCard({ video }: { video: Video }) {
  const del = useDeleteVideo();
  const processing = video.status === "processing" || video.status === "queued";

  return (
    <Card className="group animate-fade-in overflow-hidden transition-shadow hover:shadow-lg hover:shadow-primary/5">
      <CardContent className="p-0">
        <Link to={`/videos/${video.id}`} className="block">
          <div className="flex aspect-video items-center justify-center bg-gradient-to-br from-muted to-background">
            <Film className="h-10 w-10 text-muted-foreground/40" />
          </div>
        </Link>
        <div className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <Link to={`/videos/${video.id}`} className="min-w-0">
              <h3 className="truncate font-semibold hover:text-primary">{video.original_name}</h3>
              <p className="text-xs text-muted-foreground">
                {video.width}×{video.height} · {formatBytes(video.size_bytes)}
              </p>
            </Link>
            <StatusBadge status={video.status} />
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {formatDuration(video.duration)}
            </span>
            <span className="flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              {video.fps.toFixed(0)} fps
            </span>
          </div>

          {processing ? (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {video.status_message || "Processing"}
                </span>
                <span>{video.progress.toFixed(0)}%</span>
              </div>
              <Progress value={video.progress} />
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 pt-1">
              {video.status === "completed" ? (
                <Button asChild size="sm" variant="secondary">
                  <Link to={`/videos/${video.id}`}>View results</Link>
                </Button>
              ) : video.status === "failed" || video.status === "cancelled" ? (
                <AnalyzeDialog videoId={video.id} label="Retry" variant="outline" />
              ) : (
                <AnalyzeDialog videoId={video.id} label="Analyze" />
              )}
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete video"
                onClick={() => {
                  if (confirm(`Delete "${video.original_name}"? This cannot be undone.`)) {
                    del.mutate(video.id);
                  }
                }}
              >
                <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
