"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ProjectScope } from "@/components/project-scope";
import { RunStatus } from "@/components/run-status";
import { CopyButton, KpiCard, compactId, humanize, workflowVisual, type KpiDelta } from "@/components/run-widgets";
import { Icon, type IconName } from "@/components/ui/icon";
import {
  fetchApprovals, fetchDiagnosis, fetchHealth, fetchPolicies, formatDate, formatDuration,
  type Approval, type EvidenceItem, type RunSummary,
} from "@/lib/api";
import { useProjectDiscovery } from "@/lib/project";
import { runDisplayName } from "@/lib/run-display";

type AlertItem = { run: RunSummary; evidence: EvidenceItem; generatedAt: string };
type RemoteState = { projectId: string; approvals: Approval[] | null; alerts: AlertItem[]; apiHealthy: boolean; controlAvailable: boolean; checkedAt: number };
type RangeKey = "7d" | "all";
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
type ActivityBucket = { key: number; label: string; title: string; count: number; successRate: number | null; averageLatency: number | null; toolCalls: number };

export function OverviewDashboard() {
  const { projectId, projects, runs: allRuns, loading, error } = useProjectDiscovery();
  const [remoteState, setRemoteState] = useState<RemoteState>({ projectId: "", approvals: null, alerts: [], apiHealthy: false, controlAvailable: false, checkedAt: 0 });
  const [range, setRange] = useState<RangeKey>("7d");
  const [now] = useState(() => Date.now());
  const projectRuns = useMemo(() => projectId ? (allRuns ?? []).filter((run) => run.project_id === projectId).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)) : [], [allRuns, projectId]);
  const runs = useMemo(() => range === "7d" ? projectRuns.filter((run) => Date.parse(run.started_at) >= now - WEEK_MS) : projectRuns, [projectRuns, range, now]);
  const previousRuns = useMemo(() => range === "7d" ? projectRuns.filter((run) => { const started = Date.parse(run.started_at); return started >= now - 2 * WEEK_MS && started < now - WEEK_MS; }) : [], [projectRuns, range, now]);
  const heading = <OverviewHeading range={range} onRange={setRange} />;
  const buckets = useMemo(() => activityBuckets(runs, range === "7d" ? { start: now - WEEK_MS, end: now } : undefined), [runs, range, now]);
  const scopedRemote = remoteState.projectId === projectId ? remoteState : null;

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    const approvalRequest = fetchApprovals(projectId, controller.signal);
    const policyRequest = fetchPolicies(projectId, controller.signal);
    const healthRequest = fetchHealth(controller.signal);
    const diagnosisRequest = Promise.all(runs.slice(0, 8).map(async (run) => {
      try {
        const diagnosis = await fetchDiagnosis(run.run_id, controller.signal);
        return diagnosis.evidence.items.map((evidence) => ({ run, evidence, generatedAt: diagnosis.generated_at }));
      } catch { return []; }
    }));
    Promise.allSettled([approvalRequest, policyRequest, healthRequest, diagnosisRequest]).then((results) => {
      if (controller.signal.aborted) return;
      const [approvalsResult, policiesResult, healthResult, diagnosesResult] = results;
      setRemoteState({
        projectId,
        approvals: approvalsResult.status === "fulfilled" ? approvalsResult.value : null,
        alerts: diagnosesResult.status === "fulfilled" ? diagnosesResult.value.flat().slice(0, 3) : [],
        apiHealthy: healthResult.status === "fulfilled" && healthResult.value.status === "ok",
        controlAvailable: approvalsResult.status === "fulfilled" && policiesResult.status === "fulfilled",
        checkedAt: Date.now(),
      });
    });
    return () => controller.abort();
  }, [projectId, runs]);

  if (error) return <>{heading}<section className="state-panel compact"><span className="state-icon danger"><Icon name="alert" /></span><h2>Runtime data unavailable</h2><p>{error}</p></section></>;
  if (loading || (projects.length === 1 && !projectId)) return <>{heading}<div className="skeleton-stack"><div className="skeleton-metrics" /><div className="skeleton-graph" /><div className="skeleton-row" /></div></>;
  if (!projectId) return <>{heading}<ProjectScope /><section className="state-panel compact"><span className="state-icon"><Icon name="shield" /></span><h2>Select a recorded project</h2><p>Overview statistics are intentionally scoped to one project.</p></section></>;

  const succeeded = runs.filter((run) => run.status.toLowerCase() === "succeeded").length;
  const successRate = runs.length ? (succeeded / runs.length) * 100 : null;
  const durations = runs.map((run) => run.metrics.total_duration_ms).filter(Number.isFinite).sort((a, b) => a - b);
  const averageLatency = durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null;
  const medianLatency = percentile(durations, 0.5); const p95Latency = percentile(durations, 0.95);
  const totalToolCalls = runs.reduce((sum, run) => sum + run.metrics.tool_call_count, 0);
  const recentRuns = runs.slice(0, 8); const showTokens = recentRuns.some((run) => run.metrics.total_tokens !== null);

  const current = summarize(runs); const previous = summarize(previousRuns);
  const { earlier, later, basis } = trendWindows(runs, previousRuns, current, previous);
  const deltas = { count: percentDelta(later.count, earlier.count, basis), rate: percentDelta(later.rate, earlier.rate, basis), latency: percentDelta(later.latency, earlier.latency, basis), tools: percentDelta(later.tools, earlier.tools, basis) };

  return <><div className="overview-dashboard-heading">{heading}</div><div className="overview-dashboard">
    <p className="overview-context"><Icon name="shield" /> {range === "7d" ? "Showing recorded telemetry from the last 7 days for the current project" : "Showing all recorded telemetry for the current project"}</p>
    <section className="overview-kpi-grid" aria-label="Runtime metrics">
      <KpiCard icon="layers" tone="blue" label="Total runs" delta={deltas.count} seed={3} value={String(runs.length)} subtitle={`${runs.length} recorded logical run${runs.length === 1 ? "" : "s"}`} />
      <KpiCard icon="checkCircle" tone="green" label="Success rate" delta={deltas.rate} seed={7} value={successRate === null ? "—" : `${successRate.toFixed(1)}%`} subtitle={runs.length ? `${succeeded} succeeded / ${runs.length} total` : "No recorded outcomes"} />
      <KpiCard icon="bolt" tone="purple" label="Avg. latency" delta={deltas.latency} seed={11} value={averageLatency === null ? "—" : formatDuration(averageLatency)} subtitle={medianLatency === null || p95Latency === null ? "No recorded durations" : `Median ${formatDuration(medianLatency)} · p95 ${formatDuration(p95Latency)}`} />
      <KpiCard icon="tool" tone="amber" label="Tool calls" delta={deltas.tools} seed={19} value={totalToolCalls.toLocaleString()} subtitle={`${totalToolCalls.toLocaleString()} recorded tool call${totalToolCalls === 1 ? "" : "s"}`} />
    </section>

    <section className="overview-primary-grid">
      <article className="overview-panel activity-panel"><PanelHeading title="Run activity" copy="Recorded runs, success rate, and average latency over time." aside={<ActivityLegend />} />{buckets.length ? <ActivityChart buckets={buckets} /> : <CompactEmpty title="No run activity yet" copy="The chart appears after the first recorded run." />}</article>
      <ApprovalsPanel approvals={scopedRemote?.approvals ?? null} now={scopedRemote?.checkedAt ?? 0} />
    </section>

    <section className="overview-lower-grid">
      <RecentRunsTable runs={recentRuns} showTokens={showTokens} />
      <div className="overview-side-stack"><RuntimeHealth runs={runs} state={scopedRemote} /><AlertsPanel alerts={scopedRemote?.alerts ?? []} loading={!scopedRemote} now={scopedRemote?.checkedAt ?? 0} /></div>
    </section>
  </div></>;
}


function OverviewHeading({ range, onRange }: { range: RangeKey; onRange: (range: RangeKey) => void }) {
  return <header className="page-heading">
    <div><h1>Overview</h1><p className="muted">Monitor, debug, and control your AI agent workflows.</p></div>
    <div className="page-heading-actions">
      <label className="range-filter"><Icon name="calendar" /><select aria-label="Time range" onChange={(event) => onRange(event.target.value as RangeKey)} value={range}><option value="7d">Last 7 days</option><option value="all">All time</option></select><Icon className="chevron" name="chevron" /></label>
    </div>
  </header>;
}

function summarize(runs: RunSummary[]): { count: number; rate: number | null; latency: number | null; tools: number } {
  const durations = runs.map((run) => run.metrics.total_duration_ms).filter(Number.isFinite);
  return { count: runs.length, rate: runs.length ? (runs.filter((run) => run.status.toLowerCase() === "succeeded").length / runs.length) * 100 : null, latency: durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null, tools: runs.reduce((sum, run) => sum + run.metrics.tool_call_count, 0) };
}

// Compares the selected period with the previous 7 days when that period has runs; otherwise the later half of the
// recorded span is compared with the earlier half. Both use only recorded runs.
function trendWindows(runs: RunSummary[], previousRuns: RunSummary[], current: ReturnType<typeof summarize>, previous: ReturnType<typeof summarize>) {
  if (previousRuns.length) return { earlier: previous, later: current, basis: "versus the previous 7 days" };
  const times = runs.map((run) => Date.parse(run.started_at)); const middle = (Math.min(...times) + Math.max(...times)) / 2;
  const early = runs.filter((run) => Date.parse(run.started_at) < middle); const late = runs.filter((run) => Date.parse(run.started_at) >= middle);
  return { earlier: summarize(early), later: summarize(late), basis: "of the later half of recorded runs versus the earlier half" };
}

// Real change versus the comparison period; null (hidden) when there is nothing valid to compare against.
function percentDelta(current: number | null, previous: number | null, basis: string): KpiDelta | null {
  if (current === null || previous === null || previous === 0) return null;
  const change = ((current - previous) / previous) * 100;
  return { value: `${Math.abs(change) < 10 ? Math.abs(change).toFixed(1) : Math.round(Math.abs(change))}%`, up: change >= 0, basis };
}

function ActivityLegend() {
  return <div className="activity-legend"><span><i className="bars" /> Runs</span><span><i className="success" /> Success rate</span><span><i className="latency" /> Avg. latency <small>relative scale</small></span></div>;
}

type ChartBin = { count: number; factor: number; rate: number; latency: number; time: number; source: ActivityBucket };

// Presentational resampling: each recorded day is drawn as a block of narrow bars at that day's true count, and the
// success/latency lines are interpolated between days so the chart reads as continuous. Headline totals elsewhere on the page come straight from recorded runs.
function chartBins(buckets: ActivityBucket[]): ChartBin[] {
  const factor = Math.max(1, Math.ceil(28 / buckets.length)); const total = buckets.length * factor;
  const smooth = Array.from({ length: total }, (_, index) => buckets[Math.floor(index / factor)].count);
  const interpolate = (pick: (bucket: ActivityBucket) => number | null) => {
    const points = buckets.flatMap((bucket, index) => { const value = pick(bucket); return value === null ? [] : [{ x: (index + 0.5) / buckets.length, y: value }]; });
    return (x: number) => { if (!points.length) return 0; if (x <= points[0].x) return points[0].y; for (let i = 1; i < points.length; i += 1) if (x <= points[i].x) { const a = points[i - 1]; const b = points[i]; return a.y + (b.y - a.y) * ((x - a.x) / (b.x - a.x)); } return points[points.length - 1].y; };
  };
  const rate = interpolate((bucket) => bucket.successRate); const latency = interpolate((bucket) => bucket.averageLatency);
  const firstKey = buckets[0].key; const lastKey = buckets[buckets.length - 1].key;
  return smooth.map((count, index) => ({ count, factor, rate: rate((index + 0.5) / total), latency: latency((index + 0.5) / total), time: firstKey + (lastKey - firstKey) * (total > 1 ? index / (total - 1) : 0), source: buckets[Math.floor(index / factor)] }));
}

// Y-axis ceiling derived from the visible buckets: the smallest clean value about 5-20% above the maximum (21 -> 25, 33 -> 40, 47 -> 50).
function niceAxis(max: number): { top: number; step: number; intervals: number } {
  if (max <= 4) return { top: 4, step: 1, intervals: 4 };
  const target = max * 1.05; const magnitude = 10 ** Math.floor(Math.log10(target));
  const top = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((multiplier) => multiplier * magnitude).find((candidate) => candidate >= target) ?? 10 * magnitude;
  const cleanSteps = [1, 2, 2.5, 5];
  const intervals = [4, 5, 3, 2, 6].find((count) => { const step = top / count; const base = step / 10 ** Math.floor(Math.log10(step)); return cleanSteps.some((clean) => Math.abs(clean - base) < 1e-9); }) ?? 4;
  return { top, step: top / intervals, intervals };
}

function smoothPath(points: Array<[number, number]>, min: number, max: number): string {
  if (points.length < 2) return "";
  const clamp = (value: number) => Math.min(max, Math.max(min, value));
  let path = `M${points[0][0].toFixed(1)},${points[0][1].toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] ?? points[i]; const p1 = points[i]; const p2 = points[i + 1]; const p3 = points[i + 2] ?? p2;
    path += ` C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)},${clamp(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)},${clamp(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return path;
}

function ActivityChart({ buckets }: { buckets: ActivityBucket[] }) {
  const width = 1000; const height = 262; const left = 38; const right = 46; const top = 12; const bottom = 30;
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const bins = chartBins(buckets); const step = plotWidth / bins.length; const axis = niceAxis(Math.max(...bins.map((bin) => bin.count)));
  const maxLatency = Math.max(...bins.map((bin) => bin.latency), 1); const x = (index: number) => left + step * index + step / 2; const base = top + plotHeight;
  const successPoints = bins.map((bin, index): [number, number] => [x(index), base - (bin.rate / 100) * plotHeight]); const latencyPoints = bins.map((bin, index): [number, number] => [x(index), base - (bin.latency / maxLatency) * plotHeight * 0.5 - plotHeight * 0.04]);
  const perBucket = bins.length / buckets.length; const thin = Math.ceil(buckets.length / 8); const labelFor = (index: number) => index % perBucket === Math.floor(perBucket / 2) && Math.floor(index / perBucket) % thin === 0 ? bins[index].source.label : null; const ticks = Array.from({ length: axis.intervals + 1 }, (_, index) => index);
  return <div className="activity-chart-wrap"><svg className="activity-chart" role="img" aria-label="Recorded project run activity" viewBox={`0 0 ${width} ${height}`}>
    <defs><linearGradient id="activity-bar" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#3d7bf0" /><stop offset="1" stopColor="#1a3f9e" /></linearGradient></defs>
    {ticks.map((tick) => { const y = base - (plotHeight * tick) / axis.intervals; return <g key={tick}><line x1={left} x2={width - right} y1={y} y2={y} /><text x={left - 9} y={y + 3.5} textAnchor="end">{formatAxis(axis.step * tick)}</text><text x={width - right + 9} y={y + 3.5}>{Math.round((tick / axis.intervals) * 100)}%</text></g>; })}
    {bins.map((bin, index) => { const barHeight = (bin.count / axis.top) * plotHeight; return <g className="activity-bucket" key={index}><rect className="hit" x={left + step * index} y={top} width={step} height={plotHeight} /><rect className="bar" x={x(index) - step * 0.46} y={base - barHeight} width={step * 0.92} height={Math.max(bin.count > 0.05 ? 2 : 0, barHeight)} rx="1.8" fill="url(#activity-bar)" />{labelFor(index) && <text className="axis-label" x={x(index)} y={height - 9} textAnchor="middle">{labelFor(index)}</text>}<title>{bin.source.count ? `${bin.source.title}: ${bin.source.count} run${bin.source.count === 1 ? "" : "s"}, ${formatCompact(bin.source.successRate ?? 0)}% success, ${formatDuration(bin.source.averageLatency ?? 0)} avg. latency` : `${bin.source.title}: no recorded runs`}</title></g>; })}
    <path className="success-line" d={smoothPath(successPoints, top, base)} /><path className="latency-line" d={smoothPath(latencyPoints, top, base)} />
    {bins.map((_, index) => <g key={`points-${index}`}><circle className="success-point" cx={successPoints[index][0]} cy={successPoints[index][1]} r="2.2" /><circle className="latency-point" cx={latencyPoints[index][0]} cy={latencyPoints[index][1]} r="2" /></g>)}
  </svg></div>;
}

function ApprovalsPanel({ approvals, now }: { approvals: Approval[] | null; now: number }) {
  return <article className="overview-panel approvals-panel"><PanelHeading title="Pending approvals" badge={approvals?.length ?? null} link="/approvals" linkText="View all →" />{approvals === null ? <div className="overview-mini-loading"><i /><i /><i /></div> : approvals.length === 0 ? <CompactEmpty icon="check" title="No actions waiting" copy="Matching REQUIRE_APPROVAL actions will appear here." /> : <><div className="overview-approval-list">{approvals.slice(0, 3).map((approval) => <div key={approval.id}><span className={`approval-item-icon tone-${approvalIcon(approval)}`}><Icon name={approvalIcon(approval)} /></span><div className="approval-text"><div className="approval-head"><strong>{humanize(approval.action_summary)}</strong><time>{relativeTime(approval.created_at, now)}</time></div><small>{approvalContext(approval)}</small></div><Link className="approval-review" href="/approvals">Review</Link></div>)}</div>{approvals.length > 3 && <Link className="approval-overflow" href="/approvals"><Icon name="chevron" /> {approvals.length - 3} other request{approvals.length - 3 === 1 ? "" : "s"}</Link>}</>}</article>;
}

function RecentRunsTable({ runs, showTokens }: { runs: RunSummary[]; showTokens: boolean }) {
  return <article className="overview-panel recent-runs-panel"><PanelHeading title="Recent runs" copy="Latest recorded workflows for the current project." link="/runs" linkText="View all runs →" />{runs.length === 0 ? <CompactEmpty title="No runs recorded" copy="Recent runs appear after telemetry is ingested." /> : <div className="overview-table-scroll"><table className="overview-runs-table"><thead><tr><th>Status</th><th>Run ID</th><th>Agent / Workflow</th><th>Start time</th><th>Duration</th><th>Tool calls</th>{showTokens && <th>Tokens</th>}<th aria-label="Actions" /></tr></thead><tbody>{runs.map((run) => { const href = `/runs/${run.run_id}`; const name = run.workflow_name ? humanize(run.workflow_name) : runDisplayName(run); const fullId = run.external_run_id ?? run.run_id; const visual = workflowVisual(run.workflow_name ?? name); return <tr key={run.run_id}><td><Link href={href}><RunStatus status={run.status} /></Link></td><td><div className="run-id-cell"><Link className="overview-run-id" href={href} title={fullId}>{compactId(fullId)}</Link><CopyButton value={fullId} /></div></td><td><Link className="overview-workflow" href={href}><span className={`tone-${visual.tone}`}><Icon name={visual.icon} /></span><div><strong>{name}</strong><small>{[run.workflow_version ? `Version ${run.workflow_version}` : "Version not recorded", run.environment].filter(Boolean).join(" · ")}</small></div></Link></td><td><Link href={href}>{formatDate(run.started_at)}</Link></td><td><Link href={href}>{formatDuration(run.metrics.total_duration_ms)}</Link></td><td><Link href={href}>{run.metrics.tool_call_count}</Link></td>{showTokens && <td><Link href={href}>{run.metrics.total_tokens === null ? "—" : run.metrics.total_tokens.toLocaleString()}</Link></td>}<td><Link className="overview-row-arrow" href={href} aria-label={`Open ${runDisplayName(run)}`}><Icon name="more" /></Link></td></tr>; })}</tbody></table></div>}</article>;
}

function RuntimeHealth({ runs, state }: { runs: RunSummary[]; state: RemoteState | null }) {
  const latest = runs[0]?.started_at; const recent = latest && state ? state.checkedAt - Date.parse(latest) <= 24 * 60 * 60 * 1000 : false;
  const checks = [
    { label: "Agent Runtime API", ok: state?.apiHealthy ?? false, detail: state ? state.apiHealthy ? "Healthy" : "Unavailable" : "Checking" },
    { label: "Telemetry", ok: recent, detail: latest ? recent ? "Receiving data" : `Last seen ${relativeTime(latest, state?.checkedAt ?? 0)}` : "No project runs" },
    { label: "Runtime control", ok: state?.controlAvailable ?? false, detail: state ? state.controlAvailable ? "Available" : "Unavailable" : "Checking" },
    { label: "Approval service", ok: state?.approvals != null, detail: state ? state.approvals != null ? "Healthy" : "Unavailable" : "Checking" },
  ];
  return <article className="overview-panel health-panel"><PanelHeading title="Runtime health" badge={checks.every((check) => check.ok) ? "All systems operational" : null} badgeTone="ok" /><div className="health-check-list">{checks.map((check) => <div key={check.label}><span className={check.ok ? "healthy" : "unavailable"}><Icon name={check.ok ? "check" : "alert"} /></span><strong>{check.label}</strong><small>{check.detail}</small></div>)}</div></article>;
}

function AlertsPanel({ alerts, loading, now }: { alerts: AlertItem[]; loading: boolean; now: number }) {
  return <article className="overview-panel alerts-panel"><PanelHeading title="Recent alerts" link="/runs" linkText="View all →" />{loading ? <div className="overview-mini-loading"><i /><i /></div> : alerts.length === 0 ? <CompactEmpty icon="check" title="No recent findings" copy="No evidence-backed diagnosis findings were recorded in recent runs." /> : <div className="overview-alert-list">{alerts.map((alert) => <Link href={`/runs/${alert.run.run_id}`} key={`${alert.run.run_id}-${alert.evidence.evidence_id}`}><span className={`alert-severity severity-${alert.evidence.severity}`}><Icon name="alert" /></span><div><strong>{humanize(alert.evidence.anomaly_type)}</strong><small>{alert.evidence.observed_fact}</small></div><time>{relativeTime(alert.generatedAt || alert.run.started_at, now)}</time></Link>)}</div>}</article>;
}

function PanelHeading({ title, copy, badge, badgeTone = "count", link, linkText, aside }: { title: string; copy?: string; badge?: string | number | null; badgeTone?: "count" | "ok"; link?: string; linkText?: string; aside?: ReactNode }) {
  return <header className="overview-panel-heading"><div><h2>{title}{badge !== null && badge !== undefined && <span className={`heading-badge heading-badge-${badgeTone}`}>{badge}</span>}</h2>{copy && <p>{copy}</p>}</div>{aside}{link && <Link href={link}>{linkText}</Link>}</header>;
}

function CompactEmpty({ icon, title, copy }: { icon?: IconName; title: string; copy: string }) { return <div className="overview-compact-empty">{icon && <Icon name={icon} />}<div><strong>{title}</strong><p>{copy}</p></div></div>; }

function activityBuckets(runs: RunSummary[], window?: { start: number; end: number }): ActivityBucket[] {
  if (!runs.length) return [];
  const times = runs.map((run) => Date.parse(run.started_at));
  const first = window ? Math.min(window.start, ...times) : Math.min(...times); const last = window ? Math.max(window.end, ...times) : Math.max(...times);
  const stepDays = (last - first) > 90 * 86_400_000 ? 7 : 1;
  const dayStart = (time: number) => { const date = new Date(time); date.setHours(0, 0, 0, 0); return date; };
  const keys: number[] = []; const cursor = dayStart(first);
  while (cursor.getTime() <= last) { keys.push(cursor.getTime()); cursor.setDate(cursor.getDate() + stepDays); }
  const visible = keys.slice(-36); const format = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" });
  const groups = new Map<number, RunSummary[]>(visible.map((key) => [key, []]));
  runs.forEach((run) => { const started = Date.parse(run.started_at); const key = [...visible].reverse().find((candidate) => candidate <= started); if (key !== undefined) groups.get(key)!.push(run); });
  return visible.map((key) => { const items = groups.get(key) ?? []; const succeeded = items.filter((run) => run.status.toLowerCase() === "succeeded").length; const label = format.format(key); return { key, label, title: stepDays > 1 ? `Week of ${label}` : label, count: items.length, successRate: items.length ? (succeeded / items.length) * 100 : null, averageLatency: items.length ? items.reduce((sum, run) => sum + run.metrics.total_duration_ms, 0) / items.length : null, toolCalls: items.reduce((sum, run) => sum + run.metrics.tool_call_count, 0) }; });
}

function percentile(values: number[], percentileValue: number): number | null { if (!values.length) return null; const index = (values.length - 1) * percentileValue; const lower = Math.floor(index); const upper = Math.ceil(index); return values[lower] + (values[upper] - values[lower]) * (index - lower); }
function relativeTime(value: string, now: number): string { const delta = now - Date.parse(value); const minutes = Math.max(0, Math.floor(delta / 60_000)); if (minutes < 1) return "just now"; if (minutes < 60) return `${minutes}m ago`; const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours}h ago`; return `${Math.floor(hours / 24)}d ago`; }
function formatAxis(value: number): string { return Number.isInteger(value) ? String(value) : value.toFixed(1); }
function formatCompact(value: number): string { return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1); }
function approvalContext(approval: Approval): string { return [approval.workflow_name && humanize(approval.workflow_name), approval.tool_name && humanize(approval.tool_name), approval.operation && humanize(approval.operation)].filter(Boolean).join(" · ") || approval.agent_name || "Context not recorded"; }
function approvalIcon(approval: Approval): IconName { const context = `${approval.tool_name ?? ""} ${approval.operation ?? ""} ${approval.action_summary}`.toLowerCase(); if (context.includes("github") || context.includes("code")) return "code"; if (context.includes("notion") || context.includes("database")) return "database"; return "approval"; }
