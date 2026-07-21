import { useState } from "react";
import { Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAnalyzeVideo } from "@/hooks/useVideos";
import type { MotionAlgorithm } from "@/types";

const ALGORITHMS: { value: MotionAlgorithm; label: string; description: string }[] = [
  { value: "mog2", label: "MOG2 background subtraction", description: "Robust to gradual lighting change" },
  { value: "frame_diff", label: "Frame differencing", description: "Fast and sensitive to any change" },
  { value: "optical_flow", label: "Farneback optical flow", description: "Captures true directional movement" },
];

interface Props {
  videoId: number;
  label?: string;
  variant?: "default" | "outline" | "secondary";
}

export function AnalyzeDialog({ videoId, label = "Analyze", variant = "default" }: Props) {
  const [open, setOpen] = useState(false);
  const [algorithm, setAlgorithm] = useState<MotionAlgorithm>("mog2");
  const [objectDetection, setObjectDetection] = useState(true);
  const analyze = useAnalyzeVideo(videoId);

  const handleSubmit = () => {
    analyze.mutate(
      { motion_algorithm: algorithm, enable_object_detection: objectDetection },
      { onSuccess: () => setOpen(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size="sm">
          <Play className="h-4 w-4" />
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run offline analysis</DialogTitle>
          <DialogDescription>
            Configure the motion algorithm and object detection, then start processing.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Motion algorithm</Label>
            <Select value={algorithm} onValueChange={(v) => setAlgorithm(v as MotionAlgorithm)}>
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
            <p className="text-xs text-muted-foreground">
              {ALGORITHMS.find((a) => a.value === algorithm)?.description}
            </p>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div>
              <Label>Object detection (YOLOv11)</Label>
              <p className="text-xs text-muted-foreground">Detect phones, paper, bags and people.</p>
            </div>
            <Switch checked={objectDetection} onCheckedChange={setObjectDetection} />
          </div>
        </div>

        {analyze.isError ? (
          <p className="text-sm text-destructive">
            {(analyze.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
              "Failed to start analysis"}
          </p>
        ) : null}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button onClick={handleSubmit} disabled={analyze.isPending}>
            {analyze.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Start analysis
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
