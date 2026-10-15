"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RunStatus } from "@/components/run-status";
import { fetchRuns, formatDate, formatDuration, type RunSummary } from "@/lib/api";

export function OverviewDashboard() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal).then(setRuns).catch((error: Error) => {
      if (error.name !== "AbortError") setFailed(true);
    });
    return () => controller.abort();
  }, []);
  if (failed) return <section className="state-panel compact"><h2>Runtime data unavailable</h2><p>The shell is healthy, but the runs API could not be reached.</p></section>;
  if (runs === null) return <div className="skeleton-stack"><div className="skeleton-metrics" /><div className="skeleton-row" /></div>;
  const success = runs.length ? Math.round((runs.filter((run) => run.status === "succeeded").length / runs.length) * 100) : 0;
  const average = runs.length ? runs.reduce((sum, run) => sum + run.metrics.total_duration_ms, 0) / runs.length : 0;
  return <>
    <section className="metric-grid" aria-label="Runtime metrics"><article className="metric-card"><span>Total runs</span><strong>{runs.length}</strong><small>Normalized traces in Gold</small></article><article className="metric-card"><span>Success rate</span><strong>{runs.length ? `${success}%` : "—"}</strong><small>Across visible run history</small></article><article className="metric-card"><span>Average latency</span><strong>{runs.length ? formatDuration(average) : "—"}</strong><small>Wall-clock run duration</small></article><article className="metric-card"><span>Errors</span><strong>{runs.reduce((sum, run) => sum + run.metrics.error_count, 0)}</strong><small>Explicit error events and spans</small></article></section>
    <section className="recent-runs-card"><header className="section-heading"><div><p className="eyebrow">Recent activity</p><h2>Latest runs</h2></div><Link className="text-link" href="/runs">View all →</Link></header>{runs.length === 0 ? <div className="empty-state compact"><strong>Waiting for the first run</strong><p>Send OTLP telemetry through the local Collector.</p></div> : <div className="recent-list">{runs.slice(0, 5).map((run) => <Link href={`/runs/${run.run_id}`} key={run.run_id}><div><strong>{run.name}</strong><span>{run.workflow_name ?? "Unknown workflow"} · {formatDate(run.started_at)}</span></div><span>{formatDuration(run.metrics.total_duration_ms)}</span><RunStatus status={run.status} /><b>→</b></Link>)}</div>}</section>
  </>;
}
