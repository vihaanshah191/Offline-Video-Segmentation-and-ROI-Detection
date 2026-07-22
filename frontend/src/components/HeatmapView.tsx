import { useState } from "react";
import { Download, Flame, ImageOff } from "lucide-react";

import { videosApi } from "@/api/videos";
import { resolveStorageUrl } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useHeatmap } from "@/hooks/useVideos";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  videoId: number;
  /** The video's own thumbnail, used as the base frame the heatmap is
   * blended over when the opacity slider is used interactively. */
  videoThumbnailUrl?: string | null;
}

export function HeatmapView({ videoId, videoThumbnailUrl }: Props) {
  const { data, isLoading } = useHeatmap(videoId);
  const [opacity, setOpacity] = useState(1);
  const baseFrame = resolveStorageUrl(videoThumbnailUrl ?? undefined);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Flame className="h-4 w-4 text-amber-400" />
          Motion heatmap
        </CardTitle>
        {data?.generated ? (
          <Button asChild size="sm" variant="outline">
            <a href={videosApi.heatmapDownloadUrl(videoId)} download>
              <Download className="h-4 w-4" />
              PNG
            </a>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="aspect-video w-full" />
        ) : data?.generated && data.heatmap_url ? (
          <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-black">
            {baseFrame ? (
              <img src={baseFrame} alt="" className="absolute inset-0 h-full w-full object-cover" />
            ) : null}
            <img
              src={resolveStorageUrl(data.heatmap_url)}
              alt="Motion heatmap"
              className="absolute inset-0 h-full w-full object-cover transition-opacity"
              style={{ opacity: baseFrame ? opacity : 1 }}
            />
          </div>
        ) : (
          <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-muted-foreground">
            <ImageOff className="h-8 w-8" />
            <p className="text-sm">Heatmap not generated yet</p>
          </div>
        )}

        {data?.generated && baseFrame ? (
          <div className="mt-3 space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Heatmap opacity</span>
              <span className="font-mono">{Math.round(opacity * 100)}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={opacity}
              onChange={(e) => setOpacity(Number(e.target.value))}
              className="w-full accent-primary"
              aria-label="Heatmap opacity"
            />
          </div>
        ) : null}

        <p className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="h-2 w-4 rounded-sm bg-blue-500" /> Low
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-4 rounded-sm bg-green-500" /> Medium
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-4 rounded-sm bg-red-500" /> High
          </span>
        </p>
      </CardContent>
    </Card>
  );
}
