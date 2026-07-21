import { Download, Flame, ImageOff } from "lucide-react";

import { videosApi } from "@/api/videos";
import { resolveStorageUrl } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useHeatmap } from "@/hooks/useVideos";
import { Skeleton } from "@/components/ui/skeleton";

export function HeatmapView({ videoId }: { videoId: number }) {
  const { data, isLoading } = useHeatmap(videoId);

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
          <img
            src={resolveStorageUrl(data.heatmap_url)}
            alt="Motion heatmap"
            className="w-full rounded-lg border border-border"
          />
        ) : (
          <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-muted-foreground">
            <ImageOff className="h-8 w-8" />
            <p className="text-sm">Heatmap not generated yet</p>
          </div>
        )}
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
