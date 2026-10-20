"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RunStatus } from "@/components/run-status";
import { Icon } from "@/components/ui/icon";
import {
  fetchApprovals,
  fetchDiagnosis,
  fetchRuns,
  formatDate,
  formatDuration,
  type RunSummary,
} from "@/lib/api";
import { useProjectId } from "@/lib/project";
import { runDisplayName } from "@/lib/run-display";

export function OverviewDashboard() {
  const { projectId } = useProjectId();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [anomalies, setAnomalies] = useState<Record<string, number>>({});
  const [pendingApprovals, setPendingApprovals] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal)
      .then(async (loadedRuns) => {
        setRuns(loadedRuns);
        const diagnoses = await Promise.all(
          loadedRuns.slice(0, 5).map(async (run) => {
            try {
              const diagnosis = await fetchDiagnosis(run.run_id, controller.signal);
              return [run.run_id, diagnosis.evidence.items.length] as const;
            } catch {
              return [run.run_id, 0] as const;
            }
          }),
        );
        setAnomalies(Object.fromEntries(diagnoses));
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    fetchApprovals(projectId, controller.signal)
      .then((items) => setPendingApprovals(items.length))
      .catch(() => setPendingApprovals(null));
    return () => controller.abort();
  }, [projectId]);
  if (failed) return <section className="state-panel compact"><span className="state-icon danger"><Icon name="alert" /></span><h2>Runtime data unavailable</h2><p>The shell is healthy, but the runs API could not be reached.</p></section>;
  if (runs === null) return <div className="skeleton-stack"><div className="skeleton-metrics" /><div className="skeleton-row" /></div>;
  const success = runs.length ? Math.round((runs.filter((run) => run.status.toLowerCase() === "succeeded").length / runs.length) * 100) : 0;
  const average = runs.length ? runs.reduce((sum, run) => sum + run.metrics.total_duration_ms, 0) / runs.length : 0;
  const anomalyCount = Object.values(anomalies).reduce((sum, count) => sum + count, 0);
  const succeeded = runs.filter((run) => run.status.toLowerCase() === "succeeded").length;
  const failedRuns = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const otherRuns = Math.max(0, runs.length - succeeded - failedRuns);
  return <>
    <section className="metric-grid" aria-label="Runtime metrics"><article className="metric-card tone-blue"><span><Icon name="runs" /> Total runs</span><strong>{runs.length}</strong><small>Logical runs in the current Gold projection</small></article><article className="metric-card tone-green"><span><Icon name="check" /> Success rate</span><strong>{runs.length ? `${success}%` : "—"}</strong><small>{runs.length ? `${succeeded} succeeded of ${runs.length}` : "Waiting for run history"}</small></article><article className="metric-card tone-teal"><span><Icon name="activity" /> Average latency</span><strong>{runs.length ? formatDuration(average) : "—"}</strong><small>Measured wall-clock run duration</small></article><article className={`metric-card ${anomalyCount ? "tone-amber" : "tone-green"}`}><span><Icon name={anomalyCount ? "alert" : "shield"} /> Recent anomalies</span><strong>{anomalyCount}</strong><small>Evidence-backed findings in the latest runs</small></article></section>
    <section className="overview-snapshot-grid">
      <article className="snapshot-card"><header className="section-heading"><div><p className="eyebrow">Run activity</p><h2>Recorded outcomes</h2><p className="section-copy">Current visible history; no projected trend data.</p></div><span className="snapshot-total">{runs.length} runs</span></header>{runs.length ? <div className="status-composition"><div className="composition-bar" aria-label={`${succeeded} succeeded, ${failedRuns} failed, ${otherRuns} other`}><i className="composition-success" style={{ width: `${(succeeded / runs.length) * 100}%` }} /><i className="composition-failed" style={{ width: `${(failedRuns / runs.length) * 100}%` }} /><i className="composition-other" style={{ width: `${(otherRuns / runs.length) * 100}%` }} /></div><div className="composition-legend"><span><i className="success" />Succeeded <b>{succeeded}</b></span><span><i className="failed" />Failed <b>{failedRuns}</b></span><span><i className="other" />Other <b>{otherRuns}</b></span></div></div> : <div className="empty-state compact"><strong>No outcome history yet</strong><p>The composition appears after the first logical run.</p></div>}</article>
      <article className="attention-card"><header className="section-heading"><div><p className="eyebrow">Action center</p><h2>Needs attention</h2></div><Link className="text-link" href="/approvals">Open inbox →</Link></header><div className="attention-list"><Link href="/approvals"><span className="attention-icon warning"><Icon name="approval" /></span><span><strong>Pending approvals</strong><small>{pendingApprovals === null ? (projectId ? "Unavailable" : "Select a project to view") : `${pendingApprovals} awaiting review`}</small></span><b>{pendingApprovals ?? "—"}</b></Link><Link href="/runs"><span className={`attention-icon ${anomalyCount ? "danger" : "healthy"}`}><Icon name={anomalyCount ? "alert" : "check"} /></span><span><strong>Evidence findings</strong><small>Across the latest five runs</small></span><b>{anomalyCount}</b></Link></div></article>
    </section>
    <section className="recent-runs-card"><header className="section-heading"><div><p className="eyebrow">Recent activity</p><h2>Latest runs</h2><p className="section-copy">Logical workflows ordered by execution time.</p></div><Link className="text-link" href="/runs">View all runs →</Link></header>{runs.length === 0 ? <div className="empty-state compact"><strong>Waiting for the first run</strong><p>Send OTLP telemetry through the local Collector.</p></div> : <div className="recent-list recent-list-header"><span>Run / workflow</span><span>Duration</span><span>Status</span><span /></div>} {runs.length > 0 && <div className="recent-list recent-list-body">{runs.slice(0, 5).map((run) => <Link href={`/runs/${run.run_id}`} key={run.run_id}><div><strong>{runDisplayName(run)}</strong><span>{run.workflow_name ?? "Workflow not recorded"} · {formatDate(run.started_at)}</span>{(anomalies[run.run_id] ?? 0) > 0 && <em>{anomalies[run.run_id]} evidence-backed alert{anomalies[run.run_id] === 1 ? "" : "s"}</em>}</div><span>{formatDuration(run.metrics.total_duration_ms)}</span><RunStatus status={run.status} /><b>→</b></Link>)}</div>}</section>
  </>;
}
