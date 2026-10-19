import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from agent_runtime.config import Settings
from agent_runtime.main import create_app
from agent_runtime.runs.service import RunService, build_run
from agent_runtime.telemetry.records import SilverEvent
from agent_runtime.telemetry.storage.local import LocalJsonlTelemetryStore
from agent_runtime.telemetry.storage.memory import InMemoryTelemetryStore

BASE = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_linear_graph_and_metrics_follow_execution_timestamps() -> None:
    events = [
        _event("run", "RUN", 0, 100, attributes={"agent.runtime.run.name": "Checkout"}),
        _event("llm", "LLM_CALL", 10, 30, parent="run", attributes={"input_tokens": 10}),
        _event(
            "tool",
            "TOOL_CALL",
            45,
            20,
            parent="llm",
            semantic={"tool_name": "inventory"},
            attributes={"output_tokens": 5, "agent.runtime.cost": 0.02},
        ),
    ]

    record = build_run(list(reversed(events)))

    assert [node.span_id for node in record.graph.nodes] == ["run", "llm", "tool"]
    assert [(edge.source, edge.target) for edge in record.graph.edges] == [
        ("trace:run", "trace:llm"),
        ("trace:llm", "trace:tool"),
    ]
    assert record.metrics.total_duration_ms == 100
    assert record.metrics.path_length == 3
    assert record.metrics.step_count == 2
    assert record.metrics.llm_call_count == 1
    assert record.metrics.tool_call_count == 1
    assert record.metrics.total_tokens == 15
    assert record.metrics.estimated_cost == 0.02


def test_missing_tokens_remain_absent() -> None:
    metrics = build_run([_event("run", "RUN", 0, 10)]).metrics

    assert metrics.input_tokens is None
    assert metrics.output_tokens is None
    assert metrics.total_tokens is None


def test_explicit_zero_tokens_remain_zero() -> None:
    metrics = build_run(
        [_event("run", "RUN", 0, 10, attributes={"input_tokens": 0, "output_tokens": 0})]
    ).metrics

    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 0
    assert metrics.total_tokens == 0


def test_missing_cost_remains_absent() -> None:
    metrics = build_run([_event("run", "RUN", 0, 10)]).metrics

    assert metrics.estimated_cost is None


def test_explicit_zero_cost_remains_zero() -> None:
    metrics = build_run(
        [_event("run", "RUN", 0, 10, attributes={"agent.runtime.cost": 0})]
    ).metrics

    assert metrics.estimated_cost == 0


def test_branching_and_concurrency_are_preserved_without_order_edges() -> None:
    record = build_run(
        [
            _event("run", "RUN", 0, 100),
            _event("a", "AGENT_STEP", 10, 50, parent="run", agent="planner"),
            _event("b", "TOOL_CALL", 20, 30, parent="run", agent="executor"),
        ]
    )

    a = next(node for node in record.graph.nodes if node.span_id == "a")
    b = next(node for node in record.graph.nodes if node.span_id == "b")
    assert a.is_concurrent and b.is_concurrent
    assert a.lane != b.lane
    assert not any(
        edge.source == a.id and edge.target == b.id or edge.source == b.id and edge.target == a.id
        for edge in record.graph.edges
    )


def test_retries_and_repeated_steps_are_distinct_graph_facts() -> None:
    record = build_run(
        [
            _event("run", "RUN", 0, 100),
            _event("tool-0", "TOOL_CALL", 10, 10, parent="run", semantic={"tool_name": "search"}),
            _event(
                "tool-1",
                "TOOL_CALL",
                30,
                10,
                parent="run",
                semantic={"tool_name": "search", "retry_index": 1},
            ),
            _event("decide-0", "DECISION", 50, 5, parent="run", semantic={"decision": "revise"}),
            _event("decide-1", "DECISION", 70, 5, parent="run", semantic={"decision": "revise"}),
        ]
    )

    assert record.metrics.retry_count == 1
    assert record.metrics.repeated_transition_count == 1
    assert {edge.type for edge in record.graph.edges} >= {"retry", "repeated_transition"}


def test_handoff_adds_semantic_edge_to_destination_agent() -> None:
    record = build_run(
        [
            _event("run", "RUN", 0, 100),
            _event(
                "handoff",
                "HANDOFF",
                10,
                5,
                parent="run",
                agent="triage",
                semantic={"from_agent": "triage", "to_agent": "billing"},
            ),
            _event("billing", "AGENT_STEP", 20, 30, parent="run", agent="billing"),
        ]
    )

    handoff = next(edge for edge in record.graph.edges if edge.type == "handoff")
    assert handoff.source == "trace:handoff"
    assert handoff.target == "trace:billing"
    assert record.metrics.handoff_count == 1


def test_run_service_materializes_gold_and_api_exposes_stable_views() -> None:
    store = InMemoryTelemetryStore()
    asyncio.run(
        store.append_silver(
            [_event("run", "RUN", 0, 20), _event("step", "AGENT_STEP", 2, 10, parent="run")]
        )
    )
    service = RunService(store)
    asyncio.run(service.materialize())
    assert store.gold_runs["trace"].metrics.step_count == 1

    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)

    async def request_views():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (
                await client.get("/api/v1/runs"),
                await client.get("/api/v1/runs/trace"),
                await client.get("/api/v1/runs/trace/graph"),
                await client.get("/api/v1/runs/trace/metrics"),
                await client.get("/api/v1/runs/trace/events"),
                await client.get("/api/v1/runs/missing"),
            )

    listing, detail, graph, metrics, events, missing = asyncio.run(request_views())
    assert all(
        response.status_code == 200 for response in (listing, detail, graph, metrics, events)
    )
    assert listing.json()["total"] == 1
    assert detail.json()["run_id"] == "trace"
    assert len(graph.json()["nodes"]) == 2
    assert metrics.json()["step_count"] == 1
    assert events.json()["total"] == 2
    assert missing.status_code == 404


def test_local_gold_projection_survives_store_restart(tmp_path: Path) -> None:
    store = LocalJsonlTelemetryStore(tmp_path)
    asyncio.run(store.append_silver([_event("run", "RUN", 0, 20)]))
    asyncio.run(RunService(store).materialize())

    restarted = LocalJsonlTelemetryStore(tmp_path)
    record = asyncio.run(restarted.get_gold_run("trace"))

    assert record is not None
    assert record.run_id == "trace"
    assert (tmp_path / "gold-runs.jsonl").exists()


def test_multiple_traces_share_one_logical_run_and_aggregate_graph_and_metrics() -> None:
    store = InMemoryTelemetryStore()
    first_trace = [
        _event("root", "RUN", 0, 20, trace_id="trace-a", project="project-a", external="relay-1"),
        _event(
            "step",
            "AGENT_STEP",
            2,
            10,
            trace_id="trace-a",
            parent="root",
            project="project-a",
            external="relay-1",
        ),
    ]
    second_trace = [
        _event("root", "RUN", 100, 30, trace_id="trace-b", project="project-a", external="relay-1"),
        _event(
            "tool",
            "TOOL_CALL",
            105,
            10,
            trace_id="trace-b",
            parent="root",
            project="project-a",
            external="relay-1",
            semantic={"tool_name": "lookup"},
        ),
    ]
    asyncio.run(store.append_silver(first_trace))
    records = asyncio.run(RunService(store).materialize(["trace-a"]))
    logical_id = records[0].run_id
    asyncio.run(store.append_silver(second_trace))
    records = asyncio.run(RunService(store).materialize(["trace-b"]))

    assert len(records) == 1
    run = records[0]
    assert run.run_id == logical_id
    assert run.run_id.startswith("logical-")
    assert run.trace_ids == ("trace-a", "trace-b")
    assert run.external_run_id == "relay-1"
    assert [node.trace_id for node in run.graph.nodes] == [
        "trace-a",
        "trace-a",
        "trace-b",
        "trace-b",
    ]
    assert run.metrics.step_count == 2
    assert run.metrics.tool_call_count == 1
    assert run.metrics.total_duration_ms == 130
    parent_edges = [edge for edge in run.graph.edges if edge.type == "parent_child"]
    assert {(edge.source, edge.target) for edge in parent_edges} == {
        ("trace-a:root", "trace-a:step"),
        ("trace-b:root", "trace-b:tool"),
    }
    assert not any(
        edge.source.startswith("trace-a") and edge.target.startswith("trace-b")
        for edge in run.graph.edges
    )


def test_external_run_id_is_scoped_by_project_and_workflow() -> None:
    store = InMemoryTelemetryStore()
    events = [
        _event("run", "RUN", 0, 10, trace_id="a", project="project-a", external="same"),
        _event("run", "RUN", 20, 10, trace_id="b", project="project-b", external="same"),
        _event(
            "run",
            "RUN",
            40,
            10,
            trace_id="c",
            project="project-a",
            workflow="refunds",
            external="same",
        ),
    ]
    asyncio.run(store.append_silver(events))
    records = asyncio.run(RunService(store).materialize())

    assert len(records) == 3
    assert len({record.run_id for record in records}) == 3


def test_grouped_run_supports_diagnosis_and_runtime_diff() -> None:
    store = InMemoryTelemetryStore()
    target_events = [
        _event("run", "RUN", 0, 20, trace_id="target-a", project="p", external="target"),
        _event(
            "checkpoint",
            "CHECKPOINT",
            25,
            2,
            trace_id="target-b",
            project="p",
            external="target",
            semantic={"checkpoint_ref": "state-1"},
        ),
        _event(
            "error",
            "ERROR",
            30,
            5,
            trace_id="target-b",
            project="p",
            external="target",
            attributes={"error.type": "Timeout"},
        ),
    ]
    comparison_events = [
        _event("run", "RUN", 0, 20, trace_id="comparison-a", project="p", external="comparison"),
        _event(
            "tool",
            "TOOL_CALL",
            25,
            5,
            trace_id="comparison-b",
            project="p",
            external="comparison",
            semantic={"tool_name": "recover"},
        ),
    ]
    asyncio.run(store.append_silver(target_events + comparison_events))
    records = asyncio.run(RunService(store).materialize())
    target = next(record for record in records if record.external_run_id == "target")
    comparison = next(record for record in records if record.external_run_id == "comparison")

    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)

    async def grouped_views():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (
                await client.get(f"/api/v1/runs/{target.run_id}/diagnosis"),
                await client.get(f"/api/v1/runs/{target.run_id}/replay-capabilities"),
                await client.get(
                    "/api/v1/runtime-diff",
                    params={
                        "original_run_id": target.run_id,
                        "comparison_run_id": comparison.run_id,
                    },
                ),
            )

    diagnosis, capabilities, diff = asyncio.run(grouped_views())

    assert diagnosis.status_code == capabilities.status_code == diff.status_code == 200
    assert diagnosis.json()["run_id"] == target.run_id
    assert diagnosis.json()["evidence"]["items"]
    assert capabilities.json()["checkpoints"][0]["trace_id"] == "target-b"
    assert diff.json()["original_run_id"] == target.run_id
    assert diff.json()["comparison_run_id"] == comparison.run_id
    assert "TOOL_CALL:recover" in diff.json()["execution"]["added_steps"]


def _event(
    span_id: str,
    event_type: str,
    offset_ms: int,
    duration_ms: float,
    *,
    parent: str | None = None,
    agent: str | None = "agent",
    semantic: dict | None = None,
    attributes: dict | None = None,
    trace_id: str = "trace",
    project: str | None = None,
    workflow: str = "checkout",
    external: str | None = None,
) -> SilverEvent:
    timestamp = BASE + timedelta(milliseconds=offset_ms)
    return SilverEvent(
        event_id=f"{trace_id}:{span_id}",
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        timestamp=timestamp.isoformat(),
        duration_ms=duration_ms,
        status="OK",
        event_type=event_type,
        ingested_at=(BASE + timedelta(seconds=1)).isoformat(),
        observed_lag_ms=1000,
        is_late=False,
        is_out_of_order=False,
        external_run_id=external,
        project_id=project,
        workflow_name=workflow,
        workflow_version="v1",
        environment="test",
        agent_name=agent,
        semantic_attributes=semantic or {},
        attributes=attributes or {},
    )
