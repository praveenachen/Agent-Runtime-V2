"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { RunStatus } from "@/components/run-status";
import { DiagnosisPanel } from "@/components/diagnosis-panel";
import {
  fetchRun,
  formatDuration,
  type GraphEdge,
  type GraphNode,
  type RunDetail as RunDetailType,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; run: RunDetailType };

export function RunDetail({ runId }: { runId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reload, setReload] = useState(0);
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

  if (state.kind === "loading") {
    return <div className="detail-skeleton" aria-label="Loading run"><div className="skeleton-title" /><div className="skeleton-metrics" /><div className="skeleton-graph" /></div>;
  }
  if (state.kind === "error") {
    return <section className="state-panel" role="alert"><span className="state-icon danger">!</span><h2>Run unavailable</h2><p>{state.message}</p><div className="state-actions"><button className="button-secondary" onClick={retry} type="button">Try again</button><Link className="button-ghost" href="/runs">Back to runs</Link></div></section>;
  }

  const run = state.run;
  return <>
    <header className="run-detail-heading"><div><Link className="back-link" href="/runs">← Runs</Link><div className="heading-line"><h1>{run.name}</h1><RunStatus status={run.status} /></div><p className="run-id mono">{run.run_id}</p></div><div className="run-context"><span>{run.workflow_name ?? "Unknown workflow"}</span><span>{run.workflow_version ?? "No version"}</span><span>{run.environment ?? "Unknown environment"}</span></div></header>
    <section className="detail-metrics" aria-label="Run metrics">
      <CompactMetric label="Duration" value={formatDuration(run.metrics.total_duration_ms)} />
      <CompactMetric label="Steps" value={String(run.metrics.step_count)} />
      <CompactMetric label="Tool / LLM" value={`${run.metrics.tool_call_count} / ${run.metrics.llm_call_count}`} />
      <CompactMetric label="Retries" value={String(run.metrics.retry_count)} warn={run.metrics.retry_count > 0} />
      <CompactMetric label="Tokens" value={run.metrics.total_tokens.toLocaleString()} />
      <CompactMetric label="Cost" value={run.metrics.estimated_cost == null ? "—" : `$${run.metrics.estimated_cost.toFixed(4)}`} />
    </section>
    <ExecutionGraph nodes={run.graph.nodes} edges={run.graph.edges} />
    <div className="detail-grid"><Timeline run={run} /><DiagnosisPanel runId={run.run_id} /></div>
    <details className="raw-panel"><summary><span>Raw normalized events</span><small>{run.events.length} Silver records</small></summary><pre>{JSON.stringify(run.events, null, 2)}</pre></details>
  </>;
}

function ExecutionGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const columns = useMemo(() => {
    const grouped = new Map<number, GraphNode[]>();
    nodes.forEach((node) => grouped.set(node.depth, [...(grouped.get(node.depth) ?? []), node]));
    return [...grouped.entries()].sort(([a], [b]) => a - b);
  }, [nodes]);
  const semanticEdges = edges.filter((edge) => edge.type !== "parent_child");
  const incoming = (node: GraphNode) => edges.filter((edge) => edge.target === node.id);
  return <section className="graph-card">
    <header className="section-heading"><div><p className="eyebrow">Execution graph</p><h2>Trace topology</h2></div><div className="graph-legend"><span><i className="legend-line" /> parent</span><span><i className="legend-line semantic" /> semantic</span><span><i className="legend-dot" /> concurrent</span></div></header>
    <div className="graph-scroll"><div className="graph-stage" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(190px, 1fr))` }}>{columns.map(([depth, column]) => <div className="graph-column" key={depth}><span className="column-label">Depth {depth}</span>{column.sort((a, b) => a.lane - b.lane).map((node) => <article className={`graph-node node-${node.event_type.toLowerCase()}`} key={node.id}><div className="node-topline"><span>{node.event_type.replaceAll("_", " ")}</span><span>{formatDuration(node.duration_ms)}</span></div><strong>{node.label}</strong><small>{node.agent_name ?? "runtime"}</small><div className="node-flags">{node.is_concurrent && <span>parallel</span>}{incoming(node).filter((edge) => edge.type !== "parent_child").map((edge) => <span className="semantic-flag" key={edge.id}>{edge.type.replaceAll("_", " ")}</span>)}</div></article>)}</div>)}</div></div>
    {semanticEdges.length > 0 && <footer className="edge-summary">{semanticEdges.map((edge) => <span key={edge.id}>{edge.type.replaceAll("_", " ")}: <b>{shortId(edge.source)}</b> → <b>{shortId(edge.target)}</b></span>)}</footer>}
  </section>;
}

function Timeline({ run }: { run: RunDetailType }) {
  const start = new Date(run.started_at).getTime();
  return <section className="timeline-card"><header className="section-heading"><div><p className="eyebrow">Timeline</p><h2>Steps and events</h2></div><span className="subtle">Execution time</span></header><ol className="timeline">{run.graph.nodes.map((node) => <li key={node.id}><span className={`timeline-mark mark-${node.event_type.toLowerCase()}`} /><div><strong>{node.label}</strong><small>{node.event_type.replaceAll("_", " ")} · +{formatDuration(new Date(node.started_at).getTime() - start)}</small></div><time>{formatDuration(node.duration_ms)}</time></li>)}</ol></section>;
}

function CompactMetric({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return <article className="compact-metric"><span>{label}</span><strong className={warn ? "warning-text" : ""}>{value}</strong></article>;
}

function shortId(value: string) {
  return value.split(":").at(-1)?.slice(0, 8) ?? value;
}
