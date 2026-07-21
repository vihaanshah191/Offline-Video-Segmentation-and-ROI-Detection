import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatTimestamp } from "@/lib/utils";
import type { Timeline } from "@/types";

interface Props {
  timeline: Timeline;
  currentTime: number;
  onSeek: (time: number) => void;
}

/** Interactive motion-intensity timeline. Clicking anywhere seeks the player. */
export function MotionTimeline({ timeline, currentTime, onSeek }: Props) {
  const data = useMemo(
    () =>
      timeline.points.map((p) => ({
        time: p.time,
        motion: Number((p.motion_score * 100).toFixed(2)),
        active: p.active,
      })),
    [timeline],
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Motion timeline</CardTitle>
        <span className="text-xs text-muted-foreground">Click to jump · {timeline.event_markers.length} events</span>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full">
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
                domain={[0, timeline.duration]}
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
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
