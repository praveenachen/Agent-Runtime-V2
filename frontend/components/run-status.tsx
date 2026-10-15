import { Badge } from "@/components/ui/badge";

export function RunStatus({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = normalized === "failed" ? "danger" : normalized === "succeeded" ? "healthy" : "pending";
  return <Badge tone={tone}>{normalized}</Badge>;
}
