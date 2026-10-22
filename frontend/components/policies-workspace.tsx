"use client";

import { useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import type { Notice } from "@/components/control-workspace";
import { Icon } from "@/components/ui/icon";
import { savePolicy, setPolicyEnabled, type Policy, type PolicyAction } from "@/lib/api";

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
  operation: "", sideEffect: "", replayable: "", confidence: "",
  cost: "", toolCalls: "", retries: "", loops: "", allowedOperations: "",
  disallowedOperations: "",
};

export function PoliciesPanel({ policies, projectId, loading, newSignal, setPolicies, notify }: { policies: Policy[]; projectId: string; loading: boolean; newSignal: number; setPolicies: (update: (items: Policy[]) => Policy[]) => void; notify: (notice: Notice) => void }) {
  const [selectedId, setSelectedId] = useState<string | null | undefined>(undefined); // undefined = first policy, null = new policy
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [handledSignal, setHandledSignal] = useState(newSignal);
  const ordered = [...policies].sort((a, b) => b.priority - a.priority);
  const activeId = selectedId === undefined ? ordered[0]?.id ?? null : selectedId;
  const active = ordered.find((policy) => policy.id === activeId);
  // Draft mirrors the active policy; track which policy it was loaded from so first load and selection stay in sync.
  const [draftSource, setDraftSource] = useState<string | null | undefined>(undefined);
  if (newSignal !== handledSignal) { setHandledSignal(newSignal); setSelectedId(null); setDraft(emptyDraft); setDraftSource(null); }
  else if (!loading && draftSource === undefined && activeId !== null && active) { setDraftSource(activeId); setDraft(draftFrom(active)); }

  function choose(policy: Policy) { setSelectedId(policy.id); setDraftSource(policy.id); setDraft(draftFrom(policy)); notify(null); }
  function discard() { if (active) { setDraft(draftFrom(active)); setDraftSource(active.id); } else { setDraft(emptyDraft); } notify(null); }

  async function submit() {
    notify(null); setSaving(true);
    try {
      const saved = await savePolicy(active ? active.id : null, {
        project_id: projectId, name: draft.name, description: draft.description || null,
        enabled: draft.enabled, priority: Number(draft.priority), action: draft.action,
        conditions: conditions(draft), fail_closed: draft.failClosed,
      });
      setPolicies((items) => [...items.filter((item) => item.id !== saved.id), saved]);
      setSelectedId(saved.id); setDraftSource(saved.id); setDraft(draftFrom(saved));
      notify({ tone: "success", text: `Policy “${saved.name}” saved.` });
    } catch (reason) { notify({ tone: "error", text: reason instanceof Error ? reason.message : "Policy save failed." }); }
    finally { setSaving(false); }
  }

  async function toggle(policy: Policy) {
    notify(null);
    try {
      const saved = await setPolicyEnabled(policy.id, !policy.enabled);
      setPolicies((items) => items.map((item) => item.id === saved.id ? saved : item));
      if (activeId === saved.id) setDraft((current) => ({ ...current, enabled: saved.enabled }));
      notify({ tone: "success", text: `${saved.name} ${saved.enabled ? "enabled" : "disabled"}.` });
    } catch (reason) { notify({ tone: "error", text: reason instanceof Error ? reason.message : "Policy update failed." }); }
  }

  function useProviderWriteGuardrail() {
    setSelectedId(null); setDraftSource(null);
    setDraft({ ...emptyDraft, name: "Review provider writes", action: "REQUIRE_APPROVAL", priority: "10", sideEffect: "true", failClosed: true });
  }

  if (loading) return <div className="cw-split" aria-label="Loading policies"><section className="rd-card"><div className="mini-skeleton-list"><i /><i /><i /></div></section><section className="rd-card"><div className="mini-skeleton-list"><i /><i /></div></section></div>;

  const creating = !active;
  const ruleLines = Object.entries(conditions(draft)).map(([key, value]) => `${key} = ${Array.isArray(value) ? value.join(" | ") : String(value)}`);
  return <div className="cw-split cw-policy-split">
    <section className="rd-card cw-library">
      <header className="rd-card-heading"><div><h2>Policy library <span className="heading-badge heading-badge-count cw-count neutral">{ordered.length}</span></h2><p>Deterministic rules evaluated in priority order before a consequential action. No LLM in the decision path.</p></div></header>
      {ordered.length ? <ul className="cw-policy-list">{ordered.map((policy) => <li className={`${activeId === policy.id ? "selected" : ""} ${policy.enabled ? "" : "is-disabled"}`} key={policy.id}>
        <button className="cw-policy-main" onClick={() => choose(policy)} type="button">
          <span className={`cw-policy-glyph action-${policy.action.toLowerCase()}`}><Icon name="policy" /></span>
          <span className="cw-policy-text"><strong>{policy.name}</strong><small>{policy.action.replaceAll("_", " ")} · Priority {policy.priority} · {policy.fail_closed ? "fail closed" : "fail open"}</small><code>WHEN {conditionText(policy.conditions)}</code></span>
        </button>
        <div className="cw-policy-side"><span className={`cw-state ${policy.enabled ? "on" : "off"}`}><i />{policy.enabled ? "Active" : "Disabled"}</span><button className="cw-ghost" onClick={() => toggle(policy)} type="button">{policy.enabled ? "Disable" : "Enable"}</button></div>
      </li>)}</ul> : <div className="empty-state compact"><strong>No policies yet</strong><p>Create a rule for actions that call Agent Runtime before execution. Unmatched actions are allowed.</p><button className="button-secondary" onClick={useProviderWriteGuardrail} type="button">Use provider-write guardrail</button></div>}
    </section>

    <section className="rd-card cw-editor">
      <header className="rd-card-heading"><div><h2>{creating ? "New policy" : `Policy: ${active.name}`}</h2><p>{creating ? "Define when approvals, pauses or blocks apply." : (active.description ?? "Edit this policy’s conditions and behavior.")}</p></div>{!creating && <span className={`cw-state ${active.enabled ? "on" : "off"}`}><i />{active.enabled ? "Active" : "Disabled"}</span>}</header>
      <div className="cw-editor-body">
        <h3>Rule builder</h3>
        <div className="cw-code" aria-label="Live rule preview"><ol>{(ruleLines.length ? ruleLines : ["all actions"]).map((line, index) => <li key={line}><span className="ln">{index + 1}</span><span className={index === 0 ? "kw when" : "kw and"}>{index === 0 ? "WHEN" : "AND"}</span><code>{line}</code></li>)}<li><span className="ln">{Math.max(ruleLines.length, 1) + 1}</span><span className="kw then">THEN</span><code className="act">{draft.action}</code></li></ol></div>
        <div className="cw-form">
          <Field label="Policy name" wide><input value={draft.name} onChange={(event) => update(setDraft, "name", event.target.value)} /></Field>
          <Field label="Description" wide><textarea rows={2} value={draft.description} onChange={(event) => update(setDraft, "description", event.target.value)} /></Field>
          <Field label="Action"><select value={draft.action} onChange={(event) => update(setDraft, "action", event.target.value as PolicyAction)}>{["ALLOW", "BLOCK", "PAUSE", "REQUIRE_APPROVAL"].map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="Priority"><input min="0" type="number" value={draft.priority} onChange={(event) => update(setDraft, "priority", event.target.value)} /></Field>
          <Field label="Workflow"><input value={draft.workflow} onChange={(event) => update(setDraft, "workflow", event.target.value)} /></Field>
          <Field label="Agent"><input value={draft.agent} onChange={(event) => update(setDraft, "agent", event.target.value)} /></Field>
          <Field label="Tool / action"><input value={draft.tool} onChange={(event) => update(setDraft, "tool", event.target.value)} /></Field>
          <Field label="Operation"><input value={draft.operation} onChange={(event) => update(setDraft, "operation", event.target.value)} /></Field>
          <Field label="Side effect"><TriState value={draft.sideEffect} onChange={(value) => update(setDraft, "sideEffect", value)} /></Field>
          <Field label="Replayable"><TriState value={draft.replayable} onChange={(value) => update(setDraft, "replayable", value)} /></Field>
          <Field label="Confidence below"><input max="1" min="0" step="0.01" type="number" value={draft.confidence} onChange={(event) => update(setDraft, "confidence", event.target.value)} /></Field>
          <Field label="Current cost ≥"><input min="0" step="0.01" type="number" value={draft.cost} onChange={(event) => update(setDraft, "cost", event.target.value)} /></Field>
          <Field label="Tool calls ≥"><input min="0" type="number" value={draft.toolCalls} onChange={(event) => update(setDraft, "toolCalls", event.target.value)} /></Field>
          <Field label="Retries ≥"><input min="0" type="number" value={draft.retries} onChange={(event) => update(setDraft, "retries", event.target.value)} /></Field>
          <Field label="Repeated transitions ≥"><input min="0" type="number" value={draft.loops} onChange={(event) => update(setDraft, "loops", event.target.value)} /></Field>
          <Field label="Allowed operations"><input placeholder="read, search" value={draft.allowedOperations} onChange={(event) => update(setDraft, "allowedOperations", event.target.value)} /></Field>
          <Field label="Disallowed operations"><input placeholder="delete, transfer" value={draft.disallowedOperations} onChange={(event) => update(setDraft, "disallowedOperations", event.target.value)} /></Field>
        </div>
        <h3>Default behavior</h3>
        <div className="cw-choice">
          <button aria-pressed={draft.failClosed} className={draft.failClosed ? "active" : ""} onClick={() => update(setDraft, "failClosed", true)} type="button"><Icon name="shield" /><span><strong>Fail closed</strong><small>Block and require approval if the policy cannot be evaluated</small></span></button>
          <button aria-pressed={!draft.failClosed} className={!draft.failClosed ? "active" : ""} onClick={() => update(setDraft, "failClosed", false)} type="button"><Icon name="arrow" /><span><strong>Fail open</strong><small>Allow the action if the policy cannot be evaluated</small></span></button>
        </div>
        <label className="cw-switch"><input checked={draft.enabled} onChange={(event) => update(setDraft, "enabled", event.target.checked)} type="checkbox" /><span><strong>Enabled</strong><small>Disabled policies are kept but never evaluated</small></span></label>
      </div>
      <footer className="cw-editor-footer"><button className="cw-ghost" disabled={saving} onClick={discard} type="button">Discard changes</button><button className="cw-save" disabled={!draft.name || !projectId || saving} onClick={submit} type="button">{saving ? "Saving…" : creating ? "Create policy" : "Save policy"}</button></footer>
    </section>
  </div>;
}

function draftFrom(policy: Policy): Draft {
  const values = policy.conditions;
  return {
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
  };
}

function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) { return <label className={`control-field ${wide ? "wide" : ""}`}><span>{label}</span>{children}</label>; }
function TriState({ value, onChange }: { value: string; onChange: (value: string) => void }) { return <select value={value} onChange={(event) => onChange(event.target.value)}><option value="">Any</option><option value="true">True</option><option value="false">False</option></select>; }
function update(setter: Dispatch<SetStateAction<Draft>>, key: keyof Draft, value: Draft[keyof Draft]) { setter((current) => ({ ...current, [key]: value })); }
function conditions(draft: Draft): Record<string, unknown> { const result: Record<string, unknown> = {}; const strings = { workflow_name: draft.workflow, agent_name: draft.agent, tool_name: draft.tool, operation: draft.operation }; Object.entries(strings).forEach(([key, value]) => { if (value.trim()) result[key] = value.trim(); }); if (draft.sideEffect) result.side_effect = draft.sideEffect === "true"; if (draft.replayable) result.replayable = draft.replayable === "true"; const numbers = { confidence_lt: draft.confidence, current_cost_gte: draft.cost, tool_call_count_gte: draft.toolCalls, retry_count_gte: draft.retries, repeated_transition_count_gte: draft.loops }; Object.entries(numbers).forEach(([key, value]) => { if (value !== "") result[key] = Number(value); }); if (draft.allowedOperations.trim()) result.allowed_operations = csv(draft.allowedOperations); if (draft.disallowedOperations.trim()) result.disallowed_operations = csv(draft.disallowedOperations); return result; }
function conditionText(values: Record<string, unknown>) { const entries = Object.entries(values); return entries.length ? entries.map(([key, value]) => `${key} = ${Array.isArray(value) ? value.join(" | ") : String(value)}`).join(" AND ") : "all actions"; }
function csv(value: string) { return value.split(",").map((item) => item.trim()).filter(Boolean); }
function stringValue(value: unknown) { return typeof value === "string" ? value : ""; }
function numberValue(value: unknown) { return typeof value === "number" ? String(value) : ""; }
function listValue(value: unknown) { return Array.isArray(value) ? value.join(", ") : ""; }
function optionalBoolean(value: unknown) { return typeof value === "boolean" ? String(value) : ""; }
