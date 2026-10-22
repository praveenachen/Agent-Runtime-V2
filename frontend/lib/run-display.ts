import type { GraphNode, RunDetail, RunSummary } from "@/lib/api";

const GENERATED_RUN_NAME = /^(?:untitled run(?:\s+.*)?|run|trace(?:\s+.*)?)$/i;
const GENERIC_NODE_NAME = /^(?:agent step|tool call|decision|approval|run|span|event|error)$/i;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function runDisplayName(run: RunSummary): string {
  const semanticName = recordedSemanticName(run);
  if (semanticName) return semanticName;
  if (clean(run.external_run_id)) {
    const externalId = run.external_run_id!.trim();
    return UUID.test(externalId) ? `Logical run ${shortId(externalId)}` : externalId;
  }
  return `Trace ${shortId(run.trace_id, 12)}`;
}

export function runDetailDisplayName(run: RunDetail): string {
  const semanticName = recordedSemanticName(run);
  if (semanticName) return semanticName;

  const semanticLabel = run.graph.nodes
    .map((node) => clean(node.label))
    .find((value) => value && !GENERATED_RUN_NAME.test(value));
  if (semanticLabel) return semanticLabel;

  const semanticType = run.graph.nodes.find((node) => clean(node.event_type) && node.event_type !== "RUN")?.event_type;
  return semanticType ? semanticLabelForType(semanticType) : runDisplayName(run);
}

export function graphNodeDisplayName(node: GraphNode): string {
  const attributes = node.semantic_attributes;
  const keys = keysForEventType(node.event_type);
  const recorded = keys.map((key) => stringAttribute(attributes, key)).map(clean).find(Boolean);
  const label = clean(node.label);
  const fallback = label && !GENERIC_NODE_NAME.test(label) ? label : clean(node.agent_name);
  const value = recorded ?? fallback ?? label ?? semanticLabelForType(node.event_type);
  return truncate(humanizeRecordedName(value, attributes), 38);
}

export function semanticLabelForType(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function stringAttribute(attributes: Record<string, unknown>, key: string): string | null {
  const value = attributes[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
}

function keysForEventType(eventType: string): string[] {
  const shared = [
    "step_name", "agent.runtime.step.name", "action_name", "agent.runtime.action.name",
    "tool_name", "agent.runtime.tool.name", "operation", "agent.runtime.tool.operation",
    "relay.operation", "relay.stage", "decision_type", "workflow_name", "agent.runtime.workflow.name",
    "relay.provider", "agent_name", "name",
  ];
  switch (eventType.toUpperCase()) {
    case "RUN": return ["workflow_name", "agent.runtime.workflow.name", "agent.runtime.step.name", "step_name", "name"];
    case "TOOL_CALL": return ["action_name", "agent.runtime.action.name", "operation", "agent.runtime.tool.operation", "relay.operation", "tool_name", "agent.runtime.tool.name", ...shared];
    case "DECISION": return ["decision_type", "action_name", "agent.runtime.action.name", "step_name", "agent.runtime.step.name", "relay.operation", "relay.outcome", ...shared];
    case "APPROVAL": return ["action_name", "agent.runtime.action.name", "decision_type", "operation", "agent.runtime.tool.operation", "relay.operation", "relay.stage", ...shared];
    case "AGENT_STEP": return ["step_name", "agent.runtime.step.name", "action_name", "agent.runtime.action.name", "relay.stage", "relay.operation", "agent_name", ...shared];
    case "LLM_CALL": return ["action_name", "agent.runtime.action.name", "step_name", "agent.runtime.step.name", "relay.operation", "relay.stage", ...shared];
    case "ERROR": return ["operation", "agent.runtime.tool.operation", "relay.operation", "error_type", "error.type", ...shared];
    default: return shared;
  }
}

function humanizeRecordedName(value: string, attributes: Record<string, unknown>): string {
  const normalized = value.trim();
  const operation = normalized.toLowerCase().replaceAll(".", "_").replaceAll("-", "_");
  const toolContext = [stringAttribute(attributes, "tool_name"), stringAttribute(attributes, "agent.runtime.tool.name"), stringAttribute(attributes, "relay.provider")]
    .filter(Boolean).join(" ").toLowerCase();
  if (operation === "get_database" && toolContext.includes("notion")) return "Read Notion Database";
  return normalized.replace(/[._-]+/g, " ").replace(/\s+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function clean(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  return normalized || null;
}

function recordedSemanticName(run: RunSummary): string | null {
  const recordedName = clean(run.name);
  if (recordedName && !GENERATED_RUN_NAME.test(recordedName)) return recordedName;
  return clean(run.workflow_name);
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1).trimEnd()}…` : value;
}

function shortId(value: string, length = 8): string {
  return value.slice(0, length);
}
