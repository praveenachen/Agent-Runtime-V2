from typing import Protocol

from agent_runtime.control.models import ApprovalRecord, PolicyRecord


class ControlRepository(Protocol):
    async def list_policies(self, project_id: str) -> list[PolicyRecord]: ...
    async def get_policy(self, policy_id: str) -> PolicyRecord | None: ...
    async def save_policy(self, policy: PolicyRecord) -> PolicyRecord: ...
    async def delete_policy(self, policy_id: str) -> None: ...
    async def record_evaluation(self, decision: dict, approval: ApprovalRecord | None) -> str: ...
    async def list_approvals(self, project_id: str, state: str | None) -> list[ApprovalRecord]: ...
    async def get_approval(self, approval_id: str) -> ApprovalRecord | None: ...
    async def find_latest_bound_approval(
        self,
        *,
        project_id: str,
        policy_id: str,
        policy_revision: str,
        run_id: str,
        control_reference: str,
        context_hash: str,
    ) -> ApprovalRecord | None: ...
    async def resolve_approval(
        self, approval_id: str, state: str, reviewer: str | None, integration_reference: str | None
    ) -> tuple[ApprovalRecord, bool]: ...
    async def expire_approval(self, approval_id: str) -> ApprovalRecord: ...
    async def attach_integration_reference(
        self, approval_id: str, reference: str
    ) -> ApprovalRecord: ...


class ProjectAuthorizer(Protocol):
    def authorize(self, principal: str, project_id: str, operation: str) -> None: ...


class LocalPermissiveAuthorizer:
    def authorize(self, principal: str, project_id: str, operation: str) -> None:
        return None


class RuntimeControlAdapter(Protocol):
    adapter_id: str
    async def resume(self, approval: ApprovalRecord) -> str | None: ...
    async def stop(self, approval: ApprovalRecord) -> str | None: ...


class NoopRuntimeControlAdapter:
    adapter_id = "none"

    async def resume(self, approval: ApprovalRecord) -> str | None:
        return None

    async def stop(self, approval: ApprovalRecord) -> str | None:
        return None
