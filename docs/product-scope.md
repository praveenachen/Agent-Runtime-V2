# Agent Runtime — Product Scope

## One-line definition
Agent Runtime helps developers understand, compare, replay, and control how AI agents behave in production.

## Problem
Agent systems can complete without technical errors while still behaving incorrectly:
- choosing the wrong tool
- skipping validation
- looping
- becoming unexpectedly expensive
- taking unusual execution paths
- attempting actions that should require approval

Traditional traces answer "what happened". Agent Runtime focuses on:
- why behavior was unusual
- what changed between runs/versions
- how to safely test a fix
- when runtime intervention is necessary

## Five core product features
1. Runtime Graph
2. Semantic Diagnosis
3. Runtime Diff
4. Checkpoint/Debugging Replay
5. Runtime Policies + Approvals

## Validation workloads
### Relay
Tests multi-agent coordination, handoffs, loops, latency.

### CatalogFlow
Tests data/tool decisions, schema/SQL workflows, validation, replay after prompt/model changes.

### Agentic BDR-style workflow
Tests consequential external actions, confidence, approvals, side effects, human-in-the-loop policies.

Use synthetic/demo data in the public portfolio version. Do not move proprietary employer/customer data into personal infrastructure.

## Product positioning
Do not position as:
- another workflow engine
- another LangSmith trace viewer
- "Temporal but smaller"

Position as:
> A framework-agnostic control plane for debugging and governing agent behavior at runtime.
