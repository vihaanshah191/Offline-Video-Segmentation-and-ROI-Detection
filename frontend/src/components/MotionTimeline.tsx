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

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatTimestamp } from "@/lib/utils";
import type { Timeline } from "@/types";

interface Props {
  timeline: Timeline;
  currentTime: number;
  onSeek: (time: number) => void;
}

/**
 * Interactive motion-intensity timeline. Clicking anywhere seeks the player.
 * The bottom Brush control allows zooming into a specific time range for
 * detailed inspection of long recordings (drag its handles to narrow the
 * range shown above).
 */
export function MotionTimeline({ timeline, currentTime, onSeek }: Props) {
  const [brushRange, setBrushRange] = useState<[number, number] | null>(null);

  const data = useMemo(
    () =>
      timeline.points.map((p) => ({
        time: p.time,
        motion: Number((p.motion_score * 100).toFixed(2)),
        active: p.active,
      })),
    [timeline],
  );

  const isZoomed = brushRange !== null;

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
      <CardContent>
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
                formatter={(value: number) => [`${value}%`, "Motion"]}
              />
              {/* Highlight each detected activity segment. */}
              {timeline.event_markers.map((m) => (
                <ReferenceLine
                  key={m.id}
                  x={m.start}
                  stroke="hsl(160 84% 39%)"
                  strokeOpacity={0.35}
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
      </CardContent>
    </Card>
  );
}
