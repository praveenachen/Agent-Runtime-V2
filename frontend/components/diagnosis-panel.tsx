"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/icon";
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
    return <section className="rd-card rd-diagnosis diagnosis-loading" id="full-diagnosis" aria-label="Analyzing run"><div className="diagnosis-shimmer" /><div className="diagnosis-shimmer short" /><div className="diagnosis-shimmer" /></section>;
  }
  if (state.kind === "error") {
    return <section className="rd-card rd-diagnosis" id="full-diagnosis"><header className="rd-card-heading"><h2><Icon name="alert" /> Run diagnosis</h2></header><p className="diagnosis-muted">Analysis unavailable: {state.message}</p></section>;
  }

  const diagnosis = state.diagnosis; const items = diagnosis.evidence.items;
  if (!items.length) {
    return <section className="rd-card rd-diagnosis rd-diagnosis-clear" id="full-diagnosis"><header className="rd-card-heading"><h2><span className="rd-ok-icon"><Icon name="check" /></span> Run diagnosis</h2><span className="rd-confidence">Generated post-run · {diagnosis.provider}</span></header><p className="rd-clear-copy"><strong>No anomalies detected.</strong> {diagnosis.impact}</p></section>;
  }
  const confidence = diagnosis.inferred_causes[0]?.confidence;
  return <section className="rd-card rd-diagnosis" id="full-diagnosis">
    <header className="rd-card-heading"><h2><span className="rd-alert-icon"><Icon name="alert" /></span> Run diagnosis</h2>{confidence && <span className="rd-confidence"><i /> {confidence} confidence <small>(inferred cause)</small></span>}</header>
    <div className="rd-findings">{items.map((item) => <div className={`rd-finding severity-${item.severity}`} key={item.evidence_id}><Icon name="alert" /><div><strong>{item.anomaly_type.replaceAll("_", " ")}</strong><p>{item.observed_fact}</p></div><span className="rd-severity">{item.severity}</span></div>)}</div>
    <div className="rd-diagnosis-columns">
      <section><h3><Icon name="activity" /> Impact</h3><p>{diagnosis.impact}</p></section>
      <section><h3><Icon name="search" /> Likely cause <small>inferred</small></h3>{diagnosis.inferred_causes.length ? diagnosis.inferred_causes.map((cause) => <p key={cause.statement}>{cause.statement}<small>{cause.confidence} confidence</small></p>) : <p>Evidence is insufficient to infer a likely cause without guessing.</p>}</section>
      <section><h3><Icon name="spark" /> Suggested next steps <small>advisory</small></h3><ol>{diagnosis.suggested_investigations.map((step) => <li key={step}>{step}</li>)}</ol></section>
    </div>
    <details className="coverage-details"><summary>Evidence details and baseline coverage</summary><div className="finding-list">{items.map((item) => <Finding key={item.evidence_id} item={item} />)}</div>{diagnosis.evidence.baseline_coverage.length > 0 && <div>{diagnosis.evidence.baseline_coverage.map((coverage) => <span key={coverage.metric}><b>{coverage.metric.replaceAll("_", " ")}</b><small>{coverage.sample_size} samples · {coverage.confidence_label}</small></span>)}</div>}</details>
    <footer className="diagnosis-footer">Generated post-run · {diagnosis.provider}</footer>
  </section>;
}

function Finding({ item }: { item: EvidenceItem }) {
  const baseline = item.baseline_comparison;
  return <details className="finding">
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
