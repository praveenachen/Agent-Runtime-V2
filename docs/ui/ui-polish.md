# Agent Runtime — UI Polish Contract

## Purpose

The screenshots in `docs/ui/references/` define the desired visual direction for Agent Runtime.

They are **design references, not pixel-perfect implementation requirements**.

Use them to guide:

- information hierarchy
- spacing and density
- typography
- dark-theme treatment
- card and panel styling
- status colors
- sidebar and navigation
- table styling
- execution-graph presentation
- Runtime Diff presentation
- notifications
- policy and approval UX

Do **not** blindly copy:

- placeholder company/project names
- fake run IDs or example data
- controls that do not match the implemented product
- metrics that do not exist in the current backend
- decorative widgets that do not improve the user workflow

The implemented product and current backend contracts remain the source of truth.

---

## Product Design Goal

Agent Runtime should feel like:

> **Modern infrastructure tooling without infrastructure-tool complexity.**

The UI should be:

- modern
- professional
- technical
- calm
- intuitive
- cohesive
- responsive
- information-dense only where useful

It should not require extensive practice to understand or navigate.

Avoid the cognitive overload common in dense enterprise infrastructure products.

---

## Core UX Questions

Every major visible element should help the user answer at least one of:

1. **What happened?**
2. **Why did it happen?**
3. **What changed?**
4. **What can I do about it?**

If an element does not support one of these workflows, remove it or de-emphasize it.

---

## Visual System

### Surfaces

Prefer:

- dark charcoal / slate backgrounds
- slightly lighter layered panels
- subtle borders
- restrained shadows
- clear panel hierarchy

Avoid:

- pure black everywhere
- excessive gradients
- heavy glassmorphism
- overly glowing/neon surfaces
- cards around every single piece of text

### Accent colors

Use accents intentionally:

- blue / teal: navigation, neutral active states, primary actions
- green: successful or healthy states
- amber: warning / needs attention
- red: failure, destructive action, blocked/high-risk state
- purple: sparingly for semantic differentiation where useful

Status color must communicate meaning, not decoration.

### Typography

Use a clean sans-serif typeface for the interface.

Use monospace selectively for:

- run IDs
- trace/span IDs
- technical metadata
- code-like policy expressions
- raw telemetry values

Maintain a clear hierarchy between:

- page titles
- section titles
- primary values
- supporting metadata
- low-priority technical detail

### Spacing

Prefer breathing room over visual density.

Use a consistent spacing scale across:

- page gutters
- cards
- table rows
- forms
- graph panels
- metadata sections

---

## Global Shell

The global shell should include:

- product identity
- project scope
- primary navigation
- global search if implemented
- notification indicator
- user/settings area if implemented

Primary navigation should remain easy to scan.

Suggested top-level sections:

- Overview
- Runs
- Policies
- Approvals
- Compare
- Settings

Do not add top-level destinations unless the implemented product genuinely needs them.

---

## Notifications

Notifications should prioritize **actionable runtime events**, especially:

- pending approvals
- blocked actions
- paused workflows
- critical runtime-control events

Do not create notifications for every detected anomaly.

Low/medium diagnostic findings generally belong on the affected run rather than in the global notification feed.

The notification indicator should clearly surface pending approval count.

---

## Overview

Reference: `references/overview.png`

Goals:

- provide a quick operational snapshot
- surface recent runs
- surface actionable approvals/alerts
- avoid becoming a generic analytics dashboard

Only show metrics the backend genuinely supports.

Keep charts compact and purposeful.

Recent runs should be easy to scan by:

- status
- workflow
- time
- duration
- cost/tool activity where available
- anomaly/attention indicator

---

## Runs

Reference: `references/runs.png`

Goals:

- make filtering and finding a run fast
- keep table density compact but readable
- use status pills consistently
- make technical identifiers easy to copy

Useful filters may include:

- project
- workflow
- environment
- status
- date range
- search

Do not show columns purely because the reference image contains them.

---

## Run Detail

Reference: `references/run-detail.png`

This is one of the most important product screens.

The **execution graph should be the primary visual focus**.

Keep immediately visible:

- run status
- workflow/environment/version context
- core metrics
- execution graph
- key diagnosis summary

Secondary/expandable:

- raw events
- detailed evidence
- technical metadata
- lower-level telemetry

The page should help the user move naturally from:

> run failed / looked strange  
> → inspect graph  
> → inspect diagnosis/evidence  
> → compare or replay

### Graph interaction

Where practical, support:

- clear node states
- selected-node state
- hover/focus treatment
- readable edges
- retries/loops/handoffs visually distinguishable
- concurrent branches without inventing ordering

Avoid overly decorative graph styling that reduces legibility.

---

## Diagnosis

Diagnosis must preserve the evidence-first architecture.

UI must visually distinguish:

### Observed facts
What Agent Runtime directly measured.

### Inferred explanation
What the diagnosis system believes may explain those facts.

### Evidence
Metrics, graph nodes, baseline comparisons, sample sizes.

### Advisory next step
What the developer may investigate next.

Do not visually blur an inference into a confirmed fact.

Evidence details should be expandable so the default view remains calm.

---

## Runtime Diff / Compare

Reference: `references/runtime-diff.png`

The user should quickly understand:

- what configuration changed
- how execution behavior changed
- whether the outcome improved or regressed

Prioritize:

- original vs comparison identity
- configuration changes
- added/removed steps
- retry changes
- loop/repeated-transition changes
- tool/handoff differences
- metric deltas

Use improvement/regression indicators carefully.

Do not imply that a lower metric is always better without context.

---

## Replay

Replay controls must clearly communicate safety behavior.

The three supported tool modes are:

1. **Re-execute safe tools**
2. **Reuse prior outputs**
3. **Dry-run side effects**

The UI must never imply that a mocked side effect actually occurred.

If checkpoint replay is unavailable, explain the available fallback honestly.

---

## Policies

Reference: `references/approvals-policies.png`

Policies should feel understandable without requiring users to learn a custom policy language.

Prefer a human-readable rule builder such as:

`WHEN side_effect = true AND confidence < 0.70 THEN REQUIRE_APPROVAL`

Clearly expose:

- scope
- conditions
- resulting action
- enabled/disabled state
- priority
- fail-open / fail-closed behavior

Advanced technical detail can be secondary.

---

## Approvals

Reference: `references/approvals-policies.png`

An approval item should immediately answer:

- What action is being proposed?
- Which agent/run is requesting it?
- Why did a policy require approval?
- Is this an external or destructive side effect?
- What relevant confidence/risk context exists?
- What happens if I approve or reject it?

Primary actions:

- Approve
- Reject

Sanitized input/context may be shown, but secrets must never be surfaced.

---

## Interaction Polish

Add where useful:

- hover states
- keyboard focus states
- tooltips for technical concepts
- loading skeletons
- empty states
- error states
- confirmation/success states
- expandable evidence
- graph node selection
- sticky table headers/filters where useful
- responsive layouts

Motion should be subtle and functional.

Avoid decorative animation that makes infrastructure data harder to read.

---

## Accessibility

Maintain:

- sufficient contrast
- visible focus states
- semantic buttons/links
- readable text sizing
- keyboard accessibility for primary workflows
- color-independent status cues where practical

Do not rely on red/green alone to communicate state.

---

## Responsive Behavior

Desktop is the primary experience, but major screens should remain usable at narrower widths.

For smaller viewports:

- collapse secondary panels
- allow tables to scroll intentionally
- prioritize the graph / core action area
- avoid shrinking text to preserve all desktop density

---

## Implementation Constraints

During the UI polish milestone:

- Do not redesign backend architecture.
- Do not alter domain models for visual convenience.
- Do not add fake product capabilities.
- Do not copy placeholder data from screenshots.
- Do not introduce a new component framework unless there is a clear implementation need.
- Reuse/refine existing components where practical.
- Preserve current functional behavior.

The reference screenshots are subordinate to the actual implemented product contracts.

---

## Reference Files

- `references/overview.png`
- `references/runs.png`
- `references/run-detail.png`
- `references/runtime-diff.png`
- `references/approvals-policies.png`
