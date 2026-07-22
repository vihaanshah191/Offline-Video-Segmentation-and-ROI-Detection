import { Link } from "react-router-dom";
import { History } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDuration } from "@/lib/utils";
import type { Video } from "@/types";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/** The last few completed/failed/cancelled analyses, most recent first —
 * distinct from the full video grid, which is sorted by upload time. */
export function RecentAnalyses({ videos }: { videos: Video[] }) {
  const recent = [...videos]
    .filter((v) => v.analyzed_at)
    .sort((a, b) => new Date(b.analyzed_at!).getTime() - new Date(a.analyzed_at!).getTime())
    .slice(0, 5);

  if (recent.length === 0) return null;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Recent analyses</CardTitle>
        <History className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-2">
        {recent.map((video) => (
          <Link
            key={video.id}
            to={`/videos/${video.id}`}
            className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent/40"
          >
            <span className="truncate">{video.original_name}</span>
            <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
              {formatDuration(video.duration)}
              <StatusBadge status={video.status} />
              {timeAgo(video.analyzed_at!)}
            </span>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
