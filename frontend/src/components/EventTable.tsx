import { useState } from "react";
import { ArrowUpDown, Download, Search, ShieldAlert } from "lucide-react";

import { videosApi, type EventQuery } from "@/api/videos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

type SortField = NonNullable<EventQuery["sort_by"]>;

interface Props {
  videoId: number;
  onSeek: (time: number) => void;
}

export function EventTable({ videoId, onSeek }: Props) {
  const [search, setSearch] = useState("");
  const [prohibitedOnly, setProhibitedOnly] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>("start_time");
  const [order, setOrder] = useState<"asc" | "desc">("asc");

  const query: EventQuery = {
    search: search || undefined,
    prohibited_only: prohibitedOnly,
    sort_by: sortBy,
    order,
  };
  const { data: events = [], isLoading } = useEvents(videoId, query);

  const toggleSort = (field: SortField) => {
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
          <CardTitle className="text-base">Event log</CardTitle>
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
              placeholder="Search by object (phone, paper, person…)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          <Button
            variant={prohibitedOnly ? "destructive" : "outline"}
            size="sm"
            onClick={() => setProhibitedOnly((p) => !p)}
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
              <TableHead>ID</TableHead>
              <SortHead label="Start" field="start_time" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Duration" field="duration" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Motion" field="motion_score" sortBy={sortBy} order={order} onSort={toggleSort} />
              <SortHead label="Confidence" field="confidence" sortBy={sortBy} order={order} onSort={toggleSort} />
              <TableHead>Objects</TableHead>
              <TableHead>ROIs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  Loading events…
                </TableCell>
              </TableRow>
            ) : events.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  No events match your filters.
                </TableCell>
              </TableRow>
            ) : (
              events.map((event) => {
                const objects = event.objects.split(",").filter(Boolean);
                const hasProhibited = event.detections.some((d) => d.prohibited);
                return (
                  <TableRow
                    key={event.id}
                    className="cursor-pointer"
                    onClick={() => onSeek(event.start_time)}
                  >
                    <TableCell className="font-mono text-xs">#{event.id}</TableCell>
                    <TableCell className="font-mono text-xs">{formatTimestamp(event.start_time)}</TableCell>
                    <TableCell>{formatDuration(event.duration)}</TableCell>
                    <TableCell>
                      <MotionBar value={event.motion_score} />
                    </TableCell>
                    <TableCell>{(event.confidence * 100).toFixed(0)}%</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {objects.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          objects.map((o) => (
                            <Badge
                              key={o}
                              variant={hasProhibited && ["phone", "paper", "book"].includes(o) ? "destructive" : "secondary"}
                            >
                              {o}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{event.rois.length}</TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
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
  const pct = Math.min(100, value * 100 * 8); // scaled for visibility
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-muted-foreground">{value.toFixed(3)}</span>
    </div>
  );
}
