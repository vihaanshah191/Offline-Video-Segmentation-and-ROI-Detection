import { Badge } from "@/components/ui/badge";
import type { VideoStatus } from "@/types";

const MAP: Record<VideoStatus, { label: string; variant: "default" | "secondary" | "destructive" | "success" | "warning" }> = {
  uploaded: { label: "Uploaded", variant: "secondary" },
  queued: { label: "Queued", variant: "warning" },
  processing: { label: "Processing", variant: "warning" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "secondary" },
};

export function StatusBadge({ status }: { status: VideoStatus }) {
  const cfg = MAP[status] ?? MAP.uploaded;
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
