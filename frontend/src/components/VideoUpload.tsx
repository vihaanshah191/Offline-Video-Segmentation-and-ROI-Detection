import { useCallback, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, UploadCloud, X } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { useUploadVideo } from "@/hooks/useVideos";
import { cn } from "@/lib/utils";

const ACCEPT = ".mp4,.avi,.mov,.mkv";

interface QueueItem {
  id: string;
  file: File;
  progress: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
}

/** Accepts one or many files: each is uploaded sequentially (the backend
 * takes one file per request) with its own progress row, so one failure
 * doesn't block the rest of a batch. */
export function VideoUpload() {
  const upload = useUploadVideo();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const processingRef = useRef(false);
  // Items waiting to be uploaded. A second `handleFiles` call while a batch
  // is already uploading pushes here instead of starting a second worker —
  // the running loop below drains this on every iteration, so newly dropped
  // files are picked up rather than silently stuck at "pending" forever.
  const pendingRef = useRef<QueueItem[]>([]);

  const processQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;
    while (pendingRef.current.length > 0) {
      const item = pendingRef.current.shift()!;
      setQueue((q) => q.map((x) => (x.id === item.id ? { ...x, status: "uploading" } : x)));
      try {
        await new Promise<void>((resolve, reject) => {
          upload.mutate(
            {
              file: item.file,
              onProgress: (pct) =>
                setQueue((q) => q.map((x) => (x.id === item.id ? { ...x, progress: pct } : x))),
            },
            {
              onSuccess: () => resolve(),
              onError: (err: unknown) => reject(err),
            },
          );
        });
        setQueue((q) => q.map((x) => (x.id === item.id ? { ...x, status: "done", progress: 100 } : x)));
      } catch (err) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Upload failed";
        setQueue((q) => (q.map((x) => (x.id === item.id ? { ...x, status: "error", error: message } : x))));
      }
    }
    processingRef.current = false;
  }, [upload]);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const items: QueueItem[] = Array.from(files).map((file) => ({
        id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
        file,
        progress: 0,
        status: "pending",
      }));
      setQueue((q) => [...q, ...items]);
      pendingRef.current.push(...items);
      void processQueue();
    },
    [processQueue],
  );

  const activeCount = queue.filter((q) => q.status === "pending" || q.status === "uploading").length;

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload video"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border bg-card/50 px-6 py-10 text-center transition-colors hover:border-primary/60 hover:bg-accent/40",
          dragging && "border-primary bg-primary/5",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
          <UploadCloud className="h-7 w-7 text-primary" />
        </div>
        <div>
          <p className="text-sm font-semibold">
            {activeCount > 0 ? `Uploading ${activeCount} more…` : "Drop videos here or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground">
            Supports MP4, AVI, MOV and MKV — select multiple files for a batch upload
          </p>
        </div>
      </div>

      {queue.length > 0 ? (
        <div className="space-y-2 rounded-lg border border-border p-3">
          {queue.map((item) => (
            <div key={item.id} className="flex items-center gap-3 text-sm">
              {item.status === "done" ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : item.status === "error" ? (
                <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
              ) : (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
              )}
              <span className="min-w-0 flex-1 truncate">{item.file.name}</span>
              {item.status === "uploading" || item.status === "pending" ? (
                <Progress value={item.progress} className="w-24" />
              ) : item.status === "error" ? (
                <span className="max-w-[200px] truncate text-xs text-destructive">{item.error}</span>
              ) : (
                <span className="text-xs text-muted-foreground">Uploaded</span>
              )}
              {item.status === "done" || item.status === "error" ? (
                <button
                  aria-label="Dismiss"
                  onClick={() => setQueue((q) => q.filter((x) => x.id !== item.id))}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
