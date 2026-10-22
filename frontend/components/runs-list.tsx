"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { ProjectScope } from "@/components/project-scope";
import { RunStatus } from "@/components/run-status";
import { CopyButton, KpiCard, compactId, humanize, workflowVisual } from "@/components/run-widgets";
import { Icon } from "@/components/ui/icon";
import { fetchDiagnosis, formatDuration, type RunSummary } from "@/lib/api";
import { useProjectDiscovery } from "@/lib/project";
import { runDisplayName } from "@/lib/run-display";

const PAGE_SIZE = 10;
const HOUR_MS = 3_600_000;
const RANGES = { all: { label: "All time", ms: Infinity }, "24h": { label: "Last 24 hours", ms: 24 * HOUR_MS }, "7d": { label: "Last 7 days", ms: 7 * 24 * HOUR_MS }, "30d": { label: "Last 30 days", ms: 30 * 24 * HOUR_MS } } as const;
type RangeKey = keyof typeof RANGES;
type Anomalies = Record<string, number | null>;

const startFormat = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export function RunsList() {
  const { projectId, projects, runs: allRuns, loading, error } = useProjectDiscovery();
  const [status, setStatus] = useState("all");
  const [workflow, setWorkflow] = useState("all");
  const [environment, setEnvironment] = useState("all");
  const [range, setRange] = useState<RangeKey>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [anomalies, setAnomalies] = useState<Anomalies>({});
  const [now] = useState(() => Date.now());

  const runs = useMemo(() => projectId ? (allRuns ?? []).filter((run) => run.project_id === projectId).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)) : [], [allRuns, projectId]);

  useEffect(() => {
    if (!runs.length) return;
    const controller = new AbortController(); let cursor = 0;
    const worker = async () => {
      while (cursor < runs.length && !controller.signal.aborted) {
        const run = runs[cursor++];
        try {
          const diagnosis = await fetchDiagnosis(run.run_id, controller.signal);
          if (!controller.signal.aborted) setAnomalies((current) => ({ ...current, [run.run_id]: diagnosis.evidence.items.length }));
        } catch { if (!controller.signal.aborted) setAnomalies((current) => ({ ...current, [run.run_id]: null })); }
      }
    };
    void Promise.all(Array.from({ length: 6 }, worker));
    return () => controller.abort();
  }, [runs]);

  const workflows = useMemo(() => [...new Set(runs.map((run) => run.workflow_name).filter(Boolean))] as string[], [runs]);
  const environments = useMemo(() => [...new Set(runs.map((run) => run.environment).filter(Boolean))] as string[], [runs]);
  const statuses = useMemo(() => [...new Set(runs.map((run) => run.status))], [runs]);
  const filtered = useMemo(() => runs.filter((run) => {
    const needle = query.trim().toLowerCase();
    return (status === "all" || run.status === status)
      && (workflow === "all" || run.workflow_name === workflow)
      && (environment === "all" || run.environment === environment)
      && Date.parse(run.started_at) >= now - RANGES[range].ms
      && (!needle || [run.name, run.run_id, run.external_run_id, run.workflow_name, run.workflow_version, run.environment, runDisplayName(run)].some((value) => value?.toLowerCase().includes(needle)));
  }), [runs, status, workflow, environment, range, query, now]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)); const current = Math.min(page, pageCount);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const firstShown = filtered.length ? (current - 1) * PAGE_SIZE + 1 : 0; const lastShown = Math.min(current * PAGE_SIZE, filtered.length);
  const allOnPage = rows.length > 0 && rows.every((run) => selected.has(run.run_id)); const someOnPage = rows.some((run) => selected.has(run.run_id));
  const headerCheckbox = useRef<HTMLInputElement>(null);
  useEffect(() => { if (headerCheckbox.current) headerCheckbox.current.indeterminate = someOnPage && !allOnPage; }, [someOnPage, allOnPage]);

  const failed = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const durations = runs.map((run) => run.metrics.total_duration_ms).filter(Number.isFinite).sort((a, b) => a - b);
  const averageDuration = durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null;
  const median = durations.length ? (durations[Math.floor((durations.length - 1) / 2)] + durations[Math.ceil((durations.length - 1) / 2)]) / 2 : null;
  const checked = runs.filter((run) => typeof anomalies[run.run_id] === "number").length;
  const withAnomalies = runs.filter((run) => (anomalies[run.run_id] ?? 0) > 0).length;
  const diagnosing = runs.length > 0 && runs.some((run) => anomalies[run.run_id] === undefined);

  const resetPage = <T,>(setter: (value: T) => void) => (value: T) => { setter(value); setPage(1); };
  const clearFilters = () => { setStatus("all"); setWorkflow("all"); setEnvironment("all"); setRange("all"); setQuery(""); setPage(1); };
  const toggleRow = (id: string) => setSelected((currentSet) => { const next = new Set(currentSet); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const togglePage = () => setSelected((currentSet) => { const next = new Set(currentSet); rows.forEach((run) => allOnPage ? next.delete(run.run_id) : next.add(run.run_id)); return next; });

  if (error) return <section className="state-panel" role="alert"><span className="state-icon danger"><Icon name="alert" /></span><h2>Runs are unavailable</h2><p>{error} Check that the local backend is running.</p><button className="button-secondary" onClick={() => window.location.reload()} type="button">Try again</button></section>;
  if (loading || (projects.length === 1 && !projectId)) return <div className="skeleton-stack" aria-label="Loading runs"><div className="skeleton-metrics" /><div className="skeleton-toolbar" />{Array.from({ length: 6 }, (_, index) => <div className="skeleton-row" key={index} />)}</div>;
  if (!projectId) return <><ProjectScope /><section className="state-panel compact"><span className="state-icon"><Icon name="shield" /></span><h2>Select a recorded project</h2><p>Runs are scoped to the project selected in the top bar.</p></section></>;

  return <div className="runs-dashboard">
    <section className="overview-kpi-grid" aria-label="Run history summary">
      <KpiCard icon="layers" tone="blue" label="Total runs" value={String(runs.length)} subtitle="Recorded for this project" seed={5} />
      <KpiCard icon="activity" tone="red" label="Failure rate" value={runs.length ? `${((failed / runs.length) * 100).toFixed(1)}%` : "—"} subtitle={runs.length ? `${failed} failed / ${runs.length} total` : "No recorded outcomes"} seed={9} />
      <KpiCard icon="bolt" tone="green" label="Avg. duration" value={averageDuration === null ? "—" : formatDuration(averageDuration)} subtitle={median === null ? "No recorded durations" : `Median ${formatDuration(median)}`} seed={13} />
      <KpiCard icon="alert" tone="purple" label="Runs with anomalies" value={diagnosing && checked === 0 ? "…" : String(withAnomalies)} subtitle={diagnosing ? "Checking diagnoses…" : checked ? `${((withAnomalies / checked) * 100).toFixed(1)}% of ${checked} diagnosed runs` : "Diagnosis unavailable"} seed={17} />
    </section>

    <section className="runs-filters" aria-label="Run filters">
      <label><span>Workflow</span><select onChange={(event) => resetPage(setWorkflow)(event.target.value)} value={workflow}><option value="all">All workflows</option>{workflows.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>
      <label><span>Environment</span><select onChange={(event) => resetPage(setEnvironment)(event.target.value)} value={environment}><option value="all">All environments</option>{environments.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>
      <label><span>Status</span><select onChange={(event) => resetPage(setStatus)(event.target.value)} value={status}><option value="all">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>
      <label><span>Date range</span><select onChange={(event) => resetPage(setRange)(event.target.value as RangeKey)} value={range}>{(Object.keys(RANGES) as RangeKey[]).map((key) => <option key={key} value={key}>{RANGES[key].label}</option>)}</select></label>
      <label className="runs-search"><span>Search</span><div><Icon name="search" /><input aria-label="Search runs" onChange={(event) => resetPage(setQuery)(event.target.value)} placeholder="Search runs, run IDs, or metadata..." value={query} /></div></label>
    </section>

    {filtered.length === 0 ? <section className="state-panel compact"><span className="state-icon"><Icon name={runs.length ? "search" : "activity"} /></span><h2>{runs.length ? "No runs match these filters" : "No runs yet"}</h2><p>{runs.length ? "Clear filters or broaden the search to find another execution." : "Send an OTLP trace through the Collector to create the first run."}</p>{runs.length > 0 && <button className="button-secondary" onClick={clearFilters} type="button">Clear filters</button>}</section> :
      <article className="overview-panel runs-table-card">
        <div className="overview-table-scroll"><table className="runs-table"><thead><tr><th className="check-col"><input aria-label="Select all runs on this page" checked={allOnPage} onChange={togglePage} ref={headerCheckbox} type="checkbox" /></th><th>Status</th><th>Run ID</th><th>Workflow</th><th>Environment</th><th>Start time</th><th>Duration</th><th>Tool calls</th><th>Anomalies</th><th className="actions-col">Actions</th></tr></thead><tbody>{rows.map((run) => <RunRow checked={selected.has(run.run_id)} count={anomalies[run.run_id]} key={run.run_id} onToggle={() => toggleRow(run.run_id)} run={run} />)}</tbody></table></div>
        <footer className="runs-pagination"><span>Showing {firstShown}–{lastShown} of {filtered.length} run{filtered.length === 1 ? "" : "s"}{selected.size > 0 && ` · ${selected.size} selected`}</span><nav aria-label="Pagination"><button aria-label="Previous page" disabled={current === 1} onClick={() => setPage(current - 1)} type="button"><Icon className="prev" name="chevron" /></button>{pageItems(current, pageCount).map((item, index) => item === null ? <span className="ellipsis" key={`gap-${index}`}>…</span> : <button aria-current={item === current ? "page" : undefined} className={item === current ? "active" : ""} key={item} onClick={() => setPage(item)} type="button">{item}</button>)}<button aria-label="Next page" disabled={current === pageCount} onClick={() => setPage(current + 1)} type="button"><Icon className="next" name="chevron" /></button></nav></footer>
      </article>}
  </div>;
}

function RunRow({ run, count, checked, onToggle }: { run: RunSummary; count: number | null | undefined; checked: boolean; onToggle: () => void }) {
  const href = `/runs/${run.run_id}`; const name = run.workflow_name ? humanize(run.workflow_name) : runDisplayName(run); const fullId = run.external_run_id ?? run.run_id;
  const visual = workflowVisual(run.workflow_name ?? name); const env = run.environment;
  return <tr className={checked ? "selected" : ""}>
    <td className="check-col"><input aria-label={`Select ${name}`} checked={checked} onChange={onToggle} type="checkbox" /></td>
    <td><RunStatus status={run.status} /></td>
    <td><div className="run-id-cell"><Link className="overview-run-id" href={href} title={fullId}>{compactId(fullId)}</Link><CopyButton value={fullId} /></div></td>
    <td><Link className="overview-workflow" href={href}><span className={`tone-${visual.tone}`}><Icon name={visual.icon} /></span><div><strong>{name}</strong><small>{run.workflow_version ? `Version ${run.workflow_version}` : "Version not recorded"}</small></div></Link></td>
    <td>{env ? <span className={`env-pill env-${envTone(env)}`}><i />{humanize(env)}</span> : "—"}</td>
    <td className="muted-cell">{startFormat.format(Date.parse(run.started_at))}</td>
    <td>{formatDuration(run.metrics.total_duration_ms)}</td>
    <td>{run.metrics.tool_call_count}</td>
    <td>{count === undefined ? <i className="anomaly-pending" aria-label="Checking" /> : count ? <span className="anomaly-count"><Icon name="alert" />{count}</span> : <span className="muted-cell">—</span>}</td>
    <td className="actions-col"><Link className="overview-row-arrow" href={href} aria-label={`Open ${name}`}><Icon name="more" /></Link></td>
  </tr>;
}

function envTone(environment: string): string {
  const value = environment.toLowerCase();
  if (value.startsWith("prod")) return "green";
  if (value.startsWith("stag")) return "blue";
  if (value.startsWith("dev")) return "purple";
  return "slate";
}

function pageItems(current: number, total: number): Array<number | null> {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const items = new Set([1, total, current - 1, current, current + 1].filter((value) => value >= 1 && value <= total));
  const sorted = [...items].sort((a, b) => a - b); const result: Array<number | null> = [];
  sorted.forEach((value, index) => { if (index && value - sorted[index - 1] > 1) result.push(null); result.push(value); });
  return result;
}
