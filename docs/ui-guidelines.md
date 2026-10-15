# Agent Runtime — UI / Design Guidelines

## Product personality
Modern infrastructure tooling with a low learning curve.

The UI should feel:
- professional
- dark-mode-first
- calm and premium
- data-rich without being cluttered
- intuitive without extensive onboarding

## Visual direction
- deep slate/navy surfaces
- restrained blue/teal as primary accents
- green = healthy/success
- amber = caution/running
- red = failure/high-risk
- purple = replay/approval/special state where appropriate
- rounded but not playful cards
- thin separators, subtle borders, minimal shadows
- strong type hierarchy

## Information architecture
Primary nav:
- Overview
- Runs
- Policies
- Approvals
- Compare
- Settings

Global top bar:
- project selector
- global search
- notification bell with approval/alert count
- profile/org menu

## UX principles
1. Run-centric debugging.
2. Progressive disclosure: summary first, raw trace on demand.
3. High-risk actions must be obvious and actionable.
4. Important states always have text labels; do not rely on color alone.
5. Use notifications for approvals and important alerts.
6. Avoid dashboard vanity metrics that do not drive action.
7. Keep common workflows within 1–2 clicks where possible.

## Reference screens
### Overview
- 4 compact KPI cards
- run activity trend
- recent runs table
- pending approvals
- alerts
- system health

### Runs
- filters for project/workflow/environment/status/date/search
- rich run table
- anomaly count column
- status badges

### Run detail
- execution graph is visual focal point
- diagnosis immediately below/adjacent
- metric summary panel
- step timeline / events
- Compare / Replay / Raw trace actions

### Runtime Diff
- original vs replay
- config changes
- metric deltas
- side-by-side execution path
- trace differences
- replay mode
- concise behavioral summary

### Approvals + Policies
- approval inbox and policy editor may share a workspace
- approvals show side effect, confidence, risk, workflow, and clear Approve/Reject controls
- policy builder uses human-readable deterministic rules

## Implementation notes
- Next.js + React + TypeScript is a good fit.
- Build reusable primitives: Card, Badge, MetricCard, RunStatus, DataTable, Timeline, GraphNode, PolicyRule, ApprovalCard.
- Keep graph interaction simple initially: pan/zoom/select node; avoid overbuilt node editors.
- Desktop-first v1.
