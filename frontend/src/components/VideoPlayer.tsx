import { forwardRef, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Camera,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Expand,
  HelpCircle,
  SkipBack,
  SkipForward,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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

const SPEEDS = [0.25, 0.5, 1, 1.5, 2, 4];

/** Parses "mm:ss", "hh:mm:ss" or a plain number of seconds. Returns null on garbage input. */
function parseTimestamp(input: string): number | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  if (/^\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  const parts = trimmed.split(":").map((p) => Number(p));
  if (parts.some((p) => Number.isNaN(p))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

/**
 * HTML5 video player with a scaled SVG overlay that draws the ROI and object
 * detection boxes of whichever event is active at the current playback time,
 * frame-by-frame stepping, playback-speed control, previous/next-event
 * navigation, skip-to-timestamp, custom fullscreen and PNG snapshot export.
 */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer(
  { src, nativeWidth, nativeHeight, fps, events, currentTime, onTimeUpdate, onSeek },
  ref,
) {
  const [showRoi, setShowRoi] = useState(true);
  const [showDetections, setShowDetections] = useState(true);
  const [speed, setSpeed] = useState("1");
  const [timeInput, setTimeInput] = useState("");
  const [timeError, setTimeError] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const activeEvent = useMemo(
    () => events.find((e) => currentTime >= e.start_time && currentTime <= e.end_time),
    [events, currentTime],
  );

  const videoEl = () => (ref as React.RefObject<HTMLVideoElement>)?.current;

  const frameDuration = fps > 0 ? 1 / fps : 1 / 25;
  const stepFrame = (direction: 1 | -1) => {
    const el = videoEl();
    if (!el) return;
    el.pause();
    const next = Math.max(0, el.currentTime + direction * frameDuration);
    el.currentTime = next;
    onSeek(next);
  };

  const sortedEvents = useMemo(() => [...events].sort((a, b) => a.start_time - b.start_time), [events]);
  const jumpToEvent = (direction: 1 | -1) => {
    if (sortedEvents.length === 0) return;
    const next =
      direction === 1
        ? sortedEvents.find((e) => e.start_time > currentTime + 0.05)
        : [...sortedEvents].reverse().find((e) => e.start_time < currentTime - 0.05);
    const target = next ?? (direction === 1 ? sortedEvents[0] : sortedEvents[sortedEvents.length - 1]);
    onSeek(target.start_time);
  };

  const changeSpeed = (value: string) => {
    setSpeed(value);
    const el = videoEl();
    if (el) el.playbackRate = Number(value);
  };

  const handleSkip = (e: FormEvent) => {
    e.preventDefault();
    const seconds = parseTimestamp(timeInput);
    const el = videoEl();
    if (seconds === null || !el) {
      setTimeError(true);
      return;
    }
    setTimeError(false);
    const clamped = Math.max(0, Math.min(seconds, el.duration || seconds));
    el.currentTime = clamped;
    onSeek(clamped);
  };

  const toggleFullscreen = () => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void el.requestFullscreen();
    }
  };

  const exportSnapshot = () => {
    const el = videoEl();
    if (!el || !nativeWidth || !nativeHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = nativeWidth;
    canvas.height = nativeHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(el, 0, 0, nativeWidth, nativeHeight);

    if ((showRoi || showDetections) && activeEvent) {
      const scaleFactor = Math.max(2, nativeWidth / 320);
      if (showRoi) {
        ctx.strokeStyle = "hsl(199 89% 52%)";
        ctx.lineWidth = scaleFactor;
        for (const roi of activeEvent.rois) ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
      }
      if (showDetections) {
        for (const d of activeEvent.detections) {
          ctx.strokeStyle = d.prohibited ? "hsl(0 84% 60%)" : "hsl(160 84% 39%)";
          ctx.lineWidth = scaleFactor;
          ctx.strokeRect(d.x, d.y, d.w, d.h);
          ctx.fillStyle = ctx.strokeStyle;
          ctx.font = `bold ${Math.max(12, nativeWidth / 40)}px sans-serif`;
          ctx.fillText(`${d.label} ${(d.confidence * 100).toFixed(0)}%`, d.x + 4, Math.max(14, d.y - 4));
        }
      }
    }

    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `snapshot-${formatTimestamp(currentTime).replace(/[:.]/g, "-")}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, "image/png");
  };

  const vb = `0 0 ${nativeWidth || 1} ${nativeHeight || 1}`;
  const hasProhibited = activeEvent?.detections.some((d) => d.prohibited) ?? false;
  const hasConfirmedProhibited =
    activeEvent?.detections.some((d) => d.prohibited && !d.heuristic) ?? false;

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="relative overflow-hidden rounded-xl border border-border bg-black">
        <video
          ref={ref}
          src={src}
          controls
          className="w-full"
          onTimeUpdate={(e) => onTimeUpdate((e.target as HTMLVideoElement).currentTime)}
        />
        {(showRoi || showDetections) && activeEvent ? (
          <svg
            viewBox={vb}
            preserveAspectRatio="xMidYMid meet"
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
            {showRoi
              ? activeEvent.rois.map((roi) => (
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
                ))
              : null}
            {showDetections
              ? activeEvent.detections.map((d) => {
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
                })
              : null}
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
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          onClick={() => jumpToEvent(-1)}
          title="Previous event"
          aria-label="Previous event"
          disabled={events.length === 0}
        >
          <SkipBack className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="icon" onClick={() => stepFrame(-1)} title="Previous frame" aria-label="Previous frame">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="icon" onClick={() => stepFrame(1)} title="Next frame" aria-label="Next frame">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={() => jumpToEvent(1)}
          title="Next event"
          aria-label="Next event"
          disabled={events.length === 0}
        >
          <SkipForward className="h-4 w-4" />
        </Button>

        <Select value={speed} onValueChange={changeSpeed}>
          <SelectTrigger className="h-9 w-[84px]" aria-label="Playback speed">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SPEEDS.map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}x
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <form onSubmit={handleSkip} className="flex items-center gap-1">
          <Input
            value={timeInput}
            onChange={(e) => {
              setTimeInput(e.target.value);
              setTimeError(false);
            }}
            placeholder="mm:ss"
            className={cn("h-9 w-20", timeError && "border-destructive")}
            aria-label="Skip to timestamp"
          />
          <Button type="submit" variant="outline" size="sm">
            Go
          </Button>
        </form>

        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowRoi((s) => !s)}
            className={cn(!showRoi && "text-muted-foreground")}
          >
            {showRoi ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            ROI
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowDetections((s) => !s)}
            className={cn(!showDetections && "text-muted-foreground")}
          >
            {showDetections ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            Objects
          </Button>
          <Button variant="outline" size="icon" onClick={exportSnapshot} title="Export snapshot" aria-label="Export snapshot">
            <Camera className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" onClick={toggleFullscreen} title="Fullscreen" aria-label="Fullscreen">
            <Expand className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
});
