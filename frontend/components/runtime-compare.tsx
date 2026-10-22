"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { typeVisual } from "@/components/run-graph";
import { RunStatus } from "@/components/run-status";
import { MicroBars, compactId, humanize } from "@/components/run-widgets";
import { Icon, type IconName } from "@/components/ui/icon";
import {
  createReplayRequest,
  fetchReplayCapabilities,
  fetchRun,
  fetchRuntimeDiff,
  formatDuration,
  type GraphNode,
  type ReplayCapabilities,
  type ReplayMode,
  type ReplayRequest,
  type RunDetail,
  type RunSummary,
  type RuntimeDiff,
} from "@/lib/api";
import { useProjectDiscovery } from "@/lib/project";
import { runDisplayName } from "@/lib/run-display";

const modes: Array<{ value: ReplayMode; title: string; copy: string; needs?: "full_rerun" }> = [
  { value: "reexecute_safe_tools", title: "Re-execute safe tools", copy: "Only explicitly replayable read-only calls run again.", needs: "full_rerun" },
  { value: "reuse_prior_outputs", title: "Reuse prior outputs", copy: "Requires a stored output reference for each tool call.", needs: "full_rerun" },
  { value: "dry_run_side_effects", title: "Dry-run side effects", copy: "External effects are marked simulated and do not occur." },
];

const startFormat = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
type Keyed<T> = { key: string; value?: T; error?: string } | null;

export function RuntimeCompare() {
  const { projectId, runs: allRuns, loading: runsLoading, error: runsError } = useProjectDiscovery();
  const runs = useMemo(() => (allRuns ?? []).filter((run) => !projectId || run.project_id === projectId).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)), [allRuns, projectId]);
  const [requested] = useState(() => typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("original") ?? "");
  const [picked, setPicked] = useState<{ original?: string; comparison?: string }>({});
  const defaults = useMemo(() => pickPair(runs, requested), [runs, requested]);
  const original = picked.original ?? defaults.original; const comparison = picked.comparison ?? defaults.comparison;

  const [diffResult, setDiffResult] = useState<Keyed<RuntimeDiff>>(null);
  const [capsResult, setCapsResult] = useState<Keyed<ReplayCapabilities>>(null);
  const [details, setDetails] = useState<Record<string, RunDetail>>({});
  const [mode, setMode] = useState<ReplayMode>("dry_run_side_effects");
  const [request, setRequest] = useState<ReplayRequest | null>(null);
  const [planError, setPlanError] = useState("");
  const [planning, setPlanning] = useState(false);
  const [onlyDifferences, setOnlyDifferences] = useState(false);

  const diffKey = `${original}|${comparison}`;
  useEffect(() => {
    if (!original || !comparison) return;
    const controller = new AbortController();
    fetchRuntimeDiff(original, comparison, controller.signal).then((value) => setDiffResult({ key: diffKey, value })).catch((reason: Error) => { if (reason.name !== "AbortError") setDiffResult({ key: diffKey, error: reason.message }); });
    return () => controller.abort();
  }, [original, comparison, diffKey]);
  useEffect(() => {
    if (!original) return;
    const controller = new AbortController();
    fetchReplayCapabilities(original, controller.signal).then((value) => setCapsResult({ key: original, value })).catch((reason: Error) => { if (reason.name !== "AbortError") setCapsResult({ key: original, error: reason.message }); });
    return () => controller.abort();
  }, [original]);
  useEffect(() => {
    const controller = new AbortController();
    [original, comparison].filter((id) => id).forEach((id) => fetchRun(id, controller.signal).then((value) => setDetails((current) => ({ ...current, [id]: value }))).catch(() => undefined));
    return () => controller.abort();
  }, [original, comparison]);

  const diff = diffResult?.key === diffKey ? diffResult.value ?? null : null;
  const diffError = diffResult?.key === diffKey ? diffResult.error : undefined;
  const capabilities = capsResult?.key === original ? capsResult.value ?? null : null;
  const diffLoading = Boolean(original && comparison) && diffResult?.key !== diffKey;
  const originalRun = details[original]; const comparisonRun = details[comparison];
  const summaryByRun = (id: string) => runs.find((run) => run.run_id === id);
  const fullRerun = capabilities?.capabilities.find((item) => item.capability === "full_rerun");
  const modeSupported = (item: (typeof modes)[number]) => !item.needs || fullRerun?.available === true;

  async function planReplay() {
    setPlanning(true); setPlanError(""); setRequest(null);
    try { setRequest(await createReplayRequest(original, mode)); }
    catch (reason) { setPlanError(reason instanceof Error ? reason.message : "Replay planning failed."); }
    finally { setPlanning(false); }
  }
  const swap = () => { setPicked({ original: comparison, comparison: original }); setRequest(null); };

  return <main className="page-stack overview-page compare-page cmp-page">
    <header className="page-heading"><div><h1>Compare runs</h1><p className="muted">Compare an original run with a replay to understand behavioral changes and performance.</p></div><span className="safety-note"><Icon name="shield" /> Side effects default safe</span></header>
    {(runsError || diffError) && <div className="state-panel compact"><span className="state-icon danger">!</span><h2>Could not load comparison</h2><p>{runsError || diffError}</p></div>}
    {!runsError && !runsLoading && runs.length < 2 && <div className="state-panel"><span className="state-icon"><Icon name="compare" /></span><h2>Two completed runs are needed</h2><p>Runtime Diff uses real run records and does not manufacture comparison data.</p></div>}
    {!runsError && runs.length >= 2 && <div className="cmp-layout">
      <div className="cmp-main">
        <section className="cmp-runs" aria-label="Runs to compare">
          <RunCard onChange={(value) => { setPicked({ ...picked, original: value, comparison }); setRequest(null); }} role="original" run={summaryByRun(original)} runs={runs} value={original} />
          <button aria-label="Swap runs" className="cmp-swap" onClick={swap} type="button"><Icon name="compare" /></button>
          <RunCard onChange={(value) => setPicked({ ...picked, original, comparison: value })} role="comparison" run={summaryByRun(comparison)} runs={runs} value={comparison} />
        </section>
        {diffLoading && <div className="skeleton-stack"><div className="skeleton-metrics" /><div className="skeleton-graph" /></div>}
        {diff && <DiffBody comparisonRun={comparisonRun} diff={diff} onlyDifferences={onlyDifferences} originalRun={originalRun} setOnlyDifferences={setOnlyDifferences} />}
      </div>
      <aside className="cmp-side">
        <section className="rd-card cmp-replay">
          <header className="rd-card-heading"><div><h2>Replay options</h2><p>Configure how the replay should run.</p></div><span className="adapter-chip">{capabilities?.adapter_id ?? "Checking adapter"}</span></header>
          <div className="cmp-modes">{modes.map((item) => { const supported = modeSupported(item); return <label className={`${mode === item.value ? "selected" : ""} ${supported ? "" : "disabled"}`} key={item.value} title={supported ? undefined : fullRerun?.reason}><input checked={mode === item.value} disabled={!supported} name="replay-mode" onChange={() => setMode(item.value)} type="radio" /><span><strong>{item.title}</strong><small>{supported ? item.copy : `Unavailable: ${fullRerun?.reason ?? "checking adapter capabilities"}`}</small></span></label>; })}</div>
          <button className="cmp-plan" disabled={planning || !original} onClick={planReplay} type="button"><Icon name="play" /> {planning ? "Planning…" : "Create replay plan"}</button>
          <p className="cmp-note">Planning persists a safety-reviewed request. Execution starts only when a configured adapter accepts it.</p>
          {planError && <div className="control-message error" role="alert">{planError}</div>}
          {request && <div className={`replay-result ${request.status === "blocked" ? "blocked" : ""}`}><strong>{humanize(request.status)}</strong><span>{request.status_reason ?? (request.external_reference ? `Submitted as ${request.external_reference}.` : "Plan persisted; no execution was claimed.")}</span><small>{request.id}</small></div>}
        </section>
        {diff && <section className="rd-card cmp-summary">
          <header className="rd-card-heading"><h2>Replay summary</h2></header>
          <dl>{replaySummary(diff, mode, original, capabilities).map(([key, value]) => <div key={key}><dt>{key}</dt><dd title={value}>{value}</dd></div>)}</dl>
          <div className="cmp-behavior"><h3><Icon name="spark" /> Behavioral summary</h3><p>{behavioralSummary(diff)}</p></div>
        </section>}
      </aside>
    </div>}
  </main>;
}

function pickPair(runs: RunSummary[], requested: string): { original: string; comparison: string } {
  const byWorkflow = new Map<string, RunSummary[]>();
  runs.forEach((run) => { if (run.workflow_name) byWorkflow.set(run.workflow_name, [...(byWorkflow.get(run.workflow_name) ?? []), run]); });
  if (requested && runs.some((run) => run.run_id === requested)) return { original: requested, comparison: runs.find((run) => run.run_id !== requested)?.run_id ?? "" };
  // Prefer the most recent real version pair of one workflow whose versions end in vN (e.g. v1 vs v2).
  const candidates: Array<{ original: string; comparison: string; recency: number }> = [];
  for (const group of byWorkflow.values()) {
    const numbered = [...new Set(group.map((run) => String(run.workflow_version ?? "")))].map((version) => ({ version, n: Number(/v(\d+)$/i.exec(version)?.[1] ?? NaN) })).filter((item) => Number.isFinite(item.n)).sort((x, y) => x.n - y.n);
    if (numbered.length >= 2) {
      const first = group.find((run) => String(run.workflow_version) === numbered[0].version); const last = group.find((run) => String(run.workflow_version) === numbered[numbered.length - 1].version);
      if (first && last) candidates.push({ original: first.run_id, comparison: last.run_id, recency: Math.max(Date.parse(first.started_at), Date.parse(last.started_at)) });
    }
  }
  if (candidates.length) { const best = candidates.sort((x, y) => y.recency - x.recency)[0]; return { original: best.original, comparison: best.comparison }; }
  return { original: runs[0]?.run_id ?? "", comparison: runs[1]?.run_id ?? "" };
}

function RunCard({ role, run, runs, value, onChange }: { role: "original" | "comparison"; run?: RunSummary; runs: RunSummary[]; value: string; onChange: (value: string) => void }) {
  const title = run ? (run.workflow_name ? humanize(run.workflow_name) : runDisplayName(run)) : "Select a run";
  const meta = run ? [startFormat.format(Date.parse(run.started_at)), [run.workflow_name && humanize(run.workflow_name), run.workflow_version && versionLabel(run.workflow_version)].filter(Boolean).join(" ")].filter(Boolean).join(" • ") : "No run selected";
  return <article className={`cmp-run-card ${role}`}>
    <span className="cmp-run-icon"><Icon name={role === "original" ? "bolt" : "play"} /></span>
    <div className="cmp-run-body">
      <small>{role === "original" ? "Original run" : "Comparison run"}</small>
      {run ? <Link href={`/runs/${run.run_id}`} title={`Open ${run.external_run_id ?? run.run_id}`}><strong>{title}</strong></Link> : <strong>{title}</strong>}
      <span>{meta}</span>
    </div>
    <div className="cmp-run-tags">{run && <RunStatus status={run.status} />}<span className={`cmp-role ${role}`}>{role === "original" ? "Original" : "Comparison"}</span></div>
    <label className="cmp-change"><span>Change run <Icon name="chevron" /></span><select aria-label={`${role} run`} onChange={(event) => onChange(event.target.value)} value={value}>{runs.map((item) => <option key={item.run_id} value={item.run_id}>{humanize(item.workflow_name ?? runDisplayName(item))} · {item.workflow_version ? versionLabel(item.workflow_version) : "no version"} · {startFormat.format(Date.parse(item.started_at))}</option>)}</select></label>
  </article>;
}

const CONFIG_ORDER = ["prompt_version", "workflow_version", "model", "environment", "config_version", "git_commit", "tool_versions"];

// Real recorded fields only: every changed field, then recorded-but-unchanged ones (in a fixed order) to fill a balanced row of up to 4.
function configTiles(diff: RuntimeDiff) {
  const recorded = (item: RuntimeDiff["configuration"][number]) => item.changed || (display(item.original) !== "—" && display(item.comparison) !== "—");
  const sorted = [...diff.configuration].filter(recorded).sort((a, b) => CONFIG_ORDER.indexOf(a.field) - CONFIG_ORDER.indexOf(b.field));
  const changed = sorted.filter((item) => item.changed); const still = sorted.filter((item) => !item.changed && item.field !== "workflow_name");
  const picked = [...changed, ...still].slice(0, 4);
  return picked.sort((a, b) => CONFIG_ORDER.indexOf(a.field) - CONFIG_ORDER.indexOf(b.field));
}

function DiffBody({ diff, originalRun, comparisonRun, onlyDifferences, setOnlyDifferences }: { diff: RuntimeDiff; originalRun?: RunDetail; comparisonRun?: RunDetail; onlyDifferences: boolean; setOnlyDifferences: (value: boolean) => void }) {
  const changedCount = diff.configuration.filter((item) => item.changed).length;
  const tiles = configTiles(diff);
  const cards = outcomeCards(diff, originalRun, comparisonRun);
  const columns = useMemo(() => alignSequences(diff.execution.original_sequence, diff.execution.comparison_sequence), [diff]);
  const nodesA = orderedNodes(originalRun); const nodesB = orderedNodes(comparisonRun);
  const tableColumns = useMemo(() => alignSequences(nodesA.map(stepKey), nodesB.map(stepKey)), [nodesA, nodesB]);
  return <>
    <section className="rd-card cmp-config"><header className="rd-card-heading"><h2>Configuration differences</h2><span className="rd-count">{changedCount} changed</span></header>
      {tiles.length ? <div className="cmp-config-grid" style={{ gridTemplateColumns: `repeat(${tiles.length}, minmax(0, 1fr))` }}>{tiles.map((item) => <div className={item.changed ? "changed" : ""} key={item.field}><small><Icon name={configIcon(item.field)} /> {humanize(item.field)}</small>
        {item.changed ? <p><span className="old" title={display(item.original)}>{display(item.original)}</span><i>→</i><span className="new" title={display(item.comparison)}>{display(item.comparison)}</span></p> : <p><span className="old" title={display(item.comparison)}>{display(item.comparison)}</span><em>No change</em></p>}</div>)}</div> : <p className="cmp-empty">No recorded configuration values to compare.</p>}</section>
    <section className="cmp-outcomes" aria-label="Outcome metrics">{cards.map((card, index) => <article className={`cmp-outcome ${card.assessment}`} key={card.label}>
      <header><span className={`cmp-outcome-icon tone-${card.tone}`}><Icon name={card.icon} /></span><strong>{card.label}</strong></header>
      <div className="cmp-values"><div><b>{card.original}</b><small>original</small></div><i>→</i><div><b className="after">{card.comparison}</b><small>comparison</small></div></div>
      <footer><span>{card.delta}</span><MicroBars seed={index * 4 + 3} /></footer></article>)}</section>
    <section className="rd-card cmp-paths"><header className="rd-card-heading"><div><h2>Execution path</h2><p>Recorded steps in aligned columns; removed steps keep their slot so later steps line up.</p></div>
      <div className="rd-legend"><span><i className="tool" /> Tool call</span><span><i className="llm" /> LLM call</span><span><i className="decision" /> Decision / approval</span><span className="cmp-key removed">Removed</span><span className="cmp-key added">Added</span></div></header>
      <div className="cmp-path-pair">
        <PathPanel columns={columns} detail={originalRun} side="a" title="Original" values={diff.execution.original_sequence} />
        <PathPanel columns={columns} detail={comparisonRun} side="b" title="Comparison" values={diff.execution.comparison_sequence} />
      </div></section>
    <section className="rd-card cmp-traces"><header className="rd-card-heading"><div><h2>Traces comparison</h2><p>Recorded steps, aligned by position. Dashes mark steps the other run does not have.</p></div>
      <label className="cmp-toggle"><input checked={onlyDifferences} onChange={(event) => setOnlyDifferences(event.target.checked)} type="checkbox" /><span /> Show only differences</label></header>
      <div className="cmp-trace-pair"><StepTable columns={tableColumns} detail={originalRun} nodes={nodesA} only={onlyDifferences} side="a" title="Original run" /><StepTable columns={tableColumns} detail={comparisonRun} nodes={nodesB} only={onlyDifferences} side="b" title="Comparison run" /></div></section>
  </>;
}

type Card = { icon: IconName; tone: string; label: string; original: string; comparison: string; assessment: string; delta: string };

function outcomeCards(diff: RuntimeDiff, original?: RunDetail, comparison?: RunDetail): Card[] {
  const find = (name: string) => diff.outcomes.find((item) => item.metric === name);
  const cards: Card[] = []; const push = (card: Card | null) => { if (card) cards.push(card); };
  const numeric = (name: string, icon: IconName, tone: string, label: string, format: (value: number) => string, words: [string, string]): Card | null => {
    const item = find(name); if (!item) return null;
    const delta = item.delta === null || item.delta === 0 ? "No change" : `${item.delta < 0 ? "↓" : "↑"} ${item.percent_change !== null ? `${Math.abs(item.percent_change).toFixed(0)}% ` : `${format(Math.abs(item.delta))} `}${item.delta < 0 ? words[0] : words[1]}`;
    return { icon, tone, label, original: item.original === null ? "—" : format(Number(item.original)), comparison: item.comparison === null ? "—" : format(Number(item.comparison)), assessment: item.assessment, delta };
  };
  push(numeric("duration_ms", "bolt", "purple", "Total latency", formatDuration, ["faster", "slower"]));
  push(numeric("tool_calls", "tool", "blue", "Tool calls", String, ["fewer", "more"]));
  push(numeric("retries", "activity", "purple", "Retries", String, ["fewer", "more"]));
  const loops = original && comparison ? { a: original.metrics.repeated_transition_count, b: comparison.metrics.repeated_transition_count } : null;
  if (loops) { const d = diff.execution.repeated_transition_delta; push({ icon: "compare", tone: "amber", label: "Repeated transitions", original: String(loops.a), comparison: String(loops.b), assessment: d < 0 ? "improved" : d > 0 ? "regressed" : "unchanged", delta: d === 0 ? "No change" : `${d < 0 ? "↓" : "↑"} ${Math.abs(d)} ${d < 0 ? "fewer" : "more"}` }); }
  for (const [name, label, icon, tone, format] of [["estimated_cost", "Total cost", "database", "amber", (value: number) => `$${value.toFixed(4)}`], ["total_tokens", "Total tokens", "layers", "blue", (value: number) => value.toLocaleString()]] as Array<[string, string, IconName, string, (value: number) => string]>) {
    const item = find(name); if (item && item.original !== null && item.comparison !== null) push(numeric(name, icon, tone, label, format, ["lower", "higher"]));
  }
  const status = find("status");
  if (status) { const same = status.original === status.comparison; push({ icon: "checkCircle", tone: "green", label: "Outcome", original: humanize(String(status.original ?? "—")), comparison: humanize(String(status.comparison ?? "—")), assessment: status.assessment, delta: same ? "Same outcome" : `Changed to ${humanize(String(status.comparison))}` }); }
  return cards;
}

function versionLabel(version: string | number): string { const text = String(version); return /^\d/.test(text) ? `v${text}` : text; }

function configIcon(field: string): IconName { return field.includes("prompt") ? "book" : field.includes("model") ? "spark" : field.includes("workflow") ? "workflow" : field.includes("environment") ? "layers" : "settings"; }

function stepKey(node: GraphNode) { return `${node.event_type}:${node.label}`; }
function orderedNodes(detail?: RunDetail): GraphNode[] { return (detail?.graph.nodes ?? []).filter((node) => node.event_type.toUpperCase() !== "RUN").sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)); }

type Column = { a: number | null; b: number | null; kind: "match" | "removed" | "added" | "replaced" };

// Longest-common-subsequence alignment of two recorded sequences into shared columns. A step only one run has keeps its
// slot (the other side shows a placeholder), so every later step stays vertically aligned.
function alignSequences(a: string[], b: string[]): Column[] {
  const n = a.length; const m = b.length; const table = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
  const columns: Column[] = []; let pendingA: number[] = []; let pendingB: number[] = [];
  const flush = () => { const total = Math.max(pendingA.length, pendingB.length); for (let t = 0; t < total; t += 1) { const ai = pendingA[t] ?? null; const bi = pendingB[t] ?? null; columns.push({ a: ai, b: bi, kind: ai !== null && bi !== null ? "replaced" : ai !== null ? "removed" : "added" }); } pendingA = []; pendingB = []; };
  let i = 0; let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { flush(); columns.push({ a: i, b: j, kind: "match" }); i += 1; j += 1; }
    else if (j >= m || (i < n && table[i + 1][j] >= table[i][j + 1])) { pendingA.push(i); i += 1; }
    else { pendingB.push(j); j += 1; }
  }
  flush(); return columns;
}

const TYPE_LABELS: Record<string, string> = { LLM_CALL: "LLM", TOOL_CALL: "Tool", AGENT_STEP: "Agent", DECISION: "Decision", APPROVAL: "Approval", ERROR: "Error", HANDOFF: "Handoff" };
function shortLabel(value: string) { const [type, ...rest] = value.split(":"); const name = rest.join(":"); return !name || humanize(type.toLowerCase()) === name || name === TYPE_LABELS[type] ? TYPE_LABELS[type] ?? humanize(type.toLowerCase()) : name; }

function PathPanel({ title, values, side, columns, detail }: { title: string; values: string[]; side: "a" | "b"; columns: Column[]; detail?: RunDetail }) {
  const tone = side === "a" ? "removed" : "added";
  // Map sequence positions to recorded nodes (same execution order) so repeated-transition evidence lands on the right steps.
  const order = orderedNodes(detail); const aligned = Boolean(detail) && order.length === values.length;
  const position = new Map(order.map((node, index) => [node.id, index]));
  const links = aligned ? (detail?.graph.edges ?? []).filter((edge) => edge.type === "repeated_transition").flatMap((edge) => { const from = position.get(edge.source); const to = position.get(edge.target); return from !== undefined && to !== undefined ? [[from, to] as const] : []; }) : [];
  const inLoop = new Set(links.flatMap(([from, to]) => [from, to]));
  // One loop outline only: the widest contiguous run of repeated-evidence columns.
  const groups: Array<{ start: number; len: number; transitions: number }> = []; let runStart = -1;
  columns.forEach((column, index) => {
    const slot = side === "a" ? column.a : column.b; const active = slot !== null && inLoop.has(slot);
    if (active && runStart < 0) runStart = index;
    if ((!active || index === columns.length - 1) && runStart >= 0) {
      const end = active ? index : index - 1; const slots = new Set(columns.slice(runStart, end + 1).map((item) => (side === "a" ? item.a : item.b)));
      groups.push({ start: runStart, len: end - runStart + 1, transitions: links.filter(([from, to]) => slots.has(from) && slots.has(to)).length });
      runStart = -1;
    }
  });
  const loop = groups.sort((x, y) => y.len - x.len)[0];
  const metrics = detail?.metrics;
  return <div className={`cmp-path ${tone}`}>
    <header><span className={`cmp-role ${side === "a" ? "original" : "comparison"}`}>{title}</span>{metrics && <small>{formatDuration(metrics.total_duration_ms)} · {metrics.tool_call_count} tool calls · {metrics.retry_count} retries</small>}</header>
    {columns.length === 0 ? <p className="cmp-empty">No executable steps</p> : <div className="cmp-rail">
      {columns.map((column, index) => {
        const slot = side === "a" ? column.a : column.b; const last = index === columns.length - 1;
        if (slot === null) return <div className="cmp-col" key={index}><div className="cmp-node skipped"><span className="cmp-node-dot"><Icon name="x" /></span><small>{side === "b" ? "Skipped" : "—"}</small></div>{!last && <i className="cmp-arrow muted" />}</div>;
        const value = values[slot]; const [type] = value.split(":"); const visual = typeVisual(type); const changed = column.kind !== "match";
        return <div className="cmp-col" key={index}><div className={`cmp-node tone-${visual.tone} ${changed ? tone : ""}`} title={value}><span className="cmp-node-dot"><Icon name={visual.icon} /></span><small>{shortLabel(value)}</small></div>{!last && <i className="cmp-arrow" />}</div>;
      })}
      {loop && <div className="cmp-loop-overlay" style={{ left: `calc(${(loop.start / columns.length) * 100}% + 7px)`, width: `calc(${(loop.len / columns.length) * 100}% - 14px)` }}><span className="cmp-loop-badge">↺ Repeated {Math.max(loop.transitions, 1)}×</span></div>}
    </div>}
  </div>;
}

function StepTable({ title, nodes, columns, side, only, detail }: { title: string; nodes: GraphNode[]; columns: Column[]; side: "a" | "b"; only: boolean; detail?: RunDetail }) {
  const tone = side === "a" ? "removed" : "added";
  const rows = columns.filter((column) => !only || column.kind !== "match");
  return <div className="cmp-steps"><header><strong>{title}</strong><span>{detail ? `${nodes.length} step${nodes.length === 1 ? "" : "s"} · ${formatDuration(detail.metrics.total_duration_ms)}` : "Loading…"}</span></header>
    <table><thead><tr><th>#</th><th>Step</th><th>Type</th><th>Duration</th><th aria-label="Indicator" /></tr></thead><tbody>{rows.length ? rows.map((column, rowIndex) => {
      const slot = side === "a" ? column.a : column.b;
      if (slot === null) return <tr className="placeholder" key={rowIndex}><td>—</td><td colSpan={4}>{side === "b" ? "Not in comparison run" : "Not in original run"}</td></tr>;
      const node = nodes[slot]; const changed = column.kind !== "match"; const error = node.event_type.toUpperCase() === "ERROR" || node.status.toLowerCase() === "error";
      const tool = [node.semantic_attributes["agent.runtime.tool.name"], node.semantic_attributes["agent.runtime.tool.operation"]].filter((value) => typeof value === "string" && value).join(".");
      return <tr className={`${changed ? tone : ""} ${error ? "is-error" : ""}`} key={rowIndex}><td>{slot + 1}</td><td>{node.label}</td><td>{humanize(node.event_type.toLowerCase())}{tool ? ` · ${tool}` : ""}</td><td>{formatDuration(node.duration_ms)}</td><td>{error ? <span className="cmp-flag error"><Icon name="alert" /></span> : node.retry_index !== null ? <span className="cmp-flag retry">retry {node.retry_index}</span> : changed ? <span className={`cmp-flag ${tone}`}>{tone === "removed" ? "removed" : "added"}</span> : null}</td></tr>;
    }) : <tr><td className="cmp-empty" colSpan={5}>{only ? "No differing steps." : "No recorded steps."}</td></tr>}</tbody></table></div>;
}

function replaySummary(diff: RuntimeDiff, mode: ReplayMode, original: string, capabilities: ReplayCapabilities | null): Array<[string, string]> {
  const config = (field: string) => diff.configuration.find((item) => item.field === field)?.comparison;
  const rows: Array<[string, string]> = [["Mode", modes.find((item) => item.value === mode)?.title ?? mode], ["Source run", compactId(original)], ["Adapter", capabilities?.adapter_id ?? "—"]];
  [["Prompt version", "prompt_version"], ["Workflow version", "workflow_version"], ["Model", "model"], ["Environment", "environment"]].forEach(([label, field]) => { const value = config(field); if (value !== null && value !== undefined && value !== "") rows.push([label, display(value)]); });
  return rows;
}

function behavioralSummary(diff: RuntimeDiff): string {
  const total = (values: Record<string, number>) => Object.values(values).reduce((sum, value) => sum + value, 0);
  const clauses: string[] = []; const e = diff.execution;
  const removed = total(e.removed_steps); const added = total(e.added_steps);
  if (removed) clauses.push(`removed ${removed} step${removed === 1 ? "" : "s"}`);
  if (added) clauses.push(`added ${added} step${added === 1 ? "" : "s"}`);
  if (total(e.removed_tools) || total(e.added_tools)) clauses.push(`changed tool usage (${total(e.added_tools)} added, ${total(e.removed_tools)} removed)`);
  const tools = diff.outcomes.find((item) => item.metric === "tool_calls"); if (tools && tools.delta) clauses.push(`${tools.delta < 0 ? "reduced" : "increased"} tool calls from ${tools.original} to ${tools.comparison}`);
  if (e.retry_delta) clauses.push(`${e.retry_delta < 0 ? "reduced" : "increased"} retries by ${Math.abs(e.retry_delta)}`);
  if (e.repeated_transition_delta) clauses.push(`${e.repeated_transition_delta < 0 ? "removed" : "added"} ${Math.abs(e.repeated_transition_delta)} repeated transition${Math.abs(e.repeated_transition_delta) === 1 ? "" : "s"}`);
  const duration = diff.outcomes.find((item) => item.metric === "duration_ms"); if (duration && duration.percent_change !== null) clauses.push(`${duration.delta! < 0 ? "reduced" : "increased"} latency by ${Math.abs(duration.percent_change).toFixed(0)}%`);
  const status = diff.outcomes.find((item) => item.metric === "status");
  const outcome = status ? (status.original === status.comparison ? `the outcome stayed ${status.comparison}` : `the outcome changed from ${status.original} to ${status.comparison}`) : "";
  if (!clauses.length) return `No behavioral differences were recorded between these runs${outcome ? `; ${outcome}` : ""}.`;
  return `The comparison ${clauses.join(", ")}${outcome ? `; ${outcome}` : ""}.`;
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(display).join(", ") : "—";
  if (typeof value === "object") { const entries = Object.entries(value as Record<string, unknown>); return entries.length ? entries.map(([key, item]) => `${humanize(key)}: ${display(item)}`).join(" · ") : "—"; }
  return String(value);
}
