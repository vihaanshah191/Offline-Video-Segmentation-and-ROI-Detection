import { Cpu, MemoryStick, Server, Zap } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SystemInfo } from "@/types";

function Meter({ label, percent }: { label: string; percent: number | null }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{percent === null ? "—" : `${percent.toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${Math.min(100, Math.max(0, percent ?? 0))}%` }}
        />
      </div>
    </div>
  );
}

/** Live model/device info and CPU/memory/GPU resource usage for the dashboard. */
export function SystemPanel({ system }: { system: SystemInfo | undefined }) {
  if (!system) return null;
  const r = system.resources;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">System</CardTitle>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Server className="h-3.5 w-3.5" />
          {system.task_backend} backend
        </span>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Model</p>
            <p className="truncate font-medium" title={system.yolo_model}>
              {system.yolo_model}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Device</p>
            <p className="flex items-center gap-1 font-medium">
              <Zap className="h-3.5 w-3.5" />
              {system.cuda ? r.gpu_name || "CUDA" : "CPU"}
            </p>
          </div>
        </div>

        <Meter label="CPU" percent={r.cpu_percent} />
        <Meter label="Memory" percent={r.memory_percent} />
        {r.memory_used_mb !== null && r.memory_total_mb !== null ? (
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <MemoryStick className="h-3.5 w-3.5" />
            {(r.memory_used_mb / 1024).toFixed(1)} / {(r.memory_total_mb / 1024).toFixed(1)} GB
          </p>
        ) : null}

        {system.cuda && r.gpu_memory_used_mb !== null && r.gpu_memory_total_mb !== null ? (
          <>
            <Meter
              label="GPU memory"
              percent={(r.gpu_memory_used_mb / Math.max(1, r.gpu_memory_total_mb)) * 100}
            />
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Cpu className="h-3.5 w-3.5" />
              {r.gpu_memory_used_mb.toFixed(0)} / {r.gpu_memory_total_mb.toFixed(0)} MB
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
