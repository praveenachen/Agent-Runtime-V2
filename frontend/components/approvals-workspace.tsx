"use client";

import { useEffect, useState } from "react";

import { fetchApprovals, resolveApproval, type Approval } from "@/lib/api";
import { notifyApprovalCountChanged, useProjectId } from "@/lib/project";
import { ProjectScope } from "@/components/project-scope";

export function ApprovalsWorkspace() {
  const { projectId } = useProjectId();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "error">("success");
  const [loadedProject, setLoadedProject] = useState("");
  const [failedProject, setFailedProject] = useState("");
  const [resolving, setResolving] = useState(false);
  const visibleApprovals = loadedProject === projectId ? approvals : [];
  const loading = Boolean(projectId && loadedProject !== projectId && failedProject !== projectId);
  const selected = visibleApprovals.find((item) => item.id === selectedId) ?? visibleApprovals[0];

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    fetchApprovals(projectId, controller.signal).then((items) => { setApprovals(items); setLoadedProject(projectId); setFailedProject(""); }).catch((reason: Error) => { if (reason.name !== "AbortError") { setFailedProject(projectId); setMessageTone("error"); setMessage(reason.message); } });
    return () => controller.abort();
  }, [projectId]);

  async function decide(decision: "approve" | "reject") {
    if (!selected) return;
    setResolving(true); setMessage("");
    try {
      const result = await resolveApproval(selected.id, decision);
      setApprovals((items) => items.filter((item) => item.id !== result.id));
      setSelectedId(null);
      setMessageTone("success"); setMessage(`${decision === "approve" ? "Approved" : "Rejected"}. Runtime integration: ${result.integration_status}.`);
      notifyApprovalCountChanged();
    } catch (reason) { setMessageTone("error"); setMessage(reason instanceof Error ? reason.message : "Resolution failed."); }
    finally { setResolving(false); }
  }

  return <main className="page-stack control-page">
    <header className="page-heading"><div><p className="eyebrow">Human control</p><h1>Approvals</h1><p>Review paused consequential actions without taking over workflow orchestration.</p></div><span className="safety-note">{visibleApprovals.length} pending</span></header>
    <ProjectScope />
    {message && <div className={`control-message ${messageTone}`} role={messageTone === "error" ? "alert" : "status"}>{message}</div>}
    {!projectId ? <div className="state-panel compact"><span className="state-icon">⌁</span><h2>Select a project</h2><p>Approval requests are isolated by project.</p></div> : loading ? <div className="approval-layout" aria-label="Loading approvals"><section className="approval-inbox"><div className="mini-skeleton-list"><i /><i /><i /></div></section><section className="approval-detail"><div className="skeleton-title" /><div className="skeleton-row" /><div className="skeleton-row" /></section></div> : visibleApprovals.length === 0 ? <div className="state-panel"><span className="state-icon">✓</span><h2>No pending approvals</h2><p>Actions requiring review will appear here with sanitized inputs and policy evidence.</p></div> : <div className="approval-layout">
      <section className="approval-inbox"><div className="section-heading"><div><p className="eyebrow">Inbox</p><h2>Pending actions</h2></div></div>{visibleApprovals.map((approval) => <button className={selected?.id === approval.id ? "selected" : ""} key={approval.id} onClick={() => setSelectedId(approval.id)} type="button"><span className="side-effect-mark">!</span><span><strong>{approval.action_summary}</strong><small>{approval.agent_name ?? "Unknown agent"} · {approval.operation ?? "unspecified operation"}</small></span><time>{new Date(approval.created_at).toLocaleTimeString()}</time></button>)}</section>
      {selected && <section className="approval-detail"><div className="approval-title"><div><p className="eyebrow">Proposed action</p><h2>{selected.action_summary}</h2><span className="risk-label">Consequential action · review before execution</span></div><span className="diagnosis-state severity-warning">Pending</span></div><dl><div><dt>Logical run</dt><dd>{selected.run_id}</dd></div><div><dt>Workflow</dt><dd>{selected.workflow_name ?? "Not supplied"}</dd></div><div><dt>Control reference</dt><dd>{selected.control_reference ?? "Not supplied"}</dd></div><div><dt>Expires</dt><dd>{selected.expires_at ? new Date(selected.expires_at).toLocaleString() : "No expiry recorded"}</dd></div><div><dt>Agent</dt><dd>{selected.agent_name ?? "Not supplied"}</dd></div><div><dt>Tool / operation</dt><dd>{[selected.tool_name, selected.operation].filter(Boolean).join(" · ") || "Not supplied"}</dd></div></dl><div className="approval-reason"><strong>Why review is required</strong><p>{selected.match_reason}</p></div><div className="approval-bindings"><span><b>Policy revision</b><code>{selected.policy_revision ?? "Not recorded"}</code></span><span><b>Sanitized context hash</b><code>{selected.context_hash ?? "Not recorded"}</code></span></div><details className="approval-inputs"><summary>Sanitized evaluated context</summary><pre>{JSON.stringify(selected.proposed_inputs, null, 2)}</pre></details><div className="approval-actions"><button className="button-ghost reject" disabled={resolving} onClick={() => decide("reject")} type="button">Reject action</button><button className="button-primary" disabled={resolving} onClick={() => decide("approve")} type="button">{resolving ? "Resolving…" : "Approve action"}</button></div><p className="integration-note">Approval records authorization; it does not resume the workflow. Relay retries the queued action manually with the same control reference, and Agent Runtime reuses this approval only when the immutable context still matches.</p></section>}
    </div>}
  </main>;
}
