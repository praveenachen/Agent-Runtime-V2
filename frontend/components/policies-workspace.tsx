"use client";

import { useEffect, useState } from "react";

import { fetchPolicies, savePolicy, setPolicyEnabled, type Policy, type PolicyAction } from "@/lib/api";
import { useProjectId } from "@/lib/project";
import { ProjectScope } from "@/components/project-scope";

type Draft = {
  name: string; description: string; action: PolicyAction; priority: string;
  enabled: boolean; failClosed: boolean; workflow: string; agent: string; tool: string;
  operation: string; sideEffect: string; replayable: string; confidence: string;
  cost: string; toolCalls: string; retries: string; loops: string;
  allowedOperations: string; disallowedOperations: string;
};

const emptyDraft: Draft = {
  name: "", description: "", action: "REQUIRE_APPROVAL", priority: "100",
  enabled: true, failClosed: true, workflow: "", agent: "", tool: "",
  operation: "", sideEffect: "true", replayable: "", confidence: "0.70",
  cost: "", toolCalls: "", retries: "", loops: "", allowedOperations: "",
  disallowedOperations: "",
};

export function PoliciesWorkspace() {
  const { projectId } = useProjectId();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loadedProject, setLoadedProject] = useState("");
  const [failedProject, setFailedProject] = useState("");
  const [saving, setSaving] = useState(false);
  const visiblePolicies = loadedProject === projectId ? policies : [];
  const loading = Boolean(projectId && loadedProject !== projectId && failedProject !== projectId);

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    fetchPolicies(projectId, controller.signal).then((items) => { setPolicies(items); setLoadedProject(projectId); setFailedProject(""); }).catch((reason: Error) => { if (reason.name !== "AbortError") { setFailedProject(projectId); setError(reason.message); } });
    return () => controller.abort();
  }, [projectId]);

  async function submit() {
    setError(""); setMessage(""); setSaving(true);
    try {
      const saved = await savePolicy(editing, {
        project_id: projectId, name: draft.name, description: draft.description || null,
        enabled: draft.enabled, priority: Number(draft.priority), action: draft.action,
        conditions: conditions(draft), fail_closed: draft.failClosed,
      });
      setPolicies((items) => [...items.filter((item) => item.id !== saved.id), saved].sort((a, b) => b.priority - a.priority)); setLoadedProject(projectId);
      setDraft(emptyDraft); setEditing(null); setMessage(`Policy “${saved.name}” saved.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Policy save failed."); }
    finally { setSaving(false); }
  }

  function edit(policy: Policy) {
    const values = policy.conditions;
    setEditing(policy.id);
    setDraft({
      name: policy.name, description: policy.description ?? "", action: policy.action,
      priority: String(policy.priority), enabled: policy.enabled, failClosed: policy.fail_closed,
      workflow: stringValue(values.workflow_name), agent: stringValue(values.agent_name),
      tool: stringValue(values.tool_name), operation: stringValue(values.operation),
      sideEffect: optionalBoolean(values.side_effect), replayable: optionalBoolean(values.replayable),
      confidence: numberValue(values.confidence_lt), cost: numberValue(values.current_cost_gte),
      toolCalls: numberValue(values.tool_call_count_gte), retries: numberValue(values.retry_count_gte),
      loops: numberValue(values.repeated_transition_count_gte),
      allowedOperations: listValue(values.allowed_operations),
      disallowedOperations: listValue(values.disallowed_operations),
    });
  }

  async function toggle(policy: Policy) {
    setError(""); setMessage("");
    try {
      const saved = await setPolicyEnabled(policy.id, !policy.enabled);
      setPolicies((items) => items.map((item) => item.id === saved.id ? saved : item));
      setMessage(`${saved.name} ${saved.enabled ? "enabled" : "disabled"}.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Policy update failed."); }
  }

  return <main className="page-stack control-page">
    <header className="page-heading"><div><p className="eyebrow">Optional runtime control</p><h1>Policies</h1><p>Readable deterministic rules evaluated by a caller immediately before a consequential action.</p></div><span className="safety-note">No LLM in decision path</span></header>
    <ProjectScope />
    {message && <div className="control-message success" role="status">{message}</div>}
    {error && <div className="control-message error" role="alert">{error}</div>}
    {!projectId ? <div className="state-panel compact"><span className="state-icon">⌁</span><h2>Select a project</h2><p>Enter an existing project UUID to manage its isolated control policies.</p></div> : <div className="policy-layout">
      <section className="policy-list-panel"><div className="section-heading"><div><p className="eyebrow">Evaluation order</p><h2>{visiblePolicies.length} policies</h2></div></div>{loading ? <div className="mini-skeleton-list" aria-label="Loading policies"><i /><i /><i /></div> : visiblePolicies.length ? <div className="policy-list">{visiblePolicies.map((policy) => <article className={!policy.enabled ? "disabled" : ""} key={policy.id}><div><span className={`action-dot action-${policy.action.toLowerCase()}`} /><strong>{policy.name}</strong><small>Priority {policy.priority} · {policy.fail_closed ? "fail closed" : "fail open"}</small></div><p>WHEN {conditionText(policy.conditions)} THEN <b>{policy.action.replaceAll("_", " ")}</b></p><div><button className="button-ghost" onClick={() => edit(policy)} type="button">Edit</button><button className="button-ghost" onClick={() => toggle(policy)} type="button">{policy.enabled ? "Disable" : "Enable"}</button></div></article>)}</div> : <div className="empty-state compact"><strong>No policies yet</strong><p>Create a rule for actions that call Agent Runtime before execution. Unmatched actions are allowed.</p></div>}</section>
      <section className="policy-editor"><div className="section-heading"><div><p className="eyebrow">Rule builder</p><h2>{editing ? "Edit policy" : "Create policy"}</h2></div>{editing && <button className="button-ghost" onClick={() => { setEditing(null); setDraft(emptyDraft); }} type="button">Cancel</button>}</div>
        <div className="form-grid"><Field label="Name"><input value={draft.name} onChange={(event) => update(setDraft, "name", event.target.value)} /></Field><Field label="Action"><select value={draft.action} onChange={(event) => update(setDraft, "action", event.target.value as PolicyAction)}>{["ALLOW", "BLOCK", "PAUSE", "REQUIRE_APPROVAL"].map((value) => <option key={value}>{value}</option>)}</select></Field><Field label="Priority"><input min="0" type="number" value={draft.priority} onChange={(event) => update(setDraft, "priority", event.target.value)} /></Field><Field label="Workflow"><input value={draft.workflow} onChange={(event) => update(setDraft, "workflow", event.target.value)} /></Field><Field label="Agent"><input value={draft.agent} onChange={(event) => update(setDraft, "agent", event.target.value)} /></Field><Field label="Tool / action"><input value={draft.tool} onChange={(event) => update(setDraft, "tool", event.target.value)} /></Field><Field label="Operation"><input value={draft.operation} onChange={(event) => update(setDraft, "operation", event.target.value)} /></Field><Field label="Side effect"><TriState value={draft.sideEffect} onChange={(value) => update(setDraft, "sideEffect", value)} /></Field><Field label="Replayable"><TriState value={draft.replayable} onChange={(value) => update(setDraft, "replayable", value)} /></Field><Field label="Confidence below"><input max="1" min="0" step="0.01" type="number" value={draft.confidence} onChange={(event) => update(setDraft, "confidence", event.target.value)} /></Field><Field label="Current cost ≥"><input min="0" step="0.01" type="number" value={draft.cost} onChange={(event) => update(setDraft, "cost", event.target.value)} /></Field><Field label="Tool calls ≥"><input min="0" type="number" value={draft.toolCalls} onChange={(event) => update(setDraft, "toolCalls", event.target.value)} /></Field><Field label="Retries ≥"><input min="0" type="number" value={draft.retries} onChange={(event) => update(setDraft, "retries", event.target.value)} /></Field><Field label="Repeated transitions ≥"><input min="0" type="number" value={draft.loops} onChange={(event) => update(setDraft, "loops", event.target.value)} /></Field><Field label="Allowed operations"><input placeholder="read, search" value={draft.allowedOperations} onChange={(event) => update(setDraft, "allowedOperations", event.target.value)} /></Field><Field label="Disallowed operations"><input placeholder="delete, transfer" value={draft.disallowedOperations} onChange={(event) => update(setDraft, "disallowedOperations", event.target.value)} /></Field></div>
        <div className="rule-preview"><span>WHEN</span> {conditionText(conditions(draft))} <span>THEN</span> {draft.action.replaceAll("_", " ")}</div>
        <div className="policy-options"><label><input checked={draft.enabled} onChange={(event) => update(setDraft, "enabled", event.target.checked)} type="checkbox" /> Enabled</label><label><input checked={draft.failClosed} onChange={(event) => update(setDraft, "failClosed", event.target.checked)} type="checkbox" /> Fail closed</label></div>
        <button className="button-primary" disabled={!draft.name || !projectId || saving} onClick={submit} type="button">{saving ? "Saving…" : editing ? "Save changes" : "Create policy"}</button>
      </section>
    </div>}
  </main>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="control-field"><span>{label}</span>{children}</label>; }
function TriState({ value, onChange }: { value: string; onChange: (value: string) => void }) { return <select value={value} onChange={(event) => onChange(event.target.value)}><option value="">Any</option><option value="true">True</option><option value="false">False</option></select>; }
function update(setter: React.Dispatch<React.SetStateAction<Draft>>, key: keyof Draft, value: Draft[keyof Draft]) { setter((current) => ({ ...current, [key]: value })); }
function conditions(draft: Draft): Record<string, unknown> { const result: Record<string, unknown> = {}; const strings = { workflow_name: draft.workflow, agent_name: draft.agent, tool_name: draft.tool, operation: draft.operation }; Object.entries(strings).forEach(([key, value]) => { if (value.trim()) result[key] = value.trim(); }); if (draft.sideEffect) result.side_effect = draft.sideEffect === "true"; if (draft.replayable) result.replayable = draft.replayable === "true"; const numbers = { confidence_lt: draft.confidence, current_cost_gte: draft.cost, tool_call_count_gte: draft.toolCalls, retry_count_gte: draft.retries, repeated_transition_count_gte: draft.loops }; Object.entries(numbers).forEach(([key, value]) => { if (value !== "") result[key] = Number(value); }); if (draft.allowedOperations.trim()) result.allowed_operations = csv(draft.allowedOperations); if (draft.disallowedOperations.trim()) result.disallowed_operations = csv(draft.disallowedOperations); return result; }
function conditionText(values: Record<string, unknown>) { const entries = Object.entries(values); return entries.length ? entries.map(([key, value]) => `${key.replaceAll("_", " ")} = ${Array.isArray(value) ? value.join(" | ") : String(value)}`).join(" AND ") : "all actions"; }
function csv(value: string) { return value.split(",").map((item) => item.trim()).filter(Boolean); }
function stringValue(value: unknown) { return typeof value === "string" ? value : ""; }
function numberValue(value: unknown) { return typeof value === "number" ? String(value) : ""; }
function listValue(value: unknown) { return Array.isArray(value) ? value.join(", ") : ""; }
function optionalBoolean(value: unknown) { return typeof value === "boolean" ? String(value) : ""; }
