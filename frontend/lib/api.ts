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

export type BaselineScope = {
  workflow_name: string;
  environment: string;
  workflow_version: string | null;
  prompt_version: string | null;
  model: string | null;
};

export type BaselineComparison = {
  metric: string;
  current_value: number;
  median: number;
  p90: number;
  deviation_from_median: number;
  threshold: number;
  sample_size: number;
  confidence: number;
  confidence_label: string;
  baseline_scope: BaselineScope;
};

export type EvidenceItem = {
  evidence_id: string;
  anomaly_type: string;
  detector_type: "rule" | "statistical";
  severity: "critical" | "high" | "warning" | "info";
  observed_fact: string;
  metric_evidence: Record<string, number | string | null>;
  graph_evidence: string[];
  baseline_comparison: BaselineComparison | null;
  affected_node_ids: string[];
  inferred_cause: string | null;
  recommendation: string | null;
};

export type Diagnosis = {
  diagnosis_id: string;
  run_id: string;
  generated_at: string;
  status: "anomalies_detected" | "no_anomalies";
  provider: string;
  observed_facts: string[];
  impact: string;
  inferred_causes: Array<{
    statement: string;
    confidence: string;
    supporting_evidence_ids: string[];
    is_inference: true;
  }>;
  suggested_investigations: string[];
  evidence_sufficient: boolean;
  evidence: {
    items: EvidenceItem[];
    baseline_coverage: Array<{
      metric: string;
      sample_size: number;
      confidence: number;
      confidence_label: string;
      baseline_scope: BaselineScope;
    }>;
  };
};

export type ReplayCapability = "compare_only" | "full_rerun" | "checkpoint_replay";
export type ReplayMode = "reexecute_safe_tools" | "reuse_prior_outputs" | "dry_run_side_effects";

export type ReplayCapabilities = {
  run_id: string;
  adapter_id: string;
  capabilities: Array<{ capability: ReplayCapability; available: boolean; reason: string }>;
  checkpoints: Array<{ checkpoint_id: string; timestamp: string; state_reference: string | null }>;
};

export type RuntimeDiff = {
  original_run_id: string;
  comparison_run_id: string;
  configuration: Array<{ field: string; original: unknown; comparison: unknown; changed: boolean }>;
  execution: {
    original_sequence: string[]; comparison_sequence: string[];
    added_steps: Record<string, number>; removed_steps: Record<string, number>;
    added_tools: Record<string, number>; removed_tools: Record<string, number>;
    added_handoffs: Record<string, number>; removed_handoffs: Record<string, number>;
    retry_delta: number; repeated_transition_delta: number;
  };
  outcomes: Array<{
    metric: string; original: number | string | null; comparison: number | string | null;
    delta: number | null; percent_change: number | null;
    assessment: "improved" | "regressed" | "changed" | "unchanged";
  }>;
};

export type ReplayRequest = {
  id: string; status: string; resolved_capability: ReplayCapability;
  status_reason: string | null; external_reference: string | null;
  plan: { fallback_used: boolean; decisions: Array<{ label: string; action: string; reason: string; simulated: boolean }> };
};

export type PolicyAction = "ALLOW" | "BLOCK" | "PAUSE" | "REQUIRE_APPROVAL";
export type Policy = {
  id: string; project_id: string; name: string; description: string | null;
  enabled: boolean; priority: number; action: PolicyAction;
  conditions: Record<string, unknown>; fail_closed: boolean;
  created_at: string; updated_at: string;
};

export type Approval = {
  id: string; project_id: string; run_id: string; policy_id: string | null;
  state: "pending" | "approved" | "rejected" | "expired";
  action_summary: string; workflow_name: string | null; agent_name: string | null;
  tool_name: string | null; operation: string | null; confidence: number | null;
  proposed_inputs: Record<string, unknown>; match_reason: string;
  reviewer_reference: string | null; resolved_at: string | null;
  integration_reference: string | null; created_at: string; updated_at: string;
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

export async function fetchDiagnosis(runId: string, signal?: AbortSignal): Promise<Diagnosis> {
  const response = await fetch(
    `${API_URL}/api/v1/runs/${encodeURIComponent(runId)}/diagnosis`,
    { signal },
  );
  if (!response.ok) throw new Error(`Diagnosis returned ${response.status}.`);
  return (await response.json()) as Diagnosis;
}

export async function fetchReplayCapabilities(runId: string, signal?: AbortSignal): Promise<ReplayCapabilities> {
  const response = await fetch(`${API_URL}/api/v1/runs/${encodeURIComponent(runId)}/replay-capabilities`, { signal });
  if (!response.ok) throw new Error(`Replay capabilities returned ${response.status}.`);
  return (await response.json()) as ReplayCapabilities;
}

export async function fetchRuntimeDiff(original: string, comparison: string, signal?: AbortSignal): Promise<RuntimeDiff> {
  const query = new URLSearchParams({ original_run_id: original, comparison_run_id: comparison });
  const response = await fetch(`${API_URL}/api/v1/runtime-diff?${query}`, { signal });
  if (!response.ok) throw new Error(`Runtime Diff returned ${response.status}.`);
  return (await response.json()) as RuntimeDiff;
}

export async function createReplayRequest(sourceRunId: string, mode: ReplayMode): Promise<ReplayRequest> {
  const response = await fetch(`${API_URL}/api/v1/replays`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_run_id: sourceRunId, mode, capability: "full_rerun" }),
  });
  if (!response.ok) throw new Error(`Replay planning returned ${response.status}.`);
  return (await response.json()) as ReplayRequest;
}

export async function fetchPolicies(projectId: string, signal?: AbortSignal): Promise<Policy[]> {
  const response = await fetch(`${API_URL}/api/v1/policies?project_id=${encodeURIComponent(projectId)}`, { signal });
  if (!response.ok) throw new Error(`Policies returned ${response.status}.`);
  return ((await response.json()) as { items: Policy[] }).items;
}

export async function savePolicy(
  policyId: string | null,
  payload: Omit<Policy, "id" | "created_at" | "updated_at">,
): Promise<Policy> {
  const response = await fetch(`${API_URL}/api/v1/policies${policyId ? `/${policyId}` : ""}`, {
    method: policyId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? `Policy save returned ${response.status}.`);
  return (await response.json()) as Policy;
}

export async function setPolicyEnabled(policyId: string, enabled: boolean): Promise<Policy> {
  const response = await fetch(`${API_URL}/api/v1/policies/${policyId}/enabled`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw new Error(`Policy update returned ${response.status}.`);
  return (await response.json()) as Policy;
}

export async function fetchApprovals(projectId: string, signal?: AbortSignal): Promise<Approval[]> {
  const response = await fetch(`${API_URL}/api/v1/approvals?project_id=${encodeURIComponent(projectId)}&state=pending`, { signal });
  if (!response.ok) throw new Error(`Approvals returned ${response.status}.`);
  return ((await response.json()) as { items: Approval[] }).items;
}

export async function fetchPendingApprovalCount(projectId: string, signal?: AbortSignal): Promise<number> {
  const response = await fetch(`${API_URL}/api/v1/approvals/pending/count?project_id=${encodeURIComponent(projectId)}`, { signal });
  if (!response.ok) return 0;
  return ((await response.json()) as { count: number }).count;
}

export async function resolveApproval(
  approvalId: string, decision: "approve" | "reject",
): Promise<Approval & { idempotent: boolean; integration_status: string }> {
  const response = await fetch(`${API_URL}/api/v1/approvals/${approvalId}/${decision}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer_reference: "local-developer" }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? `Approval returned ${response.status}.`);
  return await response.json();
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
