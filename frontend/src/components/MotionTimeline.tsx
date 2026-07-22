import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ZoomIn } from "lucide-react";

import { resolveStorageUrl } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/SeverityBadge";
import { formatDuration, formatTimestamp } from "@/lib/utils";
import type { EventMarker, EventRecord, Severity, Timeline } from "@/types";

interface Props {
  timeline: Timeline;
  currentTime: number;
  onSeek: (time: number) => void;
  /** Full event records (with thumbnails) for the hover preview; optional so
   * this component still works with just timeline data if events haven't
   * loaded yet. */
  events?: EventRecord[];
}

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "hsl(0 84% 60%)",
  warning: "hsl(38 92% 50%)",
  normal: "hsl(160 84% 39%)",
};

/**
 * Interactive motion-intensity timeline. Clicking anywhere seeks the player.
 * The bottom Brush control allows zooming into a specific time range for
 * detailed inspection of long recordings (drag its handles to narrow the
 * range shown above). A severity-colored marker strip beneath the chart
 * shows every detected event; hovering one previews its thumbnail, objects
 * and severity.
 */
export function MotionTimeline({ timeline, currentTime, onSeek, events = [] }: Props) {
  const [brushRange, setBrushRange] = useState<[number, number] | null>(null);
  const [hoveredMarker, setHoveredMarker] = useState<EventMarker | null>(null);

  const data = useMemo(
    () =>
      timeline.points.map((p) => ({
        time: p.time,
        motion: Number((p.motion_score * 100).toFixed(2)),
        active: p.active,
      })),
    [timeline],
  );

  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const isZoomed = brushRange !== null;
  const domainStart = brushRange ? brushRange[0] : 0;
  const domainEnd = brushRange ? brushRange[1] : timeline.duration || 1;
  const domainSpan = Math.max(0.001, domainEnd - domainStart);

  const hoveredEvent = hoveredMarker ? eventById.get(hoveredMarker.id) : undefined;
  const hoveredThumb = hoveredEvent ? resolveStorageUrl(hoveredEvent.thumbnail_url) : undefined;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Motion timeline</CardTitle>
        <div className="flex items-center gap-2">
          {isZoomed ? (
            <Button variant="ghost" size="sm" onClick={() => setBrushRange(null)}>
              Reset zoom
            </Button>
          ) : null}
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <ZoomIn className="h-3.5 w-3.5" />
            Drag the bottom bar to zoom · click to jump · {timeline.event_markers.length} events
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 8, right: 12, left: -18, bottom: 0 }}
              onClick={(state) => {
                const label = state?.activeLabel;
                if (label !== undefined && label !== null) onSeek(Number(label));
              }}
            >
              <defs>
                <linearGradient id="motionFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(199 89% 52%)" stopOpacity={0.7} />
                  <stop offset="100%" stopColor="hsl(199 89% 52%)" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 18%)" vertical={false} />
              <XAxis
                dataKey="time"
                type="number"
                domain={brushRange ? [brushRange[0], brushRange[1]] : [0, timeline.duration]}
                allowDataOverflow
                tickFormatter={(v) => formatTimestamp(Number(v))}
                stroke="hsl(215 20% 65%)"
                fontSize={11}
              />
              <YAxis stroke="hsl(215 20% 65%)" fontSize={11} unit="%" width={44} />
              <Tooltip
                contentStyle={{
                  background: "hsl(222 44% 9%)",
                  border: "1px solid hsl(217 33% 18%)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(v) => `t = ${formatTimestamp(Number(v))}`}
                formatter={(value: number, _name, item) => {
                  const t = Number(item?.payload?.time ?? 0);
                  const marker = timeline.event_markers.find((m) => t >= m.start && t <= m.end);
                  if (!marker) return [`${value}%`, "Motion"];
                  const objectsLabel = marker.objects.length ? marker.objects.join(", ") : "none";
                  return [
                    `${value}% · event #${marker.id} (${marker.severity}) · objects: ${objectsLabel}`,
                    "Motion",
                  ];
                }}
              />
              {/* Highlight each detected activity segment, colored by severity. */}
              {timeline.event_markers.map((m) => (
                <ReferenceLine
                  key={m.id}
                  x={m.start}
                  stroke={SEVERITY_COLOR[m.severity]}
                  strokeOpacity={0.45}
                  strokeDasharray="2 2"
                />
              ))}
              <ReferenceLine x={currentTime} stroke="hsl(0 84% 60%)" strokeWidth={2} />
              <Area
                type="monotone"
                dataKey="motion"
                stroke="hsl(199 89% 52%)"
                strokeWidth={2}
                fill="url(#motionFill)"
                isAnimationActive={false}
              />
              <Brush
                dataKey="time"
                height={24}
                stroke="hsl(199 89% 52%)"
                fill="hsl(222 44% 9%)"
                travellerWidth={8}
                tickFormatter={(v) => formatTimestamp(Number(v))}
                onChange={(range) => {
                  if (range.startIndex == null || range.endIndex == null || data.length === 0) return;
                  const start = data[range.startIndex]?.time ?? 0;
                  const end = data[range.endIndex]?.time ?? timeline.duration;
                  setBrushRange(start < end ? [start, end] : null);
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Event marker strip: severity-colored, object-labeled, hover-previewable. */}
        <div className="relative">
          <div className="relative h-6 w-full overflow-hidden rounded-md bg-muted/40">
            {timeline.event_markers
              .filter((m) => m.end >= domainStart && m.start <= domainEnd)
              .map((m) => {
                const left = (Math.max(m.start, domainStart) - domainStart) / domainSpan;
                const width = Math.max(
                  0.004,
                  (Math.min(m.end, domainEnd) - Math.max(m.start, domainStart)) / domainSpan,
                );
                return (
                  <button
                    key={m.id}
                    className="absolute top-0 h-full cursor-pointer opacity-80 transition-opacity hover:opacity-100"
                    style={{
                      left: `${left * 100}%`,
                      width: `${width * 100}%`,
                      backgroundColor: SEVERITY_COLOR[m.severity],
                    }}
                    onMouseEnter={() => setHoveredMarker(m)}
                    onMouseLeave={() => setHoveredMarker((prev) => (prev?.id === m.id ? null : prev))}
                    onClick={() => onSeek(m.start)}
                    aria-label={`Event #${m.id} at ${formatTimestamp(m.start)}`}
                  />
                );
              })}
          </div>
          {/* Time ruler: evenly spaced labels across the currently visible domain. */}
          <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
            {[0, 0.25, 0.5, 0.75, 1].map((f) => (
              <span key={f}>{formatTimestamp(domainStart + f * domainSpan)}</span>
            ))}
          </div>
        </div>

        {hoveredMarker ? (
          <div className="flex items-center gap-3 rounded-md border border-border bg-card p-2 text-sm">
            {hoveredThumb ? (
              <img src={hoveredThumb} alt="" className="h-12 w-16 rounded object-cover" />
            ) : null}
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">Event #{hoveredMarker.id}</span>
                <SeverityBadge severity={hoveredMarker.severity} />
              </div>
              <p className="text-xs text-muted-foreground">
                {formatTimestamp(hoveredMarker.start)}–{formatTimestamp(hoveredMarker.end)} (
                {formatDuration(hoveredMarker.end - hoveredMarker.start)}) ·{" "}
                {hoveredMarker.objects.length ? hoveredMarker.objects.join(", ") : "no objects detected"}
              </p>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
