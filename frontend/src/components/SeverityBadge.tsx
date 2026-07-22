import { Badge } from "@/components/ui/badge";
import type { Severity } from "@/types";

const MAP: Record<Severity, { label: string; variant: "destructive" | "warning" | "secondary" }> = {
  critical: { label: "Critical", variant: "destructive" },
  warning: { label: "Warning", variant: "warning" },
  normal: { label: "Normal", variant: "secondary" },
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const cfg = MAP[severity] ?? MAP.normal;
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
