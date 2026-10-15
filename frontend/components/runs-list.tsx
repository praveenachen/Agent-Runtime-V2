"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { RunStatus } from "@/components/run-status";
import { Icon } from "@/components/ui/icon";
import { fetchRuns, formatDate, formatDuration, type RunSummary } from "@/lib/api";

type LoadState = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; runs: RunSummary[] };

export function RunsList() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [status, setStatus] = useState("all");
  const [workflow, setWorkflow] = useState("all");
  const [environment, setEnvironment] = useState("all");
  const [query, setQuery] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal).then((runs) => setState({ kind: "ready", runs })).catch((error: Error) => {
      if (error.name !== "AbortError") setState({ kind: "error", message: error.message });
    });
    return () => controller.abort();
  }, [reload]);

  const runs = useMemo(() => state.kind === "ready" ? state.runs : [], [state]);
  const workflows = useMemo(() => [...new Set(runs.map((run) => run.workflow_name).filter(Boolean))] as string[], [runs]);
  const environments = useMemo(() => [...new Set(runs.map((run) => run.environment).filter(Boolean))] as string[], [runs]);
  const filtered = useMemo(() => runs.filter((run) => {
    const matchesStatus = status === "all" || run.status === status;
    const matchesWorkflow = workflow === "all" || run.workflow_name === workflow;
    const matchesEnvironment = environment === "all" || run.environment === environment;
    const needle = query.trim().toLowerCase();
    const matchesQuery = !needle || [run.name, run.run_id, run.workflow_name, run.environment].some((value) => value?.toLowerCase().includes(needle));
    return matchesStatus && matchesWorkflow && matchesEnvironment && matchesQuery;
  }), [runs, status, workflow, environment, query]);

  const retry = () => { setState({ kind: "loading" }); setReload((value) => value + 1); };
  const clearFilters = () => { setStatus("all"); setWorkflow("all"); setEnvironment("all"); setQuery(""); };

  if (state.kind === "loading") return <div className="skeleton-stack" aria-label="Loading runs"><div className="skeleton-toolbar" />{Array.from({ length: 6 }, (_, index) => <div className="skeleton-row" key={index} />)}</div>;
  if (state.kind === "error") return <section className="state-panel" role="alert"><span className="state-icon danger"><Icon name="alert" /></span><h2>Runs are unavailable</h2><p>{state.message} Check that the local backend is running.</p><button className="button-secondary" onClick={retry} type="button">Try again</button></section>;

  return <>
    <section className="filter-bar" aria-label="Run filters">
      <label className="search-field"><Icon name="search" /><span className="sr-only">Search runs</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Search run ID, workflow, or environment" value={query} /></label>
      <label><span>Status</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">All statuses</option>{[...new Set(runs.map((run) => run.status))].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Workflow</span><select onChange={(event) => setWorkflow(event.target.value)} value={workflow}><option value="all">All workflows</option>{workflows.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Environment</span><select onChange={(event) => setEnvironment(event.target.value)} value={environment}><option value="all">All environments</option>{environments.map((value) => <option key={value}>{value}</option>)}</select></label>
      <span className="result-count">{filtered.length} of {runs.length}</span>
    </section>
    {filtered.length === 0 ? <section className="state-panel"><span className="state-icon"><Icon name={runs.length ? "search" : "activity"} /></span><h2>{runs.length ? "No runs match these filters" : "No runs yet"}</h2><p>{runs.length ? "Clear filters or broaden the search to find another execution." : "Send an OTLP trace through the Collector to create the first run."}</p>{runs.length > 0 && <button className="button-secondary" onClick={clearFilters} type="button">Clear filters</button>}</section> :
      <div className="run-table-wrap"><table className="run-table"><thead><tr><th>Run</th><th>Status</th><th>Environment</th><th>Started</th><th>Duration</th><th>Steps</th><th>Tokens</th><th aria-label="Open run" /></tr></thead><tbody>{filtered.map((run) => <tr key={run.run_id}><td><Link className="run-link" href={`/runs/${run.run_id}`}><strong>{run.name}</strong><span className="mono">{run.run_id}</span><small>{run.workflow_name ?? "Unspecified workflow"}</small></Link></td><td><RunStatus status={run.status} /></td><td><span className="environment-label"><i />{run.environment ?? "unknown"}</span></td><td className="mono subtle">{formatDate(run.started_at)}</td><td className="mono">{formatDuration(run.metrics.total_duration_ms)}</td><td className="mono">{run.metrics.step_count}</td><td className="mono">{run.metrics.total_tokens.toLocaleString()}</td><td><Link className="row-arrow" href={`/runs/${run.run_id}`} aria-label={`Open ${run.name}`}><Icon name="arrow" /></Link></td></tr>)}</tbody></table></div>}
  </>;
}
