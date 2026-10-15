# Milestone 4 — Behavioral Analysis + Evidence-First Diagnosis

## Goal
Detect meaningful abnormal behavior using rules/statistics and explain it with evidence.

## Deliverables
- Rule detector with a small, explicit initial rule set.
- Statistical baseline service scoped initially by workflow + environment.
- Continuously updated Gold baseline metrics.
- Cold-start behavior: rules work immediately even without historical baselines.
- Baseline-dependent findings clearly indicate confidence/coverage when history is sparse.
- Evidence aggregator that combines graph facts, metrics, rule triggers, and baseline deviations.
- LLM diagnosis layer that receives only structured evidence and produces:
  - Observed
  - Impact
  - Likely cause
  - Suggested next steps
- UI integration on Run Detail and Overview/alerts where appropriate.

## Initial anomaly categories
- excessive retries
- repeated transition/loop
- unusual tool-call count
- latency spike
- cost/token spike
- missing expected/declared validation step when such an expectation is configured
- approval wait anomaly
- unexpected/rare handoff or path when historical evidence exists

## Constraints
- No ML anomaly detector.
- No LLM-first guessing.
- Do not present inferred causality as fact.
- Deep diagnosis is post-run.

## Tests
Use deterministic synthetic histories to prove baseline behavior and evidence generation.
