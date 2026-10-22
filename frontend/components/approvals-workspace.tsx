"use client";

import { useState } from "react";

import type { Notice } from "@/components/control-workspace";
import { CopyButton } from "@/components/run-widgets";
import { Icon, type IconName } from "@/components/ui/icon";
import { resolveApproval, type Approval, type Policy } from "@/lib/api";
import { notifyApprovalCountChanged } from "@/lib/project";

type Sort = "newest" | "oldest";

export function ApprovalsPanel({ approvals, policies, loading, setApprovals, notify }: { approvals: Approval[]; policies: Policy[]; loading: boolean; setApprovals: (update: (items: Approval[]) => Approval[]) => void; notify: (notice: Notice) => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("newest");
  const [resolving, setResolving] = useState(false);
  const [now] = useState(() => Date.now());
  const ordered = [...approvals].sort((a, b) => (Date.parse(b.created_at) - Date.parse(a.created_at)) * (sort === "newest" ? 1 : -1));
  const selected = ordered.find((item) => item.id === selectedId) ?? ordered[0];
  const policy = selected?.policy_id ? policies.find((item) => item.id === selected.policy_id) : undefined;

  async function decide(approval: Approval, decision: "approve" | "reject") {
    setResolving(true); notify(null);
    try {
      const result = await resolveApproval(approval.id, decision);
      setApprovals((items) => items.filter((item) => item.id !== result.id));
      setSelectedId(null);
      notify({ tone: "success", text: `${decision === "approve" ? "Approved" : "Rejected"}. Runtime integration: ${result.integration_status}.` });
      notifyApprovalCountChanged();
    } catch (reason) { notify({ tone: "error", text: reason instanceof Error ? reason.message : "Resolution failed." }); }
    finally { setResolving(false); }
  }

  if (loading) return <div className="cw-split" aria-label="Loading approvals"><section className="rd-card"><div className="mini-skeleton-list"><i /><i /><i /></div></section><section className="rd-card"><div className="mini-skeleton-list"><i /><i /></div></section></div>;
  if (approvals.length === 0) return <section className="state-panel compact"><span className="state-icon"><Icon name="check" /></span><h2>No actions are waiting for review</h2><p>A REQUIRE_APPROVAL policy will pause matching side effects here.</p></section>;

  return <div className="cw-split">
    <section className="rd-card cw-inbox">
      <header className="rd-card-heading"><div><h2>Pending approvals <span className="heading-badge heading-badge-count cw-count">{approvals.length}</span></h2><p>Review actions that require human approval based on your policies.</p></div>
        <label className="cw-sort"><span className="sr-only">Sort</span><select onChange={(event) => setSort(event.target.value as Sort)} value={sort}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label></header>
      <ul className="cw-approval-list">{ordered.map((approval) => <li className={selected?.id === approval.id ? "selected" : ""} key={approval.id}>
        <button className="cw-approval-main" onClick={() => setSelectedId(approval.id)} type="button">
          <span className={`approval-item-icon tone-${approvalIcon(approval)}`}><Icon name={approvalIcon(approval)} /></span>
          <span className="cw-approval-text"><strong>{humanize(approval.action_summary)}</strong><small>{[approval.workflow_name && humanize(approval.workflow_name), approval.agent_name, [approval.tool_name, approval.operation].filter(Boolean).join(".")].filter(Boolean).join(" · ") || "Context not recorded"}</small>{approval.confidence !== null && <em>Confidence {approval.confidence.toFixed(2)}</em>}</span>
        </button>
        <div className="cw-approval-side"><time>{relativeTime(approval.created_at, now)}</time>
          <div className="cw-row-actions"><button className="reject" disabled={resolving} onClick={() => decide(approval, "reject")} type="button">Reject</button><button className="approve" disabled={resolving} onClick={() => decide(approval, "approve")} type="button">Approve</button></div></div>
      </li>)}</ul>
    </section>
    {selected && <section className="rd-card cw-detail">
      <header className="rd-card-heading"><div className="cw-detail-title"><span className={`approval-item-icon tone-${approvalIcon(selected)}`}><Icon name={approvalIcon(selected)} /></span><div><h2>{humanize(selected.action_summary)}</h2><span className="risk-label">Consequential action · review before execution</span></div></div><span className="cw-pending-pill">Pending</span></header>
      <dl className="cw-facts">
        <div><dt>Logical run</dt><dd><Identifier label="logical run ID" value={selected.run_id} /></dd></div>
        <div><dt>Workflow</dt><dd>{selected.workflow_name ?? "Not supplied"}</dd></div>
        <div><dt>Agent</dt><dd>{selected.agent_name ?? "Not supplied"}</dd></div>
        <div><dt>Tool / operation</dt><dd>{[selected.tool_name, selected.operation].filter(Boolean).join(" · ") || "Not supplied"}</dd></div>
        <div><dt>Requested</dt><dd>{new Date(selected.created_at).toLocaleString()} · {relativeTime(selected.created_at, now)}</dd></div>
        <div><dt>Expires</dt><dd>{selected.expires_at ? new Date(selected.expires_at).toLocaleString() : "No expiry recorded"}</dd></div>
        <div className="wide"><dt>Control reference</dt><dd><Identifier label="control reference" value={selected.control_reference} fallback="Not supplied" /></dd></div>
      </dl>
      <div className="cw-policy-card"><span className="cw-policy-icon"><Icon name="policy" /></span><div><small>Triggering policy</small><strong>{policy?.name ?? (selected.policy_id ? "Policy not found in this project" : "No policy recorded")}</strong>{policy && <em>{policy.action.replaceAll("_", " ")} · Priority {policy.priority} · {policy.fail_closed ? "fail closed" : "fail open"}</em>}</div></div>
      <div className="approval-reason"><strong>Why review is required</strong><p>{selected.match_reason}</p></div>
      <details className="cw-technical"><summary>Technical details <Icon name="chevron" /></summary>
        <dl><div><dt>Policy revision</dt><dd><Identifier label="policy revision" value={selected.policy_revision} fallback="Not recorded" /></dd></div><div><dt>Sanitized context hash</dt><dd><Identifier label="context hash" value={selected.context_hash} fallback="Not recorded" /></dd></div></dl>
        <p>Sanitized evaluated context</p><pre>{JSON.stringify(selected.proposed_inputs, null, 2)}</pre>
      </details>
      <div className="cw-detail-actions"><button className="cw-reject" disabled={resolving} onClick={() => decide(selected, "reject")} type="button">Reject action</button><button className="cw-approve" disabled={resolving} onClick={() => decide(selected, "approve")} type="button">{resolving ? "Resolving…" : "Approve action"}</button></div>
      <p className="integration-note">Approval records authorization; it does not resume the workflow. Relay retries the queued action manually with the same control reference, and Agent Runtime reuses this approval only when the immutable context still matches.</p>
    </section>}
  </div>;
}

// Long identifiers are shown shortened with a copy button; the full value stays in the tooltip and is what gets copied.
function Identifier({ value, label, fallback = "—" }: { value: string | null; label: string; fallback?: string }) {
  if (!value) return <>{fallback}</>;
  return <span className="cw-id"><code title={value}>{value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value}</code><CopyButton label={label} value={value} /></span>;
}

function humanize(value: string): string { return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function relativeTime(value: string, now: number): string { const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60_000)); if (minutes < 1) return "just now"; if (minutes < 60) return `${minutes}m ago`; const hours = Math.floor(minutes / 60); return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`; }
function approvalIcon(approval: Approval): IconName { const context = `${approval.tool_name ?? ""} ${approval.operation ?? ""} ${approval.action_summary}`.toLowerCase(); if (context.includes("github") || context.includes("code")) return "code"; if (context.includes("notion") || context.includes("database")) return "database"; return "approval"; }
