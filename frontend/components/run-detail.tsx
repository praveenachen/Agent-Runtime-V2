"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DiagnosisPanel } from "@/components/diagnosis-panel";
import { RunGraph, collapseRetries, isErrorNode, nodeVisual } from "@/components/run-graph";
import { RunStatus } from "@/components/run-status";
import { CopyButton, humanize, workflowVisual } from "@/components/run-widgets";
import { Icon, type IconName } from "@/components/ui/icon";
import {
  fetchRun,
  formatDuration,
  type GraphNode,
  type RunDetail as RunDetailType,
  type SilverEvent,
} from "@/lib/api";
import { graphNodeDisplayName, runDetailDisplayName, semanticLabelForType } from "@/lib/run-display";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; run: RunDetailType };

type EventsTab = "events" | "llm" | "tool" | "raw";

const clock = new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const startedFormat = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });

export function RunDetail({ runId }: { runId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reload, setReload] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<EventsTab>("events");
  useEffect(() => {
    const controller = new AbortController();
    fetchRun(runId, controller.signal)
      .then((run) => setState({ kind: "ready", run }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState({ kind: "error", message: error.message });
      });
    return () => controller.abort();
  }, [runId, reload]);
  const retry = () => { setState({ kind: "loading" }); setReload((value) => value + 1); };

  const run = state.kind === "ready" ? state.run : null;
  const nodes = useMemo(() => {
    if (!run) return [];
    const eventAttributes = new Map(run.events.map((event) => [event.span_id, { ...event.attributes, ...event.semantic_attributes }]));
    return run.graph.nodes.map((node) => ({ ...node, semantic_attributes: { ...(eventAttributes.get(node.span_id) ?? {}), ...node.semantic_attributes } }));
  }, [run]);

  if (state.kind === "loading") {
    return <div className="detail-skeleton" aria-label="Loading run"><div className="skeleton-title" /><div className="skeleton-metrics" /><div className="skeleton-graph" /></div>;
  }
  if (state.kind === "error" || !run) {
    return <section className="state-panel" role="alert"><span className="state-icon danger">!</span><h2>Run unavailable</h2><p>{state.kind === "error" ? state.message : ""}</p><div className="state-actions"><button className="button-secondary" onClick={retry} type="button">Try again</button><Link className="button-ghost" href="/runs">Back to runs</Link></div></section>;
  }

  const edges = run.graph.edges;
  const collapsed = collapseRetries(nodes, edges);
  const selectNode = (nodeId: string) => setSelectedId(collapsed.owner.get(nodeId) ?? nodeId);
  const openRaw = () => { setTab("raw"); window.setTimeout(() => document.getElementById("run-events")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0); };

  return <>
    <RunHeader onRaw={openRaw} run={run} />
    <section className="rd-card rd-graph-card">
      <header className="rd-card-heading"><div><h2>Execution graph</h2><p>Recorded parent/child structure, left to right. Click a node for details.</p></div>
        <div className="rd-legend"><span><i className="ok" /> Success</span><span><i className="err" /> Failed</span><span><i className="tool" /> Tool call</span><span><i className="llm" /> LLM / agent</span><span><i className="decision" /> Decision / approval</span></div></header>
      <RunGraph edges={edges} nodes={nodes} onSelect={setSelectedId} selectedId={selectedId} />
      {selectedId && <NodeDetail members={collapsed.groups.get(selectedId) ?? nodes.filter((node) => node.id === selectedId)} onClose={() => setSelectedId(null)} start={Date.parse(run.started_at)} />}
    </section>
    <div className="rd-layout">
      <div className="rd-main">
        <DiagnosisPanel runId={run.run_id} />
        <EventsPanel nodes={nodes} onTab={setTab} run={run} tab={tab} />
      </div>
      <aside className="rd-side">
        <MetricsCard run={run} />
        <StepList nodes={nodes} onSelect={selectNode} selectedId={selectedId} owner={(id) => collapsed.owner.get(id) ?? id} run={run} />
      </aside>
    </div>
  </>;
}

function shortRunId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function recordedAttribute(run: RunDetailType, key: string): string | null {
  for (const event of run.events) {
    const value = event.attributes[key] ?? event.semantic_attributes[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function RunHeader({ run, onRaw }: { run: RunDetailType; onRaw: () => void }) {
  const fullId = run.external_run_id ?? run.run_id; const rawTitle = runDetailDisplayName(run); const title = rawTitle.includes("_") && !rawTitle.includes(" ") ? humanize(rawTitle) : rawTitle;
  const model = recordedAttribute(run, "agent.runtime.model.name"); const prompt = recordedAttribute(run, "agent.runtime.prompt.version");
  const visual = workflowVisual(run.workflow_name ?? title);
  const subtitle = [`${run.metrics.step_count} steps`, `${run.metrics.tool_call_count} tool call${run.metrics.tool_call_count === 1 ? "" : "s"}`, `${run.metrics.llm_call_count} LLM call${run.metrics.llm_call_count === 1 ? "" : "s"}`, `${run.trace_ids.length} OTel trace${run.trace_ids.length === 1 ? "" : "s"}`].join(" · ");
  return <>
    <header className="rd-header">
      <div><Link className="back-link" href="/runs">Runs <span>›</span> <b>{shortRunId(fullId)}</b></Link><div className="heading-line"><h1>{title}</h1><RunStatus status={run.status} /></div><p className="rd-subtitle">{subtitle}</p></div>
      <div className="rd-actions"><Link className="button-secondary" href={`/compare?original=${encodeURIComponent(run.run_id)}`}><Icon name="compare" /> Compare</Link><button className="button-secondary" onClick={onRaw} type="button"><Icon name="code" /> View raw events</button></div>
    </header>
    <section className="rd-meta" aria-label="Run identity">
      {run.workflow_name && <div><span className={`rd-meta-icon tone-${visual.tone}`}><Icon name={visual.icon} /></span><div><small>Workflow</small><strong>{humanize(run.workflow_name)}</strong>{run.workflow_version && <em>Version {run.workflow_version}</em>}</div></div>}
      {run.environment && <div><span className="rd-meta-icon plain"><Icon name="layers" /></span><div><small>Environment</small><strong><i className="rd-dot" />{humanize(run.environment)}</strong></div></div>}
      {model && <div><span className="rd-meta-icon plain"><Icon name="spark" /></span><div><small>Model</small><strong>{model}</strong></div></div>}
      {prompt && <div><span className="rd-meta-icon plain"><Icon name="book" /></span><div><small>Prompt version</small><strong>{prompt}</strong></div></div>}
      <div><span className="rd-meta-icon plain"><Icon name="calendar" /></span><div><small>Started</small><strong>{startedFormat.format(Date.parse(run.started_at))}</strong><em>Duration {formatDuration(run.metrics.total_duration_ms)}</em></div></div>
      <div><span className="rd-meta-icon plain"><Icon name="copy" /></span><div><small>Run ID</small><strong className="mono rd-run-id" title={fullId}>{shortRunId(fullId)}<CopyButton value={fullId} /></strong></div></div>
    </section>
  </>;
}

function NodeDetail({ members, start, onClose }: { members: GraphNode[]; start: number; onClose: () => void }) {
  const node = members[0]; const attributes = Object.entries(node.semantic_attributes).filter(([, value]) => value !== null && value !== undefined && value !== "" && typeof value !== "object").slice(0, 12);
  return <div className="rd-node-detail">
    <header><div><strong>{graphNodeDisplayName(node)}</strong><span>{semanticLabelForType(node.event_type)} · {node.status.toLowerCase() === "unset" ? "ok" : node.status.toLowerCase()}{members.length > 1 ? ` · ${members.length} retry attempts` : ""}</span></div><button aria-label="Close details" onClick={onClose} type="button"><Icon name="x" /></button></header>
    <dl><div><dt>Duration</dt><dd>{formatDuration(members.reduce((sum, member) => sum + member.duration_ms, 0))}</dd></div><div><dt>Offset</dt><dd>+{formatDuration(Date.parse(node.started_at) - start)}</dd></div><div><dt>Agent</dt><dd>{node.agent_name ?? "—"}</dd></div><div><dt>Span</dt><dd className="mono" title={node.span_id}>{node.span_id.slice(0, 12)}</dd></div></dl>
    {attributes.length > 0 && <details><summary>Recorded metadata</summary><dl className="rd-attrs">{attributes.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd title={String(value)}>{String(value)}</dd></div>)}</dl></details>}
  </div>;
}

function MetricsCard({ run }: { run: RunDetailType }) {
  const m = run.metrics;
  const cards: Array<{ icon: IconName; tone: string; label: string; value: string; note?: string }> = [
    { icon: "bolt", tone: "blue", label: "Duration", value: formatDuration(m.total_duration_ms) },
    { icon: "tool", tone: "amber", label: "Tool calls", value: String(m.tool_call_count), note: m.tool_latency_ms ? `${formatDuration(m.tool_latency_ms)} in tools` : undefined },
    { icon: "spark", tone: "purple", label: "LLM calls", value: String(m.llm_call_count) },
    { icon: "activity", tone: m.retry_count ? "red" : "green", label: "Retries", value: String(m.retry_count), note: m.retry_count ? undefined : "None recorded" },
  ];
  if (m.total_tokens !== null) cards.push({ icon: "layers", tone: "blue", label: "Total tokens", value: m.total_tokens.toLocaleString(), note: m.input_tokens !== null && m.output_tokens !== null ? `${m.input_tokens.toLocaleString()} in · ${m.output_tokens.toLocaleString()} out` : undefined });
  if (m.estimated_cost !== null) cards.push({ icon: "database", tone: "green", label: "Cost", value: `$${m.estimated_cost.toFixed(4)}` });
  if (m.approval_wait_ms > 0) cards.push({ icon: "approval", tone: "amber", label: "Approval wait", value: formatDuration(m.approval_wait_ms) });
  if (m.repeated_transition_count > 0) cards.push({ icon: "compare", tone: "amber", label: "Repeated transitions", value: `${m.repeated_transition_count}×` });
  if (m.error_count > 0) cards.push({ icon: "alert", tone: "red", label: "Errors", value: String(m.error_count) });
  return <section className="rd-card rd-metrics"><header className="rd-card-heading"><h2>Run metrics</h2></header><div className="rd-metric-grid">{cards.slice(0, 8).map((card) => <article className={`tone-${card.tone}`} key={card.label}><span className="rd-metric-icon"><Icon name={card.icon} /></span><div><small>{card.label}</small><strong>{card.value}</strong>{card.note && <em>{card.note}</em>}</div></article>)}</div></section>;
}

function StepList({ nodes, run, selectedId, onSelect, owner }: { nodes: GraphNode[]; run: RunDetailType; selectedId: string | null; onSelect: (id: string) => void; owner: (id: string) => string }) {
  const steps = [...nodes].filter((node) => !(node.event_type.toUpperCase() === "RUN" && !node.parent_span_id)).sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
  return <section className="rd-card rd-steps"><header className="rd-card-heading"><h2>Step list</h2><span className="rd-count">{steps.length} steps · {formatDuration(run.metrics.total_duration_ms)}</span></header>
    <ol>{steps.map((node) => { const visual = nodeVisual(node); const error = isErrorNode(node);
      return <li key={node.id}><button className={`${error ? "is-error" : ""} ${selectedId === owner(node.id) ? "selected" : ""}`} onClick={() => onSelect(node.id)} type="button"><span className={`rd-step-icon tone-${visual.tone}`}><Icon name={visual.icon} /></span><span className="rd-step-text"><strong>{graphNodeDisplayName(node)}</strong><small>{clock.format(Date.parse(node.started_at))} · {semanticLabelForType(node.event_type)}</small></span><time>{formatDuration(node.duration_ms)}</time></button></li>; })}</ol></section>;
}

const DETAIL_KEYS = ["agent.runtime.tool.name", "agent.runtime.tool.operation", "relay.operation", "relay.outcome", "agent.runtime.model.name", "error.code"];

function eventDetail(event: SilverEvent): string {
  const attributes = { ...event.attributes, ...event.semantic_attributes };
  return DETAIL_KEYS.flatMap((key) => attributes[key] !== undefined && attributes[key] !== "" ? [`${key.split(".").at(-1)}: ${String(attributes[key])}`] : []).join(" · ") || "—";
}

function EventsPanel({ run, nodes, tab, onTab }: { run: RunDetailType; nodes: GraphNode[]; tab: EventsTab; onTab: (tab: EventsTab) => void }) {
  const names = new Map(nodes.map((node) => [node.span_id, graphNodeDisplayName(node)]));
  const events = [...run.events].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  const llm = events.filter((event) => event.event_type === "LLM_CALL"); const tool = events.filter((event) => event.event_type === "TOOL_CALL");
  const shown = tab === "llm" ? llm : tab === "tool" ? tool : events;
  const tabs: Array<[EventsTab, string]> = [["events", `Events (${events.length})`], ["llm", `LLM calls (${llm.length})`], ["tool", `Tool calls (${tool.length})`], ["raw", "Raw events"]];
  return <section className="rd-card rd-events" id="run-events">
    <div className="rd-tabs" role="tablist">{tabs.map(([key, label]) => <button aria-selected={tab === key} className={tab === key ? "active" : ""} key={key} onClick={() => onTab(key)} role="tab" type="button">{label}</button>)}</div>
    {tab === "raw" ? <pre id="raw-events">{JSON.stringify(run.events, null, 2)}</pre> : shown.length === 0 ? <p className="diagnosis-muted rd-empty">No {tab === "llm" ? "LLM calls" : "tool calls"} were recorded for this run.</p> :
      <div className="overview-table-scroll"><table className="rd-event-table"><thead><tr><th>Time</th><th>Type</th><th>Step</th><th>Status</th><th>Duration</th><th>Details</th></tr></thead><tbody>{shown.map((event) => <tr className={event.event_type === "ERROR" || event.status.toLowerCase() === "error" ? "is-error" : ""} key={event.event_id}><td className="mono">{clock.format(Date.parse(event.timestamp))}</td><td>{semanticLabelForType(event.event_type)}</td><td>{names.get(event.span_id) ?? "—"}</td><td>{event.status.toLowerCase() === "unset" ? "ok" : event.status.toLowerCase()}</td><td>{formatDuration(event.duration_ms)}</td><td className="rd-detail-cell" title={eventDetail(event)}>{eventDetail(event)}</td></tr>)}</tbody></table></div>}
  </section>;
}
