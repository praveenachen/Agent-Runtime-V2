from typing import Any

from agent_runtime.control.models import PolicyMatch, PolicyRecord, RuntimeContext

_EXACT_FIELDS = {
    "workflow_name", "agent_name", "tool_name", "action_name", "operation",
    "side_effect", "replayable",
}
_NUMERIC_FIELDS = {
    "confidence_lt": ("confidence", lambda actual, expected: actual < expected, "<"),
    "confidence_lte": ("confidence", lambda actual, expected: actual <= expected, "<="),
    "confidence_gte": ("confidence", lambda actual, expected: actual >= expected, ">="),
    "current_cost_gte": ("current_cost", lambda actual, expected: actual >= expected, ">="),
    "tool_call_count_gte": ("tool_call_count", lambda actual, expected: actual >= expected, ">="),
    "retry_count_gte": ("retry_count", lambda actual, expected: actual >= expected, ">="),
    "repeated_transition_count_gte": (
        "repeated_transition_count", lambda actual, expected: actual >= expected, ">="
    ),
}
_OPERATION_LISTS = {"allowed_operations", "disallowed_operations"}
SUPPORTED_CONDITIONS = _EXACT_FIELDS | set(_NUMERIC_FIELDS) | _OPERATION_LISTS


class PolicyEvaluationError(ValueError):
    pass


def validate_conditions(conditions: dict[str, Any]) -> None:
    unknown = set(conditions) - SUPPORTED_CONDITIONS
    if unknown:
        raise PolicyEvaluationError(f"Unsupported conditions: {', '.join(sorted(unknown))}")
    for key in _OPERATION_LISTS:
        if key in conditions and not isinstance(conditions[key], list):
            raise PolicyEvaluationError(f"{key} must be a list")
    for key in _NUMERIC_FIELDS:
        if key in conditions and not isinstance(conditions[key], (int, float)):
            raise PolicyEvaluationError(f"{key} must be numeric")
    for key in {"side_effect", "replayable"}:
        if key in conditions and not isinstance(conditions[key], bool):
            raise PolicyEvaluationError(f"{key} must be boolean")


def match_policy(policy: PolicyRecord, context: RuntimeContext) -> PolicyMatch | None:
    validate_conditions(policy.conditions)
    explanations: list[str] = []
    for field in _EXACT_FIELDS:
        if field not in policy.conditions:
            continue
        actual = getattr(context, field)
        expected = policy.conditions[field]
        if actual is None or actual != expected:
            return None
        explanations.append(f"{field} = {expected!r}")
    for condition, (field, comparator, symbol) in _NUMERIC_FIELDS.items():
        if condition not in policy.conditions:
            continue
        actual = getattr(context, field)
        expected = policy.conditions[condition]
        if actual is None or not comparator(actual, expected):
            return None
        explanations.append(f"{field} {symbol} {expected}")
    if "allowed_operations" in policy.conditions:
        allowed = policy.conditions["allowed_operations"]
        if context.operation is None or context.operation not in allowed:
            return None
        explanations.append(f"operation is allowed: {context.operation}")
    if "disallowed_operations" in policy.conditions:
        disallowed = policy.conditions["disallowed_operations"]
        if context.operation is None or context.operation not in disallowed:
            return None
        explanations.append(f"operation is disallowed: {context.operation}")
    if not explanations:
        explanations.append("policy has no conditions and matches all supplied contexts")
    return PolicyMatch(
        policy.id, policy.name, policy.action, policy.priority, tuple(explanations)
    )
