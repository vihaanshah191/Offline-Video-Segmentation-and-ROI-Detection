import { forwardRef, useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { EventRecord } from "@/types";

interface Props {
  src: string;
  nativeWidth: number;
  nativeHeight: number;
  events: EventRecord[];
  currentTime: number;
  onTimeUpdate: (t: number) => void;
}

/**
 * HTML5 video player with a scaled SVG overlay that draws the ROI and object
 * detection boxes of whichever event is active at the current playback time.
 */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer(
  { src, nativeWidth, nativeHeight, events, currentTime, onTimeUpdate },
  ref,
) {
  const [showOverlay, setShowOverlay] = useState(true);

  const activeEvent = useMemo(
    () => events.find((e) => currentTime >= e.start_time && currentTime <= e.end_time),
    [events, currentTime],
  );

  const vb = `0 0 ${nativeWidth || 1} ${nativeHeight || 1}`;

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl border border-border bg-black">
        <video
          ref={ref}
          src={src}
          controls
          className="w-full"
          onTimeUpdate={(e) => onTimeUpdate((e.target as HTMLVideoElement).currentTime)}
        />
        {showOverlay && activeEvent ? (
          <svg
            viewBox={vb}
            preserveAspectRatio="xMidYMid meet"
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
            {activeEvent.rois.map((roi) => (
              <rect
                key={`roi-${roi.id}`}
                x={roi.x}
                y={roi.y}
                width={roi.w}
                height={roi.h}
                fill="hsl(199 89% 52% / 0.12)"
                stroke="hsl(199 89% 52%)"
                strokeWidth={Math.max(2, nativeWidth / 320)}
              />
            ))}
            {activeEvent.detections.map((d) => (
              <g key={`det-${d.id}`}>
                <rect
                  x={d.x}
                  y={d.y}
                  width={d.w}
                  height={d.h}
                  fill="none"
                  stroke={d.prohibited ? "hsl(0 84% 60%)" : "hsl(160 84% 39%)"}
                  strokeWidth={Math.max(2, nativeWidth / 320)}
                />
                <text
                  x={d.x + 4}
                  y={Math.max(14, d.y - 4)}
                  fill={d.prohibited ? "hsl(0 84% 60%)" : "hsl(160 84% 39%)"}
                  fontSize={Math.max(12, nativeWidth / 40)}
                  fontWeight="bold"
                >
                  {d.label} {(d.confidence * 100).toFixed(0)}%
                </text>
              </g>
            ))}
          </svg>
        ) : null}
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {activeEvent ? (
            <Badge variant="success">Event #{activeEvent.id} active</Badge>
          ) : (
            <Badge variant="secondary">No active event</Badge>
          )}
          {activeEvent?.detections.some((d) => d.prohibited) ? (
            <Badge variant="destructive">Prohibited object</Badge>
          ) : null}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowOverlay((s) => !s)}
          className={cn(!showOverlay && "text-muted-foreground")}
        >
          {showOverlay ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          ROI overlay
        </Button>
      </div>
    </div>
  );
});
