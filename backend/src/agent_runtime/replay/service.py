from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_runtime.domain.models import ReplayCapability, ReplayMode, ReplayStatus
from agent_runtime.replay.diff import compare_runs
from agent_runtime.replay.models import (
    CapabilityAvailability,
    ReplayAction,
    ReplayCapabilities,
    ReplayPlan,
    ReplayRequestRecord,
    RuntimeDiff,
    SemanticCheckpoint,
    StepReplayDecision,
)
from agent_runtime.replay.ports import FrameworkReplayAdapter, ReplayRequestRepository
from agent_runtime.runs.models import GraphNode, RunRecord
from agent_runtime.runs.service import RunService


class ReplayService:
    def __init__(
        self,
        runs: RunService,
        repository: ReplayRequestRepository,
        adapter: FrameworkReplayAdapter,
    ) -> None:
        self._runs = runs
        self._repository = repository
        self._adapter = adapter

    async def capabilities(self, run_id: str) -> ReplayCapabilities | None:
        run = await self._runs.get_run(run_id)
        if run is None:
            return None
        checkpoints = extract_checkpoints(run)
        values = []
        for capability in ReplayCapability:
            available = self._adapter.supports(capability, run)
            if capability == ReplayCapability.CHECKPOINT_REPLAY:
                available = available and bool(checkpoints)
            reason = _capability_reason(capability, available, bool(checkpoints))
            values.append(CapabilityAvailability(capability, available, reason))
        return ReplayCapabilities(run.run_id, self._adapter.adapter_id, tuple(values), checkpoints)

    async def create_request(
        self,
        *,
        source_run_id: str,
        mode: ReplayMode,
        requested_capability: ReplayCapability,
        checkpoint_id: str | None,
        requested_changes: dict[str, Any],
    ) -> ReplayRequestRecord | None:
        run = await self._runs.get_run(source_run_id)
        if run is None:
            return None
        plan = build_replay_plan(
            run,
            mode=mode,
            requested_capability=requested_capability,
            checkpoint_id=checkpoint_id,
            adapter=self._adapter,
        )
        status = ReplayStatus.PLANNED if plan.executable else ReplayStatus.BLOCKED
        external_reference = None
        if plan.executable:
            external_reference = await self._adapter.submit(plan, requested_changes)
            if external_reference:
                status = ReplayStatus.PENDING
        now = datetime.now(UTC).isoformat()
        record = ReplayRequestRecord(
            id=str(uuid4()),
            project_id=run.project_id,
            source_run_id=source_run_id,
            mode=mode,
            status=status,
            requested_changes=requested_changes,
            requested_capability=requested_capability,
            resolved_capability=plan.resolved_capability,
            checkpoint_id=plan.checkpoint_id,
            adapter_id=self._adapter.adapter_id,
            plan=plan.to_dict(),
            output_run_id=None,
            external_reference=external_reference,
            status_reason=plan.blocked_reason,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(record)

    async def get_request(self, request_id: str) -> ReplayRequestRecord | None:
        return await self._repository.get(request_id)

    async def compare(self, original_id: str, comparison_id: str) -> RuntimeDiff | None:
        original = await self._runs.get_run(original_id)
        comparison = await self._runs.get_run(comparison_id)
        if original is None or comparison is None:
            return None
        return compare_runs(original, comparison)


def build_replay_plan(
    run: RunRecord,
    *,
    mode: ReplayMode,
    requested_capability: ReplayCapability,
    checkpoint_id: str | None,
    adapter: FrameworkReplayAdapter,
) -> ReplayPlan:
    checkpoints = {item.checkpoint_id for item in extract_checkpoints(run)}
    resolved = requested_capability
    fallback = False
    blocked_reason = None
    if requested_capability == ReplayCapability.CHECKPOINT_REPLAY and (
        not checkpoint_id
        or checkpoint_id not in checkpoints
        or not adapter.supports(requested_capability, run)
    ):
        fallback = True
        resolved = ReplayCapability.FULL_RERUN
    if not adapter.supports(resolved, run):
        blocked_reason = (
            "No configured replay adapter can execute this request. Compare-only remains available."
        )
        resolved = ReplayCapability.COMPARE_ONLY
    decisions = tuple(_decision(node, mode, adapter) for node in _ordered_nodes(run))
    unsafe = [item for item in decisions if item.action == ReplayAction.BLOCK_UNSAFE]
    executable = resolved != ReplayCapability.COMPARE_ONLY and not unsafe
    if unsafe and blocked_reason is None:
        blocked_reason = f"{len(unsafe)} step(s) have no safe replay behavior."
    return ReplayPlan(
        source_run_id=run.run_id,
        requested_capability=requested_capability,
        resolved_capability=resolved,
        checkpoint_id=checkpoint_id if resolved == ReplayCapability.CHECKPOINT_REPLAY else None,
        adapter_id=adapter.adapter_id,
        mode=mode,
        fallback_used=fallback,
        decisions=decisions,
        executable=executable,
        blocked_reason=blocked_reason,
    )


def extract_checkpoints(run: RunRecord) -> tuple[SemanticCheckpoint, ...]:
    result = []
    for event in run.events:
        semantic = event.get("semantic_attributes", {})
        attributes = event.get("attributes", {})
        checkpoint_id = (
            semantic.get("checkpoint_ref")
            or semantic.get("checkpoint_id")
            or attributes.get("agent.runtime.checkpoint.ref")
            or attributes.get("agent.runtime.checkpoint.id")
        )
        if event.get("event_type") != "CHECKPOINT" and not checkpoint_id:
            continue
        identifier = str(checkpoint_id or event["event_id"])
        result.append(
            SemanticCheckpoint(
                checkpoint_id=identifier,
                run_id=run.run_id,
                trace_id=str(event.get("trace_id") or run.trace_id),
                span_id=str(event["span_id"]),
                timestamp=str(event["timestamp"]),
                integration=_value(attributes, "agent.runtime.integration"),
                workflow_name=run.workflow_name,
                environment=run.environment,
                workflow_version=_optional_text(run.workflow_version),
                prompt_version=_optional_text(event.get("prompt_version")),
                model=_optional_text(event.get("model")),
                state_reference=(
                    _value(semantic, "checkpoint_ref")
                    or _value(semantic, "state_ref")
                    or _value(attributes, "agent.runtime.checkpoint.state_ref")
                ),
                input_reference=_value(semantic, "input_ref"),
                output_reference=_value(semantic, "output_ref"),
            )
        )
    return tuple(result)


def _decision(
    node: GraphNode, mode: ReplayMode, adapter: FrameworkReplayAdapter
) -> StepReplayDecision:
    if node.event_type != "TOOL_CALL":
        return StepReplayDecision(
            node.id,
            node.span_id,
            node.label,
            node.event_type,
            ReplayAction.REEXECUTE,
            "Framework orchestration step.",
        )
    semantic = node.semantic_attributes
    side_effect = semantic.get("side_effect")
    replayable = semantic.get("replayable") is True
    output_ref = semantic.get("output_ref") or semantic.get("prior_output_ref")
    safe = side_effect is False and replayable
    adapter_safe = replayable and adapter.safe_to_reexecute(node)
    if mode == ReplayMode.REUSE_PRIOR_OUTPUTS:
        action = ReplayAction.REUSE if output_ref else ReplayAction.BLOCK_UNSAFE
        reason = (
            "Prior output reference is available."
            if output_ref
            else "No prior output reference is available."
        )
    elif mode == ReplayMode.DRY_RUN_SIDE_EFFECTS and side_effect is True:
        action, reason = ReplayAction.MOCK, "External side effect is simulated and will not occur."
    elif safe or adapter_safe:
        action = ReplayAction.REEXECUTE
        reason = "Tool is explicitly replayable and safe for this adapter."
    elif output_ref:
        action, reason = ReplayAction.REUSE, "Safety is ambiguous; reuse is safer than execution."
    else:
        action = ReplayAction.BLOCK_UNSAFE
        reason = "Safety is ambiguous and no reusable output exists."
    return StepReplayDecision(
        node.id,
        node.span_id,
        node.label,
        node.event_type,
        action,
        reason,
        simulated=action == ReplayAction.MOCK,
    )


def _ordered_nodes(run: RunRecord) -> list[GraphNode]:
    return sorted(
        (node for node in run.graph.nodes if node.event_type != "RUN"),
        key=lambda node: (node.started_at, node.span_id),
    )


def _value(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    return str(value) if value is not None else None


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _capability_reason(capability: ReplayCapability, available: bool, has_checkpoints: bool) -> str:
    if capability == ReplayCapability.COMPARE_ONLY:
        return "Completed runs can always be compared."
    if available:
        return "Supported by the configured framework adapter."
    if capability == ReplayCapability.CHECKPOINT_REPLAY and not has_checkpoints:
        return "This run has no semantic checkpoints."
    return "No configured framework adapter supports this capability."
