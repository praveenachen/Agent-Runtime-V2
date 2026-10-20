import type { GraphNode, RunDetail, RunSummary } from "@/lib/api";

const GENERATED_RUN_NAME = /^(?:untitled run(?:\s+.*)?|run|trace(?:\s+.*)?)$/i;
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
  const candidates = [
    node.label,
    stringAttribute(attributes, "workflow_name"),
    stringAttribute(attributes, "tool_name"),
    stringAttribute(attributes, "operation"),
    stringAttribute(attributes, "name"),
    node.agent_name,
  ];
  const value = candidates.map(clean).find(Boolean) ?? semanticLabelForType(node.event_type);
  return truncate(value, 34);
}

export function semanticLabelForType(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function stringAttribute(attributes: Record<string, unknown>, key: string): string | null {
  const value = attributes[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
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
