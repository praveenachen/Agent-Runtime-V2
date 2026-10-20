"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/icon";
import {
  createReplayRequest,
  fetchReplayCapabilities,
  fetchRuns,
  fetchRuntimeDiff,
  formatDuration,
  type ReplayCapabilities,
  type ReplayMode,
  type ReplayRequest,
  type RunSummary,
  type RuntimeDiff,
} from "@/lib/api";

const modes: Array<{ value: ReplayMode; title: string; copy: string }> = [
  { value: "reexecute_safe_tools", title: "Re-execute safe tools", copy: "Only explicitly replayable read-only calls run again." },
  { value: "reuse_prior_outputs", title: "Reuse prior outputs", copy: "Requires a stored output reference for each tool call." },
  { value: "dry_run_side_effects", title: "Dry-run side effects", copy: "External effects are marked simulated and do not occur." },
];

export function RuntimeCompare() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [original, setOriginal] = useState("");
  const [comparison, setComparison] = useState("");
  const [diff, setDiff] = useState<RuntimeDiff | null>(null);
  const [capabilities, setCapabilities] = useState<ReplayCapabilities | null>(null);
  const [mode, setMode] = useState<ReplayMode>("dry_run_side_effects");
  const [request, setRequest] = useState<ReplayRequest | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [planning, setPlanning] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal).then((items) => {
      setRuns(items);
      const requested = new URLSearchParams(window.location.search).get("original");
      const source = items.some((item) => item.run_id === requested) ? requested! : items[0]?.run_id ?? "";
      setOriginal(source);
      setComparison(items.find((item) => item.run_id !== source)?.run_id ?? "");
    }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!original) return;
    const controller = new AbortController();
    fetchReplayCapabilities(original, controller.signal).then(setCapabilities).catch((reason: Error) => setError(reason.message));
    return () => controller.abort();
  }, [original]);

  useEffect(() => {
    if (!original || !comparison) return;
    const controller = new AbortController();
    fetchRuntimeDiff(original, comparison, controller.signal).then(setDiff).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
    return () => controller.abort();
  }, [original, comparison]);

  function selectOriginal(value: string) {
    setOriginal(value); setDiff(null); setLoading(Boolean(value && comparison)); setRequest(null);
  }

  function selectComparison(value: string) {
    setComparison(value); setDiff(null); setLoading(Boolean(original && value));
  }

  async function planReplay() {
    setPlanning(true); setError(""); setRequest(null);
    try { setRequest(await createReplayRequest(original, mode)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Replay planning failed."); }
    finally { setPlanning(false); }
  }

  return (
    <main className="page-stack compare-page">
      <header className="page-heading">
        <div><p className="eyebrow">Debugging replay</p><h1>Runtime Diff</h1><p>Compare configuration, semantic execution, and recorded outcomes across complete logical runs.</p></div>
        <span className="safety-note"><Icon name="shield" /> Side effects default safe</span>
      </header>

      <section className="compare-selectors" aria-label="Runs to compare">
        <RunSelect label="Original run" value={original} runs={runs} onChange={selectOriginal} />
        <span className="compare-arrow">→</span>
        <RunSelect label="Comparison run" value={comparison} runs={runs} onChange={selectComparison} />
      </section>

      {error && <div className="state-panel compact"><span className="state-icon danger">!</span><h2>Could not load comparison</h2><p>{error}</p></div>}
      {!error && loading && <div className="skeleton-stack"><div className="skeleton-metrics" /><div className="skeleton-graph" /></div>}
      {!error && !loading && runs.length < 2 && <div className="state-panel"><span className="state-icon"><Icon name="compare" /></span><h2>Two completed runs are needed</h2><p>Runtime Diff uses real Gold run records and does not manufacture comparison data.</p></div>}
      {!error && !loading && diff && <DiffView diff={diff} />}

      {original && <section className="replay-workbench">
        <div className="section-heading"><div><p className="eyebrow">Replay planner</p><h2>Choose tool behavior</h2></div><span className="adapter-chip">Adapter: {capabilities?.adapter_id ?? "checking"}</span></div>
        <div className="capability-strip">{capabilities?.capabilities.map((item) => <div className={item.available ? "available" : "unavailable"} key={item.capability}><strong>{label(item.capability)}</strong><span>{item.reason}</span></div>)}</div>
        <div className="replay-mode-grid">{modes.map((item) => <label className={mode === item.value ? "selected" : ""} key={item.value}><input checked={mode === item.value} name="replay-mode" onChange={() => setMode(item.value)} type="radio" /><span><strong>{item.title}</strong><small>{item.copy}</small></span></label>)}</div>
        <div className="replay-submit"><p>Planning records decisions in PostgreSQL. Execution starts only when a configured adapter accepts the plan.</p><button className="button-secondary" disabled={planning} onClick={planReplay} type="button">{planning ? "Planning…" : "Create replay plan"}</button></div>
        {request && <div className={`replay-result ${request.status === "blocked" ? "blocked" : ""}`}><strong>{label(request.status)}</strong><span>{request.status_reason ?? (request.external_reference ? `Submitted as ${request.external_reference}.` : "Plan persisted; no execution was claimed.")}</span><small>{request.id}</small></div>}
      </section>}
    </main>
  );
}

function RunSelect({ label: title, value, runs, onChange }: { label: string; value: string; runs: RunSummary[]; onChange: (value: string) => void }) {
  const selected = runs.find((run) => run.run_id === value);
  return <label className="run-selector"><span>{title}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">Select a run</option>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.name} · {run.workflow_version ? `v${run.workflow_version}` : "version not recorded"} · {run.status}</option>)}</select><small>{(selected?.external_run_id ?? value) || "No run selected"}</small></label>;
}

function DiffView({ diff }: { diff: RuntimeDiff }) {
  return <div className="diff-stack">
    <section className="diff-card"><div className="section-heading"><div><p className="eyebrow">Configuration</p><h2>What changed</h2></div></div><div className="config-diff">{diff.configuration.map((item) => <div className={item.changed ? "changed" : ""} key={item.field}><strong>{label(item.field)}</strong><span>{display(item.original)}</span><i>→</i><span>{display(item.comparison)}</span></div>)}</div></section>
    <section className="diff-card"><div className="section-heading"><div><p className="eyebrow">Execution</p><h2>Semantic paths and structural changes</h2><p className="section-copy">Added and removed steps describe recorded behavior, independent of service-level trace boundaries.</p></div><div className="delta-pills"><span>Retries {signed(diff.execution.retry_delta)}</span><span>Loops {signed(diff.execution.repeated_transition_delta)}</span></div></div><div className="path-compare"><Path title="Original" values={diff.execution.original_sequence} tone="removed" /><Path title="Comparison" values={diff.execution.comparison_sequence} tone="added" /></div><div className="structural-deltas"><Delta title="Added steps" values={diff.execution.added_steps} /><Delta title="Removed steps" values={diff.execution.removed_steps} /><Delta title="Added tools" values={diff.execution.added_tools} /><Delta title="Removed tools" values={diff.execution.removed_tools} /><Delta title="Added handoffs" values={diff.execution.added_handoffs} /><Delta title="Removed handoffs" values={diff.execution.removed_handoffs} /></div></section>
    <section className="diff-card"><div className="section-heading"><div><p className="eyebrow">Outcomes</p><h2>Recorded metric movement</h2><p className="section-copy">A dash means the producer did not emit the metric; it does not mean zero.</p></div></div><div className="outcome-grid">{diff.outcomes.map((item) => <div className={`outcome ${item.assessment}`} key={item.metric}><span>{label(item.metric)}</span><strong>{metric(item.metric, item.original)} → {metric(item.metric, item.comparison)}</strong><small>{item.assessment}{item.percent_change === null ? "" : ` · ${signed(item.percent_change)}%`}</small></div>)}</div></section>
  </div>;
}

function Path({ title, values, tone }: { title: string; values: string[]; tone: string }) { return <div className="runtime-path"><strong>{title}</strong><div>{values.length ? values.map((value, index) => <span className={tone} key={`${value}-${index}`}>{value}</span>) : <small>No executable steps</small>}</div></div>; }
function Delta({ title, values }: { title: string; values: Record<string, number> }) { const entries = Object.entries(values); return <div><strong>{title}</strong>{entries.length ? entries.map(([name, count]) => <span key={name}>{name} ×{count}</span>) : <small>None</small>}</div>; }
function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function display(value: unknown) { return value === null || value === undefined ? "Not recorded" : String(value); }
function signed(value: number) { return `${value > 0 ? "+" : ""}${Number.isInteger(value) ? value : value.toFixed(1)}`; }
function metric(name: string, value: number | string | null) { if (value === null) return "—"; if (name === "duration_ms" && typeof value === "number") return formatDuration(value); if (name === "estimated_cost" && typeof value === "number") return `$${value.toFixed(4)}`; return String(value); }
