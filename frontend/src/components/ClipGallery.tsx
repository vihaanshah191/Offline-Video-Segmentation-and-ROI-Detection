import { Download, Film, Play } from "lucide-react";

import { resolveStorageUrl } from "@/api/client";
import { videosApi } from "@/api/videos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useClips } from "@/hooks/useVideos";
import { formatDuration, formatTimestamp } from "@/lib/utils";

interface Props {
  videoId: number;
  onSeek: (time: number) => void;
}

export function ClipGallery({ videoId, onSeek }: Props) {
  const { data: clips = [], isLoading } = useClips(videoId);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Segmented clips ({clips.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading clips…</p>
        ) : clips.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No clips generated.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {clips.map((clip) => (
              <div
                key={clip.event_id}
                className="overflow-hidden rounded-lg border border-border bg-card/50"
              >
                <button
                  className="relative flex aspect-video w-full items-center justify-center bg-gradient-to-br from-muted to-background"
                  onClick={() => onSeek(clip.start_time)}
                >
                  {clip.thumbnail_url ? (
                    <img
                      src={resolveStorageUrl(clip.thumbnail_url)}
                      alt={`Clip ${clip.event_id}`}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <Film className="h-8 w-8 text-muted-foreground/40" />
                  )}
                  <span className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 transition-opacity hover:opacity-100">
                    <Play className="h-8 w-8 text-white" />
                  </span>
                </button>
                <div className="space-y-2 p-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-muted-foreground">
                      {formatTimestamp(clip.start_time)} → {formatTimestamp(clip.end_time)}
                    </span>
                    <span className="font-medium">{formatDuration(clip.duration)}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {clip.objects.length === 0 ? (
                      <span className="text-xs text-muted-foreground">No objects</span>
                    ) : (
                      clip.objects.map((o) => (
                        <Badge key={o} variant="secondary">
                          {o}
                        </Badge>
                      ))
                    )}
                  </div>
                  <Button asChild size="sm" variant="outline" className="w-full">
                    <a href={videosApi.clipDownloadUrl(videoId, clip.event_id)} download>
                      <Download className="h-4 w-4" />
                      Download clip
                    </a>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
