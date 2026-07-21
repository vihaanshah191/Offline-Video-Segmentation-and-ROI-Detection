import { forwardRef, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff, HelpCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatTimestamp } from "@/lib/utils";
import type { EventRecord } from "@/types";

interface Props {
  src: string;
  nativeWidth: number;
  nativeHeight: number;
  fps: number;
  events: EventRecord[];
  currentTime: number;
  onTimeUpdate: (t: number) => void;
  onSeek: (t: number) => void;
}

/**
 * HTML5 video player with a scaled SVG overlay that draws the ROI and object
 * detection boxes of whichever event is active at the current playback time,
 * plus single-frame step controls for frame-by-frame inspection.
 */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer(
  { src, nativeWidth, nativeHeight, fps, events, currentTime, onTimeUpdate, onSeek },
  ref,
) {
  const [showOverlay, setShowOverlay] = useState(true);

  const activeEvent = useMemo(
    () => events.find((e) => currentTime >= e.start_time && currentTime <= e.end_time),
    [events, currentTime],
  );

  const frameDuration = fps > 0 ? 1 / fps : 1 / 25;
  const stepFrame = (direction: 1 | -1) => {
    const el = (ref as React.RefObject<HTMLVideoElement>)?.current;
    if (!el) return;
    el.pause();
    const next = Math.max(0, el.currentTime + direction * frameDuration);
    el.currentTime = next;
    onSeek(next);
  };

  const vb = `0 0 ${nativeWidth || 1} ${nativeHeight || 1}`;
  const hasProhibited = activeEvent?.detections.some((d) => d.prohibited) ?? false;
  const hasConfirmedProhibited =
    activeEvent?.detections.some((d) => d.prohibited && !d.heuristic) ?? false;

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
            {activeEvent.detections.map((d) => {
              const color = d.prohibited ? "hsl(0 84% 60%)" : "hsl(160 84% 39%)";
              // Confidence drives opacity so low-confidence boxes read as
              // tentative and high-confidence ones as assertive at a glance.
              const opacity = Math.max(0.35, d.confidence);
              return (
                <g key={`det-${d.id}`} opacity={opacity}>
                  <rect
                    x={d.x}
                    y={d.y}
                    width={d.w}
                    height={d.h}
                    fill="none"
                    stroke={color}
                    strokeWidth={Math.max(2, nativeWidth / 320)}
                    strokeDasharray={d.heuristic ? "6 4" : undefined}
                  />
                  <text
                    x={d.x + 4}
                    y={Math.max(14, d.y - 4)}
                    fill={color}
                    fontSize={Math.max(12, nativeWidth / 40)}
                    fontWeight="bold"
                  >
                    {d.heuristic ? "possible " : ""}
                    {d.label} {(d.confidence * 100).toFixed(0)}%
                  </text>
                </g>
              );
            })}
          </svg>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {activeEvent ? (
            <Badge variant="success">Event #{activeEvent.id} active</Badge>
          ) : (
            <Badge variant="secondary">No active event</Badge>
          )}
          {hasConfirmedProhibited ? (
            <Badge variant="destructive">Prohibited object</Badge>
          ) : hasProhibited ? (
            <Badge variant="warning" className="gap-1">
              <HelpCircle className="h-3 w-3" />
              Possible prohibited item
            </Badge>
          ) : null}
          <span className="font-mono text-xs text-muted-foreground">{formatTimestamp(currentTime)}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => stepFrame(-1)} title="Previous frame" aria-label="Previous frame">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" onClick={() => stepFrame(1)} title="Next frame" aria-label="Next frame">
            <ChevronRight className="h-4 w-4" />
          </Button>
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
    </div>
  );
});
