import { Cpu, Database, Gauge, ImageOff, Timer, Zap } from "lucide-react";

import { StatCard } from "@/components/StatCard";
import { Card, CardContent } from "@/components/ui/card";
import type { ProcessingStats } from "@/types";

/** Displays the pipeline's own performance telemetry from the most recent
 * analysis run — throughput, per-stage timing and cache efficiency. Useful
 * both for judges evaluating engineering rigor and for operators tuning
 * FRAME_SAMPLE_STEP / hardware for large deployments. */
export function ProcessingStatsPanel({ stats }: { stats: ProcessingStats | null }) {
  if (!stats) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-14 text-center text-muted-foreground">
          <ImageOff className="h-10 w-10 opacity-40" />
          <p>No processing statistics recorded for this run.</p>
        </CardContent>
      </Card>
    );
  }

  const cacheTotal = stats.object_detection_cache_hits + stats.object_detection_cache_misses;
  const cacheHitRate = cacheTotal > 0 ? stats.object_detection_cache_hits / cacheTotal : null;

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
      <StatCard
        label="Motion detection"
        value={`${stats.motion_detection_seconds.toFixed(2)}s`}
        icon={Timer}
        hint={`${stats.motion_detection_throughput_fps.toFixed(0)} fps throughput`}
        accent="primary"
      />
      <StatCard
        label="Total pipeline time"
        value={`${stats.total_pipeline_seconds.toFixed(2)}s`}
        icon={Zap}
        accent="emerald"
      />
      <StatCard
        label="Resolved algorithm"
        value={stats.resolved_motion_algorithm}
        icon={Cpu}
        accent="violet"
      />
      <StatCard
        label="Frames processed"
        value={stats.frames_processed.toLocaleString()}
        icon={Gauge}
        hint={stats.frames_with_errors > 0 ? `${stats.frames_with_errors} skipped (corrupt)` : "0 errors"}
        accent={stats.frames_with_errors > 0 ? "amber" : "primary"}
      />
      <StatCard label="Samples analysed" value={stats.samples.toLocaleString()} icon={Gauge} accent="primary" />
      <StatCard
        label="Detection cache"
        value={cacheHitRate !== null ? `${(cacheHitRate * 100).toFixed(0)}% hit rate` : "disabled"}
        icon={Database}
        hint={
          cacheTotal > 0
            ? `${stats.object_detection_cache_hits} hits / ${stats.object_detection_cache_misses} misses`
            : undefined
        }
        accent="emerald"
      />
    </div>
  );
}
