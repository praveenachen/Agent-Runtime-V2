"use client";

import { useEffect, useState } from "react";

import { fetchDiagnosis, type Diagnosis, type EvidenceItem } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; diagnosis: Diagnosis };

export function DiagnosisPanel({ runId }: { runId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    fetchDiagnosis(runId, controller.signal)
      .then((diagnosis) => setState({ kind: "ready", diagnosis }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState({ kind: "error", message: error.message });
      });
    return () => controller.abort();
  }, [runId]);

  if (state.kind === "loading") {
    return <aside className="diagnosis-panel diagnosis-loading" aria-label="Analyzing run"><div className="diagnosis-shimmer" /><div className="diagnosis-shimmer short" /><div className="diagnosis-shimmer" /></aside>;
  }
  if (state.kind === "error") {
    return <aside className="diagnosis-panel"><p className="eyebrow">Diagnosis</p><h2>Analysis unavailable</h2><p className="diagnosis-muted">{state.message}</p></aside>;
  }

  const diagnosis = state.diagnosis;
  const highest = diagnosis.evidence.items[0]?.severity;
  return <aside className="diagnosis-panel">
    <header className="diagnosis-heading"><div><p className="eyebrow">Evidence-first diagnosis</p><h2>{diagnosis.evidence.items.length ? `${diagnosis.evidence.items.length} finding${diagnosis.evidence.items.length === 1 ? "" : "s"}` : "No anomalies detected"}</h2></div><span className={`diagnosis-state severity-${highest ?? "clear"}`}>{highest ?? "clear"}</span></header>
    <p className="impact-copy">{diagnosis.impact}</p>
    {diagnosis.evidence.items.length > 0 && <div className="finding-list">{diagnosis.evidence.items.map((item) => <Finding key={item.evidence_id} item={item} />)}</div>}
    <section className="diagnosis-section"><h3>Likely cause <span>inferred</span></h3>{diagnosis.inferred_causes.length ? <ul>{diagnosis.inferred_causes.map((cause) => <li key={cause.statement}>{cause.statement}<small>{cause.confidence} confidence · evidence {cause.supporting_evidence_ids.join(", ")}</small></li>)}</ul> : <p className="diagnosis-muted">Evidence is insufficient to infer a likely cause without guessing.</p>}</section>
    <section className="diagnosis-section"><h3>Suggested investigation <span>advisory</span></h3><ul>{diagnosis.suggested_investigations.map((step) => <li key={step}>{step}</li>)}</ul></section>
    <details className="coverage-details"><summary>Baseline coverage</summary><div>{diagnosis.evidence.baseline_coverage.map((coverage) => <span key={coverage.metric}><b>{coverage.metric.replaceAll("_", " ")}</b><small>{coverage.sample_size} samples · {coverage.confidence_label}</small></span>)}</div></details>
    <footer className="diagnosis-footer">Generated post-run · {diagnosis.provider}</footer>
  </aside>;
}

function Finding({ item }: { item: EvidenceItem }) {
  const baseline = item.baseline_comparison;
  return <details className="finding" open={item.severity === "critical" || item.severity === "high"}>
    <summary><span className={`finding-mark severity-${item.severity}`} /><div><strong>{item.anomaly_type.replaceAll("_", " ")}</strong><small>{item.detector_type} detector · {item.severity}</small></div><span className="finding-expand">+</span></summary>
    <div className="finding-body"><p><b>Observed</b>{item.observed_fact}</p>{baseline && <p><b>Baseline</b>Median {formatValue(baseline.median)} · p90 {formatValue(baseline.p90)} · {baseline.sample_size} samples ({baseline.confidence_label} confidence)</p>}{item.affected_node_ids.length > 0 && <p><b>Affected steps</b><span className="node-refs">{item.affected_node_ids.map(shortId).join(", ")}</span></p>}{item.recommendation && <p><b>Next step</b>{item.recommendation}</p>}</div>
  </details>;
}

function shortId(value: string) {
  return value.split(":").at(-1)?.slice(0, 10) ?? value;
}

function formatValue(value: number) {
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}
