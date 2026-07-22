import { Link } from "react-router-dom";
import { ListTodo } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { useQueue } from "@/hooks/useVideos";

/** Live "what's running right now" view: every queued/processing video. */
export function QueuePanel() {
  const { data: queue } = useQueue();
  const items = queue ?? [];

  if (items.length === 0) return null;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Processing queue</CardTitle>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <ListTodo className="h-3.5 w-3.5" />
          {items.length} active
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((video) => (
          <Link
            key={video.id}
            to={`/videos/${video.id}`}
            className="block space-y-1.5 rounded-md border border-border p-2.5 hover:bg-accent/40"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">{video.original_name}</span>
              <StatusBadge status={video.status} />
            </div>
            <Progress value={video.progress} />
            <p className="truncate text-xs text-muted-foreground">
              {video.status_message || "Waiting…"} · {video.progress.toFixed(0)}%
            </p>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
