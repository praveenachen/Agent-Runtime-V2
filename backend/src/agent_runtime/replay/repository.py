from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from agent_runtime.domain.models import ReplayRequest
from agent_runtime.replay.models import ReplayRequestRecord


class InMemoryReplayRequestRepository:
    def __init__(self) -> None:
        self.records: dict[str, ReplayRequestRecord] = {}

    async def create(self, record: ReplayRequestRecord) -> ReplayRequestRecord:
        now = datetime.now(UTC).isoformat()
        stored = replace(record, id=record.id or str(uuid4()), created_at=now, updated_at=now)
        self.records[stored.id] = stored
        return stored

    async def get(self, request_id: str) -> ReplayRequestRecord | None:
        return self.records.get(request_id)


class SqlAlchemyReplayRequestRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    async def create(self, record: ReplayRequestRecord) -> ReplayRequestRecord:
        entity = ReplayRequest(
            id=UUID(record.id),
            project_id=_uuid(record.project_id),
            source_run_id=record.source_run_id,
            mode=record.mode,
            status=record.status,
            requested_changes=record.requested_changes,
            requested_capability=record.requested_capability,
            resolved_capability=record.resolved_capability,
            checkpoint_id=record.checkpoint_id,
            adapter_id=record.adapter_id,
            plan=record.plan,
            output_run_id=record.output_run_id,
            external_reference=record.external_reference,
            status_reason=record.status_reason,
        )
        with self._sessions.begin() as session:
            session.add(entity)
        return _from_entity(entity)

    async def get(self, request_id: str) -> ReplayRequestRecord | None:
        try:
            identifier = UUID(request_id)
        except ValueError:
            return None
        with self._sessions() as session:
            entity = session.get(ReplayRequest, identifier)
            return _from_entity(entity) if entity else None


def _from_entity(entity: ReplayRequest) -> ReplayRequestRecord:
    return ReplayRequestRecord(
        id=str(entity.id),
        project_id=str(entity.project_id) if entity.project_id else None,
        source_run_id=entity.source_run_id,
        mode=entity.mode,
        status=entity.status,
        requested_changes=entity.requested_changes,
        requested_capability=entity.requested_capability,
        resolved_capability=entity.resolved_capability,
        checkpoint_id=entity.checkpoint_id,
        adapter_id=entity.adapter_id,
        plan=entity.plan,
        output_run_id=entity.output_run_id,
        external_reference=entity.external_reference,
        status_reason=entity.status_reason,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


def _uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None
