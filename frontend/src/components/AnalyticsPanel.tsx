import { Activity, AlertTriangle, Clock, Gauge, Layers, Timer, TrendingUp } from "lucide-react";

import { ObjectChart } from "@/components/ObjectChart";
import { StatCard } from "@/components/StatCard";
import { formatDuration, formatPercent, formatTimestamp } from "@/lib/utils";
import type { Analytics } from "@/types";

export function AnalyticsPanel({ analytics }: { analytics: Analytics }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
        <StatCard label="Total events" value={analytics.total_events} icon={Layers} accent="primary" />
        <StatCard
          label="Motion duration"
          value={formatDuration(analytics.total_motion_duration)}
          icon={Clock}
          hint={`${formatPercent(analytics.motion_coverage)} of video`}
          accent="emerald"
        />
        <StatCard
          label="Peak activity"
          value={formatTimestamp(analytics.peak_activity_time)}
          icon={TrendingUp}
          hint={`score ${analytics.peak_motion_score.toFixed(3)}`}
          accent="amber"
        />
        <StatCard
          label="Avg motion"
          value={analytics.average_motion_score.toFixed(3)}
          icon={Gauge}
          accent="violet"
        />
        <StatCard
          label="Longest event"
          value={formatDuration(analytics.longest_event_duration)}
          icon={Timer}
          hint={analytics.longest_event_id ? `#${analytics.longest_event_id}` : undefined}
          accent="primary"
        />
        <StatCard
          label="Objects detected"
          value={analytics.total_detections}
          icon={Activity}
          accent="emerald"
        />
        <StatCard
          label="Prohibited"
          value={analytics.prohibited_detections}
          icon={AlertTriangle}
          accent="rose"
        />
      </div>
      <ObjectChart objectCounts={analytics.object_counts} />
    </div>
  );
}
