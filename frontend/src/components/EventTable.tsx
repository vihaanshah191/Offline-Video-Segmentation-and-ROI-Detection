import { useState } from "react";
import {
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileJson,
  Flame,
  HelpCircle,
  ImageOff,
  Search,
  ShieldAlert,
} from "lucide-react";

import { resolveStorageUrl } from "@/api/client";
import { videosApi, type EventQuery } from "@/api/videos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SeverityBadge } from "@/components/SeverityBadge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEvents } from "@/hooks/useVideos";
import { cn, formatDuration, formatTimestamp } from "@/lib/utils";
import type { EventRecord } from "@/types";

type SortField = NonNullable<EventQuery["sort_by"]>;
const PAGE_SIZE = 25;

interface Props {
  videoId: number;
  onSeek: (time: number) => void;
}

export function EventTable({ videoId, onSeek }: Props) {
  const [search, setSearch] = useState("");
  const [prohibitedOnly, setProhibitedOnly] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>("start_time");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(0);

  const query: EventQuery = {
    search: search || undefined,
    prohibited_only: prohibitedOnly,
    sort_by: sortBy,
    order,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  const { data, isLoading } = useEvents(videoId, query);
  const events = data?.items ?? [];
  const total = data?.pageInfo.total ?? 0;
  const hasNextPage = (page + 1) * PAGE_SIZE < total;

  const exportEvent = (event: EventRecord) => {
    const blob = new Blob([JSON.stringify(event, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `video${videoId}_event${event.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleSort = (field: SortField) => {
    setPage(0);
    if (sortBy === field) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setOrder("asc");
    }
  };

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">Event log{total > 0 ? ` (${total})` : ""}</CardTitle>
          <Button asChild size="sm" variant="outline">
            <a href={videosApi.csvUrl(videoId)} download>
              <Download className="h-4 w-4" />
              Export CSV
            </a>
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search by object (phone, book, person…)"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              className="pl-8"
            />
          </div>
          <Button
            variant={prohibitedOnly ? "destructive" : "outline"}
            size="sm"
            onClick={() => {
              setProhibitedOnly((p) => !p);
              setPage(0);
            }}
          >
            <ShieldAlert className="h-4 w-4" />
            Prohibited only
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Thumb</TableHead>
              <TableHead>ID</TableHead>
              <SortHead label="Start" field="start_time" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Duration" field="duration" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Motion" field="motion_score" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Confidence" field="confidence" sortBy={sortBy} order={order} onSort={toggleSort} />
              <TableHead>Severity</TableHead>
              <TableHead>Objects</TableHead>
              <TableHead>ROIs</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
                  Loading events…
                </TableCell>
              </TableRow>
            ) : events.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
                  No events match your filters.
                </TableCell>
              </TableRow>
            ) : (
              events.map((event) => {
                const objects = event.objects.split(",").filter(Boolean);
                const heuristicLabels = new Set(
                  event.detections.filter((d) => d.heuristic).map((d) => d.label),
                );
                const prohibitedLabels = new Set(
                  event.detections.filter((d) => d.prohibited).map((d) => d.label),
                );
                const thumbUrl = resolveStorageUrl(event.thumbnail_url);
                return (
                  <TableRow
                    key={event.id}
                    className="cursor-pointer"
                    onClick={() => onSeek(event.start_time)}
                  >
                    <TableCell>
                      {thumbUrl ? (
                        <img
                          src={thumbUrl}
                          alt={`Event #${event.id} thumbnail`}
                          className="h-10 w-14 rounded object-cover"
                        />
                      ) : (
                        <div className="flex h-10 w-14 items-center justify-center rounded bg-muted">
                          <ImageOff className="h-4 w-4 text-muted-foreground" />
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">#{event.id}</TableCell>
                    <TableCell className="font-mono text-xs">{formatTimestamp(event.start_time)}</TableCell>
                    <TableCell>{formatDuration(event.duration)}</TableCell>
                    <TableCell>
                      <MotionBar value={event.motion_score} />
                    </TableCell>
                    <TableCell>{(event.confidence * 100).toFixed(0)}%</TableCell>
                    <TableCell>
                      <SeverityBadge severity={event.severity} />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {objects.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          objects.map((o) => (
                            <Badge
                              key={o}
                              variant={prohibitedLabels.has(o) ? "destructive" : "secondary"}
                              className="gap-1"
                              title={
                                heuristicLabels.has(o)
                                  ? "Heuristic signal: this model has no direct class for the " +
                                    "underlying concept and is using a related, imperfect proxy. " +
                                    "Treat as a hint, not confirmation."
                                  : undefined
                              }
                            >
                              {o}
                              {heuristicLabels.has(o) && <HelpCircle className="h-3 w-3 opacity-70" />}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{event.rois.length}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        {event.clip_url ? (
                          <Button asChild variant="ghost" size="icon" title="Download clip">
                            <a href={videosApi.clipDownloadUrl(videoId, event.id)} download>
                              <Download className="h-4 w-4" />
                            </a>
                          </Button>
                        ) : null}
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Export event as JSON"
                          onClick={() => exportEvent(event)}
                        >
                          <FileJson className="h-4 w-4" />
                        </Button>
                        {event.heatmap_url ? (
                          <Button asChild variant="ghost" size="icon" title="View event heatmap">
                            <a href={resolveStorageUrl(event.heatmap_url)} target="_blank" rel="noreferrer">
                              <Flame className="h-4 w-4 text-amber-400" />
                            </a>
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {total > PAGE_SIZE ? (
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={!hasNextPage} onClick={() => setPage((p) => p + 1)}>
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SortHead({
  label,
  field,
  sortBy,
  order,
  onSort,
}: {
  label: string;
  field: SortField;
  sortBy: SortField;
  order: "asc" | "desc";
  onSort: (f: SortField) => void;
}) {
  const active = sortBy === field;
  return (
    <TableHead>
      <button
        className={cn("flex items-center gap-1 hover:text-foreground", active && "text-foreground")}
        onClick={() => onSort(field)}
      >
        {label}
        <ArrowUpDown className={cn("h-3 w-3", active && order === "desc" && "rotate-180")} />
      </button>
    </TableHead>
  );
}

function MotionBar({ value }: { value: number }) {
  const pct = Math.min(100, value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-muted-foreground">{value.toFixed(3)}</span>
    </div>
  );
}
