import { useCallback, useRef, useState } from "react";
import { Loader2, UploadCloud } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { useUploadVideo } from "@/hooks/useVideos";
import { cn } from "@/lib/utils";

const ACCEPT = ".mp4,.avi,.mov,.mkv";

export function VideoUpload() {
  const upload = useUploadVideo();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (!file) return;
      setError(null);
      setProgress(0);
      upload.mutate(
        { file, onProgress: setProgress },
        {
          onError: (err: unknown) => {
            const message =
              (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
              "Upload failed";
            setError(message);
          },
        },
      );
    },
    [upload],
  );

  return (
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
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {upload.isPending ? (
        <>
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm font-medium">Uploading… {progress}%</p>
          <Progress value={progress} className="w-56" />
        </>
      ) : (
        <>
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
            <UploadCloud className="h-7 w-7 text-primary" />
          </div>
          <div>
            <p className="text-sm font-semibold">Drop a video here or click to browse</p>
            <p className="text-xs text-muted-foreground">Supports MP4, AVI, MOV and MKV</p>
          </div>
        </>
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
