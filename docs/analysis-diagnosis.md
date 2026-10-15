# Behavioral Analysis and Evidence-First Diagnosis Contract

This contract implements Milestone 4 as a post-run Gold projection. It does not perform during-run
control, policy evaluation, approval orchestration, or automatic remediation.

## Detection layers

The analysis service runs two independent detector types over a completed Gold run:

- deterministic rules provide cold-start findings without history;
- transparent statistical detectors compare eligible metrics with compatible historical runs.

Detectors emit observed evidence only. The evidence aggregator builds the package consumed by an
explainer. An LLM adapter may explain that package, but it does not receive unrestricted raw
telemetry and cannot create detector findings. The default explainer is deterministic.

## Baseline scope and statistics

The baseline key contains workflow and environment, plus workflow version, prompt version, and model
when supplied. Missing optional dimensions use an explicit wildcard. This prevents known incompatible
versions from being mixed while making sparse coverage visible.

Eligible metrics are total duration, declared cost, total tokens, tool calls, retries, handoffs, step
count, and parent-depth path length. Each metric stores sample size, median, p90, median absolute
deviation, minimum, maximum, and a continuous confidence score. A target run is excluded from its
comparison baseline.

There is no artificial fixed warm-up gate. One historical sample is labeled `insufficient` because a
deviation distribution cannot be estimated. Confidence then grows with sample count and is always
included with a finding. A statistical finding requires the current value to exceed both the p90 and
the robust `median + 3 * MAD` limit.

## Cold-start rules

The initial explicit rules detect:

- three or more retries;
- two or more repeated semantic transitions;
- twenty or more tool calls;
- any recorded run failure/error;
- configured validation checkpoints that are absent;
- approval wait of five minutes or more.

Validation is evaluated only when the RUN event declares
`agent.runtime.expected_validation_steps` as a list or comma-separated string.

## Evidence and diagnosis

Every evidence item contains detector/anomaly type, severity, an observed fact, metric and graph
support, affected node IDs, an optional baseline comparison with sample size/confidence, and an
advisory recommendation. Detector evidence never contains an inferred cause.

The diagnosis record separately stores:

- observed facts copied from evidence;
- impact;
- likely causes explicitly marked as inference with supporting evidence IDs;
- suggested investigations marked advisory;
- whether the available evidence is sufficient.

Inference references that do not resolve to evidence in the package are discarded before storage.
No hidden chain-of-thought is requested or stored.

## Storage and API

Gold projections are stored as workflow baselines and run diagnoses behind the telemetry analytics
store. Local development uses `gold-baselines.jsonl` and `gold-diagnoses.jsonl`; production uses the
Databricks merge/query boundary.

- `GET /api/v1/runs/{run_id}/diagnosis`
- `GET /api/v1/runs/{run_id}/anomalies`
- `GET /api/v1/runs/{run_id}/evidence`

Baseline projections refresh whenever Gold runs are materialized and again before diagnosis. Diagnosis
itself remains on-demand and post-run. The same services can later be invoked by a scheduled Databricks
job without changing detector contracts.
