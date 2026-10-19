# Runtime Control Contract

Milestone 6 adds a narrow inline control path for consequential actions. Telemetry ingestion,
graph construction, statistical analysis, and diagnosis remain out-of-band.

## Inline request

An agent runtime calls `POST /api/v1/policies/evaluate` immediately before an action and supplies
the current project/run identity plus any available workflow, agent, tool, operation, side-effect,
replayability, confidence, cost, and count facts. Missing values are never inferred and conditions
that require a missing value do not match.

The response tells the caller to `ALLOW`, `BLOCK`, `PAUSE`, or `REQUIRE_APPROVAL`. The additive
`authorization_source` field distinguishes a direct policy result, a new approval request, an
existing pending request, and authorization from an existing approved approval. For pause or
approval, the caller retains its own continuation/checkpoint and stops advancing. Agent Runtime is
not a workflow engine and approval does not create a bearer credential.

## Conditions and precedence

Conditions are ANDed. V1 supports exact workflow/agent/tool/action/operation, boolean side-effect
and replayability, confidence thresholds, accumulated cost/count thresholds, and allowed or
disallowed operation lists.

All enabled project policies are evaluated. Conflict resolution is explicit and deterministic:
`BLOCK > REQUIRE_APPROVAL > PAUSE > ALLOW`. Priority orders policies inside the same action class;
it cannot silently override the safety ordering. Every match and explanation is returned.

## Failure behavior

Malformed legacy policy evaluation observes its own `fail_closed` setting. Fail-open skips that
policy; fail-closed applies a labeled BLOCK fallback with `decision_made=false`. A repository-wide
failure uses `AGENT_RUNTIME_POLICY_SERVICE_FAIL_CLOSED` and likewise states that no policy decision
was made.

## Approvals and adapters

Approval state is `PENDING -> APPROVED | REJECTED | EXPIRED`. Repeating the same resolution is
idempotent; attempting the opposite resolution returns a conflict. Inputs are redacted before
persistence. Policy decisions and approval transitions have PostgreSQL audit records.

A caller may retry an action with the same `control_reference`. An approved record authorizes the
retry only when project, policy ID, immutable policy revision hash, logical run ID, control
reference, and deterministic sanitized-context hash all match and the approval has not expired.
The hash is computed after redaction from the context evaluated by policy; raw secrets are never
hashed or persisted for this purpose. Any relevant policy edit changes the revision hash and
invalidates reuse. Missing control references, rejected approvals, and expired approvals never
authorize a retry. The default expiry is 24 hours and is configurable with
`AGENT_RUNTIME_APPROVAL_TTL_SECONDS`.

On a valid retry the evaluation action is `ALLOW`, `authorization_source` is
`existing_approved_approval`, and `authorizing_approval_id` identifies the server-side approval.
No new approval is created. Repeated retries return the same authorization result.

Approval resolution invokes an optional runtime-control adapter. Approve maps to `resume`; reject
maps to `stop`. The default adapter performs neither operation and reports `not_configured`.

## Tenancy

`project_id` is required on new control-plane records. Authorization is behind a `ProjectAuthorizer`
port. V1 uses a permissive local implementation; production identity and RBAC remain integration
work rather than a dependency of the policy engine.
