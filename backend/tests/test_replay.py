import asyncio
from dataclasses import replace

from httpx import ASGITransport, AsyncClient

from agent_runtime.config import Settings
from agent_runtime.domain.models import ReplayCapability, ReplayMode
from agent_runtime.main import create_app
from agent_runtime.replay.diff import compare_runs
from agent_runtime.replay.models import ReplayAction
from agent_runtime.replay.repository import InMemoryReplayRequestRepository
from agent_runtime.replay.service import build_replay_plan, extract_checkpoints
from agent_runtime.runs.models import ExecutionGraph, GraphNode, RunMetrics, RunRecord
from agent_runtime.telemetry.storage.memory import InMemoryTelemetryStore


def test_side_effects_are_not_reexecuted_automatically() -> None:
    run = _run("source", nodes=(_tool("charge", side_effect=True, replayable=True),))

    plan = build_replay_plan(
        run,
        mode=ReplayMode.REEXECUTE_SAFE_TOOLS,
        requested_capability=ReplayCapability.FULL_RERUN,
        checkpoint_id=None,
        adapter=FullRerunAdapter(),
    )

    assert plan.decisions[0].action == ReplayAction.BLOCK_UNSAFE
    assert not plan.executable


def test_reuse_mode_requires_and_uses_prior_output_reference() -> None:
    run = _run(
        "source",
        nodes=(_tool("lookup", side_effect=False, replayable=True, output_ref="volume://one"),),
    )

    plan = build_replay_plan(
        run,
        mode=ReplayMode.REUSE_PRIOR_OUTPUTS,
        requested_capability=ReplayCapability.FULL_RERUN,
        checkpoint_id=None,
        adapter=FullRerunAdapter(),
    )

    assert plan.decisions[0].action == ReplayAction.REUSE
    assert plan.executable


def test_dry_run_marks_side_effect_as_simulated() -> None:
    run = _run("source", nodes=(_tool("send-email", side_effect=True, replayable=False),))

    plan = build_replay_plan(
        run,
        mode=ReplayMode.DRY_RUN_SIDE_EFFECTS,
        requested_capability=ReplayCapability.FULL_RERUN,
        checkpoint_id=None,
        adapter=FullRerunAdapter(),
    )

    assert plan.decisions[0].action == ReplayAction.MOCK
    assert plan.decisions[0].simulated is True
    assert plan.executable


def test_checkpoint_request_falls_back_to_full_rerun() -> None:
    run = _run("source", checkpoint=True)

    plan = build_replay_plan(
        run,
        mode=ReplayMode.REEXECUTE_SAFE_TOOLS,
        requested_capability=ReplayCapability.CHECKPOINT_REPLAY,
        checkpoint_id="checkpoint-1",
        adapter=FullRerunAdapter(),
    )

    assert plan.resolved_capability == ReplayCapability.FULL_RERUN
    assert plan.fallback_used
    assert plan.executable


def test_checkpoint_capable_adapter_preserves_checkpoint_request() -> None:
    run = _run("source", checkpoint=True)

    plan = build_replay_plan(
        run,
        mode=ReplayMode.REEXECUTE_SAFE_TOOLS,
        requested_capability=ReplayCapability.CHECKPOINT_REPLAY,
        checkpoint_id="checkpoint-1",
        adapter=CheckpointAdapter(),
    )

    assert extract_checkpoints(run)[0].state_reference == "volume://checkpoint"
    assert plan.resolved_capability == ReplayCapability.CHECKPOINT_REPLAY
    assert not plan.fallback_used


def test_runtime_diff_compares_configuration_execution_and_outcomes() -> None:
    original = _run(
        "original",
        version="v1",
        model="small",
        nodes=(_tool("search", side_effect=False, replayable=True), _decision("retry")),
        duration=200,
        retries=1,
        loops=1,
        tokens=100,
        status="failed",
    )
    comparison = _run(
        "comparison",
        version="v2",
        model="large",
        nodes=(_tool("cache", side_effect=False, replayable=True),),
        duration=100,
        retries=0,
        loops=0,
        tokens=80,
        status="succeeded",
    )

    result = compare_runs(original, comparison)

    assert next(item for item in result.configuration if item.field == "workflow_version").changed
    assert result.execution.added_tools == {"TOOL_CALL:cache": 1}
    assert result.execution.removed_tools == {"TOOL_CALL:search": 1}
    assert result.execution.retry_delta == -1
    assert result.execution.repeated_transition_delta == -1
    duration = next(item for item in result.outcomes if item.metric == "duration_ms")
    status = next(item for item in result.outcomes if item.metric == "status")
    assert duration.assessment == "improved"
    assert status.assessment == "improved"


def test_replay_and_diff_apis_persist_plan_and_report_capability() -> None:
    store = InMemoryTelemetryStore()
    source = _run("source", checkpoint=True)
    comparison = _run("comparison", duration=50)
    asyncio.run(store.upsert_gold_runs([source, comparison]))
    repository = InMemoryReplayRequestRepository()
    app = create_app(
        Settings(app_env="test", _env_file=None),
        telemetry_store=store,
        replay_repository=repository,
        replay_adapter=CheckpointAdapter(),
    )

    async def requests():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            capabilities = await client.get("/api/v1/runs/source/replay-capabilities")
            created = await client.post(
                "/api/v1/replays",
                json={
                    "source_run_id": "source",
                    "mode": "dry_run_side_effects",
                    "capability": "checkpoint_replay",
                    "checkpoint_id": "checkpoint-1",
                },
            )
            status = await client.get(f"/api/v1/replays/{created.json()['id']}")
            diff = await client.get(
                "/api/v1/runtime-diff",
                params={"original_run_id": "source", "comparison_run_id": "comparison"},
            )
            return capabilities, created, status, diff

    capabilities, created, replay_status, diff = asyncio.run(requests())
    responses = (capabilities, created, replay_status, diff)
    assert all(item.status_code in {200, 201} for item in responses)
    assert capabilities.json()["checkpoints"][0]["checkpoint_id"] == "checkpoint-1"
    assert created.json()["status"] == "pending"
    assert replay_status.json()["external_reference"] == "adapter-job-1"
    assert diff.json()["original_run_id"] == "source"


class FullRerunAdapter:
    adapter_id = "test-full"

    def supports(self, capability, run):
        return capability in {ReplayCapability.COMPARE_ONLY, ReplayCapability.FULL_RERUN}

    def safe_to_reexecute(self, node):
        return False

    async def submit(self, plan, changes):
        return "adapter-job-1"


class CheckpointAdapter(FullRerunAdapter):
    adapter_id = "test-checkpoint"

    def supports(self, capability, run):
        return True


def _tool(name: str, *, side_effect: bool, replayable: bool, output_ref: str | None = None):
    semantic = {"tool_name": name, "side_effect": side_effect, "replayable": replayable}
    if output_ref:
        semantic["output_ref"] = output_ref
    return GraphNode(
        id=f"trace:{name}",
        span_id=name,
        parent_span_id="run",
        event_type="TOOL_CALL",
        label=name,
        started_at="2026-01-01T00:00:01+00:00",
        ended_at="2026-01-01T00:00:02+00:00",
        duration_ms=1,
        status="OK",
        agent_name="agent",
        depth=1,
        lane=0,
        is_concurrent=False,
        semantic_attributes=semantic,
    )


def _decision(name: str):
    return replace(
        _tool(name, side_effect=False, replayable=True),
        event_type="DECISION",
        semantic_attributes={"decision": name},
    )


def _run(
    run_id: str,
    *,
    nodes=(),
    version="v1",
    model="model",
    duration=100,
    retries=0,
    loops=0,
    tokens=0,
    status="succeeded",
    checkpoint=False,
):
    run_node = GraphNode(
        id=f"{run_id}:run",
        span_id="run",
        parent_span_id=None,
        event_type="RUN",
        label="Run",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:03+00:00",
        duration_ms=duration,
        status="OK",
        agent_name=None,
        depth=0,
        lane=0,
        is_concurrent=False,
    )
    events = [
        {
            "event_id": f"{run_id}:run",
            "span_id": "run",
            "event_type": "RUN",
            "timestamp": run_node.started_at,
            "model": model,
            "semantic_attributes": {},
            "attributes": {},
        }
    ]
    if checkpoint:
        events.append(
            {
                "event_id": f"{run_id}:checkpoint",
                "span_id": "checkpoint",
                "event_type": "CHECKPOINT",
                "timestamp": "2026-01-01T00:00:00.500000+00:00",
                "prompt_version": "p1",
                "model": model,
                "semantic_attributes": {
                    "checkpoint_id": "checkpoint-1",
                    "state_ref": "volume://checkpoint",
                },
                "attributes": {},
            }
        )
    metrics = RunMetrics(
        total_duration_ms=duration,
        agent_latency_ms=0,
        tool_latency_ms=0,
        tool_call_count=sum(node.event_type == "TOOL_CALL" for node in nodes),
        llm_call_count=0,
        retry_count=retries,
        handoff_count=0,
        repeated_transition_count=loops,
        error_count=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=tokens,
        estimated_cost=0.01,
        approval_wait_ms=0,
        path_length=2,
        step_count=len(nodes),
    )
    return RunRecord(
        run_id=run_id,
        trace_id=run_id,
        name=run_id,
        status=status,
        started_at=run_node.started_at,
        ended_at=run_node.ended_at,
        materialized_at=run_node.ended_at,
        organization_id=None,
        project_id=None,
        workflow_name="checkout",
        workflow_version=version,
        environment="test",
        graph=ExecutionGraph(nodes=(run_node, *nodes), edges=tuple()),
        metrics=metrics,
        events=tuple(events),
    )
