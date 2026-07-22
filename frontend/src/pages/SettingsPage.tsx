import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Save, Settings as SettingsIcon, ShieldCheck } from "lucide-react";
import axios from "axios";

import { settingsApi } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/hooks/useAuth";
import type { MotionAlgorithm, RuntimeConfigUpdate } from "@/types";

const ALGORITHMS: { value: MotionAlgorithm; label: string }[] = [
  { value: "auto", label: "Auto (recommended)" },
  { value: "mog2", label: "MOG2 background subtraction" },
  { value: "frame_diff", label: "Frame differencing" },
  { value: "optical_flow", label: "Farneback optical flow" },
];

export function SettingsPage() {
  const qc = useQueryClient();
  const { authEnabled, user } = useAuth();
  const canManage = !authEnabled || user?.role === "admin";

  const { data: config, isLoading } = useQuery({
    queryKey: ["runtime-settings"],
    queryFn: settingsApi.get,
  });
  const { data: capabilities } = useQuery({
    queryKey: ["settings-capabilities"],
    queryFn: settingsApi.capabilities,
  });

  const [form, setForm] = useState<RuntimeConfigUpdate>({});
  useEffect(() => {
    if (config) {
      setForm({
        default_motion_algorithm: config.default_motion_algorithm,
        motion_threshold: config.motion_threshold,
        min_motion_area: config.min_motion_area,
        frame_sample_step: config.frame_sample_step,
        yolo_confidence: config.yolo_confidence,
        enable_object_detection: config.enable_object_detection,
      });
    }
  }, [config]);

  const save = useMutation({
    mutationFn: (payload: RuntimeConfigUpdate) => settingsApi.update(payload),
    onSuccess: (data) => {
      qc.setQueryData(["runtime-settings"], data);
    },
  });

  const reset = useMutation({
    mutationFn: settingsApi.reset,
    onSuccess: (data) => {
      qc.setQueryData(["runtime-settings"], data);
    },
  });

  const errorDetail = (err: unknown): string => {
    if (axios.isAxiosError(err)) {
      if (err.response?.status === 403) return "You don't have permission to change settings.";
      return err.response?.data?.detail ?? "Failed to save settings.";
    }
    return "Failed to save settings.";
  };

  if (isLoading || !config) {
    return <div className="text-muted-foreground">Loading settings…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <section>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <SettingsIcon className="h-6 w-6" />
          Settings
        </h1>
        <p className="text-muted-foreground">
          Runtime-editable defaults for new analysis runs. Does not affect analyses already in progress.
        </p>
      </section>

      {!canManage ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <ShieldCheck className="h-4 w-4" />
            Signed in as <strong>{user?.role}</strong> — settings are read-only for this role.
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Analysis defaults</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label>Default motion algorithm</Label>
            <Select
              value={form.default_motion_algorithm ?? config.default_motion_algorithm}
              onValueChange={(v) => setForm((f) => ({ ...f, default_motion_algorithm: v }))}
              disabled={!canManage}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ALGORITHMS.map((a) => (
                  <SelectItem key={a.value} value={a.value}>
                    {a.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Motion sensitivity threshold</Label>
              <span className="font-mono text-xs text-muted-foreground">
                {(form.motion_threshold ?? config.motion_threshold).toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={form.motion_threshold ?? config.motion_threshold}
              onChange={(e) => setForm((f) => ({ ...f, motion_threshold: Number(e.target.value) }))}
              className="w-full accent-primary"
              disabled={!canManage}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Min motion area (px)</Label>
              <Input
                type="number"
                min={1}
                value={form.min_motion_area ?? config.min_motion_area}
                onChange={(e) => setForm((f) => ({ ...f, min_motion_area: Number(e.target.value) }))}
                disabled={!canManage}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Frame sample step</Label>
              <Input
                type="number"
                min={1}
                max={60}
                value={form.frame_sample_step ?? config.frame_sample_step}
                onChange={(e) => setForm((f) => ({ ...f, frame_sample_step: Number(e.target.value) }))}
                disabled={!canManage}
              />
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <Label>Enable object detection by default</Label>
            <Switch
              checked={form.enable_object_detection ?? config.enable_object_detection}
              onCheckedChange={(v) => setForm((f) => ({ ...f, enable_object_detection: v }))}
              disabled={!canManage}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>YOLO confidence threshold</Label>
              <span className="font-mono text-xs text-muted-foreground">
                {(form.yolo_confidence ?? config.yolo_confidence).toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={form.yolo_confidence ?? config.yolo_confidence}
              onChange={(e) => setForm((f) => ({ ...f, yolo_confidence: Number(e.target.value) }))}
              className="w-full accent-primary"
              disabled={!canManage}
            />
          </div>

          {save.isError ? <p className="text-sm text-destructive">{errorDetail(save.error)}</p> : null}
          {save.isSuccess ? <p className="text-sm text-emerald-400">Settings saved.</p> : null}

          {canManage ? (
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => reset.mutate()} disabled={reset.isPending}>
                {reset.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                Reset to defaults
              </Button>
              <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
                {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save
              </Button>
            </div>
          ) : null}

          {config.updated_by ? (
            <p className="text-right text-xs text-muted-foreground">
              Last updated by {config.updated_by} at {new Date(config.updated_at).toLocaleString()}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {capabilities ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Deployment capabilities (read-only)</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Model</p>
              <p className="font-medium">{capabilities.yolo_model}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Device</p>
              <p className="font-medium">{capabilities.yolo_device}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Task backend</p>
              <p className="font-medium">{capabilities.task_backend}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Max upload</p>
              <p className="font-medium">{capabilities.max_upload_mb} MB</p>
            </div>
            <div className="col-span-2">
              <p className="text-xs text-muted-foreground">Allowed extensions</p>
              <p className="font-medium">{capabilities.allowed_extensions.join(", ")}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Authentication</p>
              <p className="font-medium">{capabilities.auth_enabled ? "Enabled" : "Disabled"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Demo mode</p>
              <p className="font-medium">{capabilities.demo_mode_enabled ? "Enabled" : "Disabled"}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
