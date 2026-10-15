export type RunMetrics = {
  total_duration_ms: number; agent_latency_ms: number; tool_latency_ms: number;
  tool_call_count: number; llm_call_count: number; retry_count: number;
  handoff_count: number; repeated_transition_count: number; error_count: number;
  input_tokens: number; output_tokens: number; total_tokens: number;
  estimated_cost: number | null; approval_wait_ms: number; path_length: number; step_count: number;
};

export type GraphNode = {
  id: string; span_id: string; parent_span_id: string | null; event_type: string; label: string;
  started_at: string; ended_at: string; duration_ms: number; status: string; agent_name: string | null;
  depth: number; lane: number; is_concurrent: boolean; retry_index: number | null;
  semantic_attributes: Record<string, unknown>;
};

export type GraphEdge = {
  id: string; source: string; target: string;
  type: "parent_child" | "handoff" | "retry" | "repeated_transition";
  metadata: Record<string, unknown>;
};

export type SilverEvent = {
  event_id: string; trace_id: string; span_id: string; parent_span_id: string | null;
  timestamp: string; duration_ms: number; status: string; event_type: string;
  agent_name: string | null; is_late: boolean; is_out_of_order: boolean;
  semantic_attributes: Record<string, unknown>; attributes: Record<string, unknown>;
};

export type RunSummary = {
  run_id: string; trace_id: string; name: string; status: string; started_at: string;
  ended_at: string; materialized_at: string; workflow_name: string | null;
  workflow_version: string | null; environment: string | null;
  organization_id: string | null; project_id: string | null; metrics: RunMetrics;
};

export type RunDetail = RunSummary & {
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  events: SilverEvent[];
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function fetchRuns(signal?: AbortSignal): Promise<RunSummary[]> {
  const response = await fetch(`${API_URL}/api/v1/runs?limit=100`, { signal });
  if (!response.ok) throw new Error(`The runs API returned ${response.status}.`);
  const payload = (await response.json()) as { items: RunSummary[] };
  return payload.items;
}

export async function fetchRun(runId: string, signal?: AbortSignal): Promise<RunDetail> {
  const response = await fetch(`${API_URL}/api/v1/runs/${encodeURIComponent(runId)}`, { signal });
  if (response.status === 404) throw new Error("This run could not be found.");
  if (!response.ok) throw new Error(`The run API returned ${response.status}.`);
  return (await response.json()) as RunDetail;
}

export function formatDuration(milliseconds: number): string {
  if (milliseconds < 1_000) return `${Math.round(milliseconds)} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1_000).toFixed(2)} s`;
  return `${(milliseconds / 60_000).toFixed(1)} min`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit",
  }).format(new Date(value));
}
