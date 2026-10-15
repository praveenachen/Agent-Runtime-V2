"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { RunStatus } from "@/components/run-status";
import { fetchRuns, formatDate, formatDuration, type RunSummary } from "@/lib/api";

type LoadState = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; runs: RunSummary[] };

export function RunsList() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [status, setStatus] = useState("all");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal).then((runs) => setState({ kind: "ready", runs })).catch((error: Error) => {
      if (error.name !== "AbortError") setState({ kind: "error", message: error.message });
    });
    return () => controller.abort();
  }, [reload]);
  const retry = () => { setState({ kind: "loading" }); setReload((value) => value + 1); };
  const filtered = useMemo(() => state.kind !== "ready" ? [] : status === "all" ? state.runs : state.runs.filter((run) => run.status === status), [state, status]);

  if (state.kind === "loading") return <div className="skeleton-stack" aria-label="Loading runs">{Array.from({ length: 5 }, (_, index) => <div className="skeleton-row" key={index} />)}</div>;
  if (state.kind === "error") return <section className="state-panel" role="alert"><span className="state-icon danger">!</span><h2>Runs are unavailable</h2><p>{state.message} Check that the local backend is running.</p><button className="button-secondary" onClick={retry} type="button">Try again</button></section>;

  return <><div className="toolbar"><div className="segmented" aria-label="Filter runs by status">{["all", "succeeded", "failed", "running"].map((value) => <button aria-pressed={status === value} className={status === value ? "active" : ""} key={value} onClick={() => setStatus(value)} type="button">{value}</button>)}</div><span className="result-count">{filtered.length} run{filtered.length === 1 ? "" : "s"}</span></div>
    {filtered.length === 0 ? <section className="state-panel"><span className="state-icon">◇</span><h2>{state.runs.length ? "No runs match this filter" : "No runs yet"}</h2><p>{state.runs.length ? "Choose another status to widen the view." : "Send an OTLP trace through the Collector to create the first run."}</p></section> :
      <div className="run-table-wrap"><table className="run-table"><thead><tr><th>Run</th><th>Status</th><th>Started</th><th>Duration</th><th>Steps</th><th>Tokens</th><th aria-label="Open run" /></tr></thead><tbody>{filtered.map((run) => <tr key={run.run_id}><td><Link className="run-link" href={`/runs/${run.run_id}`}><strong>{run.name}</strong><span>{run.workflow_name ?? "Unspecified workflow"} · {run.environment ?? "unknown env"}</span></Link></td><td><RunStatus status={run.status} /></td><td className="mono subtle">{formatDate(run.started_at)}</td><td className="mono">{formatDuration(run.metrics.total_duration_ms)}</td><td className="mono">{run.metrics.step_count}</td><td className="mono">{run.metrics.total_tokens.toLocaleString()}</td><td><Link className="row-arrow" href={`/runs/${run.run_id}`} aria-label={`Open ${run.name}`}>→</Link></td></tr>)}</tbody></table></div>}
  </>;
}
