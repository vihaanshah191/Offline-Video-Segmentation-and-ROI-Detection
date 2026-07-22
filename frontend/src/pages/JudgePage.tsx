import {
  Activity,
  Boxes,
  Cpu,
  Database,
  Flame,
  Layers,
  Scissors,
  ScanSearch,
  Shield,
  Upload,
  Video as VideoIcon,
  Zap,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useGlobalStats, useSystemInfo } from "@/hooks/useVideos";
import { formatDuration } from "@/lib/utils";

const PIPELINE_STEPS = [
  {
    icon: Upload,
    title: "Upload",
    detail: "Extension + magic-byte validation, streamed to disk with a size cap.",
  },
  {
    icon: Activity,
    title: "Motion Detection",
    detail: "MOG2 / frame-diff / optical-flow (or auto-selected), Otsu adaptive thresholding.",
  },
  {
    icon: ScanSearch,
    title: "ROI Extraction",
    detail: "Contours merged by IoU into stable regions, filtered by size relative to frame.",
  },
  {
    icon: Scissors,
    title: "Segmentation",
    detail: "Hysteresis thresholding + temporal smoothing turns noisy scores into clean events.",
  },
  {
    icon: Boxes,
    title: "Object Detection",
    detail: "Batched YOLOv11 inference on representative frames per event, perceptual-hash cached.",
  },
  {
    icon: Flame,
    title: "Heatmap & Reports",
    detail: "Whole-video + per-event heatmaps, CSV export, and a full PDF investigation report.",
  },
];

const DETECTION_NOTES = [
  {
    label: "phone / bag / bottle / laptop / person",
    note: "Direct YOLOv11 (COCO) classes — high-confidence, no proxying involved.",
    kind: "direct" as const,
  },
  {
    label: "book → \"possible notes\"",
    note:
      "COCO has no 'handwritten notes' class. A detected book is surfaced as a heuristic, " +
      "visually distinct (dashed box, 'possible' label) signal — never claimed as confirmed.",
    kind: "heuristic" as const,
  },
];

export function JudgePage() {
  const { data: stats } = useGlobalStats();
  const { data: system } = useSystemInfo();

  return (
    <div className="mx-auto max-w-5xl space-y-10 pb-16">
      <section className="space-y-2 text-center">
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">Judge Mode</p>
        <h1 className="text-3xl font-bold tracking-tight">
          Offline Video Segmentation &amp; ROI Detection
        </h1>
        <p className="mx-auto max-w-2xl text-muted-foreground">
          An AI-powered, fully offline analytics pipeline for examination-hall recordings: motion
          detection, region-of-interest extraction, event segmentation, object detection and
          investigation-ready reports — no cloud dependency, no internet required at analysis time.
        </p>
      </section>

      {/* Live counters */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <LiveStat icon={VideoIcon} label="Videos analyzed" value={stats?.completed_videos ?? "—"} />
        <LiveStat icon={Layers} label="Events detected" value={stats?.total_events ?? "—"} />
        <LiveStat
          icon={Activity}
          label="Footage processed"
          value={stats ? formatDuration(stats.total_video_duration_seconds) : "—"}
        />
        <LiveStat icon={Cpu} label="Inference device" value={system?.cuda ? "GPU (CUDA)" : "CPU"} />
      </section>

      {/* Pipeline diagram */}
      <section className="space-y-4">
        <h2 className="text-center text-lg font-semibold">Processing Pipeline</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.title} className="relative">
              <Card className="h-full">
                <CardContent className="flex flex-col items-center gap-2 p-4 text-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15">
                    <step.icon className="h-5 w-5 text-primary" />
                  </div>
                  <p className="text-sm font-semibold">
                    {i + 1}. {step.title}
                  </p>
                  <p className="text-xs text-muted-foreground">{step.detail}</p>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      </section>

      {/* Model / system info */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Zap className="h-4 w-4" />
              Model &amp; Runtime
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Object detection model" value={system?.yolo_model ?? "—"} />
            <Row label="Inference device" value={system?.yolo_device ?? "—"} />
            <Row label="Task backend" value={system?.task_backend ?? "—"} />
            <Row label="Default motion algorithm" value={system?.default_motion_algorithm ?? "—"} />
            <Row label="FFmpeg available" value={system?.ffmpeg ? "Yes" : "No (OpenCV fallback)"} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-4 w-4" />
              Honesty by Design
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {DETECTION_NOTES.map((d) => (
              <div key={d.label}>
                <p className="font-medium">
                  {d.label}{" "}
                  <span
                    className={
                      d.kind === "heuristic"
                        ? "rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-400"
                        : "rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400"
                    }
                  >
                    {d.kind}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">{d.note}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4" />
              Why This Design
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
            <div>
              <p className="font-medium">Fully offline</p>
              <p className="text-xs text-muted-foreground">
                No cloud API calls during analysis — everything runs on local OpenCV/YOLO, so it
                works in air-gapped exam-hall environments.
              </p>
            </div>
            <div>
              <p className="font-medium">Streaming pipeline</p>
              <p className="text-xs text-muted-foreground">
                A bounded frame-reader queue plus a two-pass design (full motion decode once, object
                detection only on a handful of representative frames per event) keeps memory flat on
                multi-hour recordings.
              </p>
            </div>
            <div>
              <p className="font-medium">Never overclaims</p>
              <p className="text-xs text-muted-foreground">
                Heuristic detections are visually and textually distinguished from confirmed ones
                throughout the UI, CSV and PDF report — a screening aid, not a verdict.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function LiveStat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof VideoIcon;
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-1 p-5 text-center">
        <Icon className="h-5 w-5 text-primary" />
        <p className="text-2xl font-bold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 py-1 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
