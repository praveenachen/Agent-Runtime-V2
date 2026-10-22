"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Icon, type IconName } from "@/components/ui/icon";
import { formatDuration, type GraphEdge, type GraphNode } from "@/lib/api";
import { graphNodeDisplayName } from "@/lib/run-display";

const NODE_H = 66; const ROW_H = 94; const PAD = 18; const MIN_NODE_W = 104; const MAX_NODE_W = 224;

export type GraphVisual = { tone: "run" | "agent" | "llm" | "tool" | "decision" | "error"; icon: IconName };

export function nodeVisual(node: GraphNode): GraphVisual { return typeVisual(node.event_type); }

export function typeVisual(eventType: string): GraphVisual {
  switch (eventType.toUpperCase()) {
    case "RUN": return { tone: "run", icon: "workflow" };
    case "AGENT_STEP": return { tone: "agent", icon: "graph" };
    case "LLM_CALL": return { tone: "llm", icon: "spark" };
    case "TOOL_CALL": return { tone: "tool", icon: "tool" };
    case "APPROVAL": return { tone: "decision", icon: "approval" };
    case "DECISION": return { tone: "decision", icon: "compare" };
    case "ERROR": return { tone: "error", icon: "alert" };
    default: return { tone: "run", icon: "activity" };
  }
}

export function nodeLabel(node: GraphNode): string {
  const agent = node.semantic_attributes["gen_ai.agent.name"];
  return typeof agent === "string" && agent.trim() ? agent.trim() : graphNodeDisplayName(node);
}

export type CollapsedGraph = { nodes: GraphNode[]; edges: GraphEdge[]; groups: Map<string, GraphNode[]>; owner: Map<string, string> };

// Retry attempts (nodes of one type joined by recorded retry edges) are drawn as ONE logical node. Only the drawing is merged:
// the underlying events and the step list are untouched, and the attempt count is kept for the "Repeated N×" badge.
export function collapseRetries(nodes: GraphNode[], edges: GraphEdge[]): CollapsedGraph {
  const byId = new Map(nodes.map((node) => [node.id, node])); const parent = new Map<string, string>();
  const find = (id: string): string => { let root = id; while (parent.get(root) !== undefined && parent.get(root) !== root) root = parent.get(root)!; return root; };
  edges.filter((edge) => edge.type === "retry").forEach((edge) => {
    const a = byId.get(edge.source); const b = byId.get(edge.target);
    if (a && b && a.event_type === b.event_type) { const ra = find(a.id); const rb = find(b.id); if (ra !== rb) parent.set(rb, ra); }
  });
  const groups = new Map<string, GraphNode[]>(); const owner = new Map<string, string>();
  [...nodes].sort((x, y) => Date.parse(x.started_at) - Date.parse(y.started_at)).forEach((node) => { const root = find(node.id); const list = groups.get(root) ?? []; list.push(node); groups.set(root, list); });
  // Representative = earliest attempt, so edges into the first attempt stay where they were.
  const reps = new Map<string, string>(); groups.forEach((members, root) => { reps.set(root, members[0].id); members.forEach((member) => owner.set(member.id, members[0].id)); });
  const mergedGroups = new Map<string, GraphNode[]>(); groups.forEach((members) => mergedGroups.set(members[0].id, members));
  const kept = nodes.filter((node) => owner.get(node.id) === node.id);
  const seen = new Set<string>(); const mapped: GraphEdge[] = [];
  edges.forEach((edge) => {
    const source = owner.get(edge.source) ?? edge.source; const target = owner.get(edge.target) ?? edge.target; if (source === target) return;
    const key = `${edge.type}:${source}:${target}`; if (seen.has(key)) return; seen.add(key); mapped.push({ ...edge, source, target });
  });
  return { nodes: kept, edges: mapped, groups: mergedGroups, owner };
}

// Presentation only: when parallel TOOL_CALL leaves sit beside one retried TOOL_CALL node under the same parent, draw the leaves
// joining into that node (dashed "join" connectors) and place it one column to their right. The recorded parent edge to the
// retried node is kept in the data but not drawn, since the joins replace it visually. Nothing else is added or changed.
function withFanIn(graph: CollapsedGraph): CollapsedGraph {
  const byId = new Map(graph.nodes.map((node) => [node.id, node])); const hasChildren = new Set(graph.edges.filter((edge) => edge.type === "parent_child").map((edge) => edge.source));
  const hidden = new Set<string>(); const joins: GraphEdge[] = [];
  const parents = new Set(graph.edges.filter((edge) => edge.type === "parent_child").map((edge) => edge.source));
  parents.forEach((parent) => {
    const children = graph.edges.filter((edge) => edge.type === "parent_child" && edge.source === parent).map((edge) => byId.get(edge.target)).filter((node): node is GraphNode => Boolean(node && node.event_type.toUpperCase() === "TOOL_CALL"));
    const collectors = children.filter((node) => (graph.groups.get(node.id)?.length ?? 0) > 1); const leaves = children.filter((node) => !hasChildren.has(node.id) && (graph.groups.get(node.id)?.length ?? 0) <= 1);
    if (collectors.length !== 1 || leaves.length < 2) return;
    hidden.add(`${parent}->${collectors[0].id}`);
    leaves.forEach((leaf) => joins.push({ id: `join:${leaf.id}:${collectors[0].id}`, source: leaf.id, target: collectors[0].id, type: "join" as GraphEdge["type"], metadata: {} }));
  });
  if (!joins.length) return graph;
  return { ...graph, edges: [...graph.edges.filter((edge) => !(edge.type === "parent_child" && hidden.has(`${edge.source}->${edge.target}`))), ...joins] };
}

export const isErrorNode = (node: GraphNode) => node.event_type.toUpperCase() === "ERROR" || node.status.toLowerCase() === "error";

// Layered left-to-right layout over the edges Agent Runtime returned. Repeated-transition edges are an
// evidence overlay (summarised in Run metrics), so they take no part in layout; nothing is merged or invented.
function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const used = edges.filter((edge) => edge.type !== "repeated_transition" && byId.has(edge.source) && byId.has(edge.target) && edge.source !== edge.target);
  const preds = new Map<string, string[]>(); const succs = new Map<string, string[]>();
  used.forEach((edge) => { preds.set(edge.target, [...(preds.get(edge.target) ?? []), edge.source]); succs.set(edge.source, [...(succs.get(edge.source) ?? []), edge.target]); });
  const time = (id: string) => Date.parse(byId.get(id)!.started_at);
  const layerOf = new Map<string, number>(); const visiting = new Set<string>();
  const layer = (id: string): number => {
    const known = layerOf.get(id); if (known !== undefined) return known;
    if (visiting.has(id)) return 0; // ignore back edges so cycles cannot recurse forever
    visiting.add(id);
    const value = Math.max(-1, ...(preds.get(id) ?? []).map(layer)) + 1;
    visiting.delete(id); layerOf.set(id, value); return value;
  };
  nodes.forEach((node) => layer(node.id));
  const layers: string[][] = [];
  nodes.forEach((node) => { const index = layerOf.get(node.id)!; (layers[index] ??= []).push(node.id); });
  const y = new Map<string, number>(); let next = 0;
  layers.forEach((ids) => {
    if (!ids) return;
    const desired = (id: string) => { const parents = (preds.get(id) ?? []).filter((parent) => y.has(parent)); return parents.length ? parents.reduce((sum, parent) => sum + y.get(parent)!, 0) / parents.length : null; };
    const sorted = [...ids].sort((a, b) => (desired(a) ?? next) - (desired(b) ?? next) || time(a) - time(b));
    let last = -Infinity; let index = 0;
    while (index < sorted.length) {
      const parent = (preds.get(sorted[index]) ?? [])[0]; let end = index + 1;
      while (parent !== undefined && end < sorted.length && (preds.get(sorted[end]) ?? [])[0] === parent) end += 1;
      const group = sorted.slice(index, end); const anchor = group.length > 1 ? y.get(parent!) ?? null : desired(group[0]);
      const start = Math.max(last + 1, anchor === null ? (Number.isFinite(last) ? last + 1 : 0) : anchor - (group.length - 1) / 2);
      group.forEach((id, offset) => y.set(id, start + offset)); last = start + group.length - 1; index = end;
    }
    next = Math.max(next, last + 1);
  });
  const minY = Math.min(...y.values(), 0);
  const leadsToError = new Set<string>();
  const reaches = (id: string, seen = new Set<string>()): boolean => {
    if (leadsToError.has(id)) return true;
    if (seen.has(id)) return false; seen.add(id);
    const result = isErrorNode(byId.get(id)!) || (succs.get(id) ?? []).some((child) => reaches(child, seen));
    if (result) leadsToError.add(id); return result;
  };
  nodes.forEach((node) => reaches(node.id));
  const toolCount = (id: string): number => used.filter((edge) => edge.source === id && edge.type === "parent_child" && byId.get(edge.target)!.event_type.toUpperCase() === "TOOL_CALL").length;
  // Repeated-transition evidence: nodes linked by repeated_transition edges form chains. No cycle edge is invented; each
  // chain is later outlined with one dashed loop and a single "Repeated N×" badge (N = recorded transitions).
  const repeated = edges.filter((edge) => edge.type === "repeated_transition" && byId.has(edge.source) && byId.has(edge.target));
  const component = new Map<string, number>(); const chains: Array<{ ids: string[]; transitions: number }> = [];
  repeated.forEach((edge) => {
    const known = [component.get(edge.source), component.get(edge.target)].filter((value): value is number => value !== undefined);
    const index = known.length ? known[0] : chains.length; if (index === chains.length) chains.push({ ids: [], transitions: 0 });
    [edge.source, edge.target].forEach((id) => { if (!chains[index].ids.includes(id)) { chains[index].ids.push(id); component.set(id, index); } });
    chains[index].transitions += 1;
  });
  return { chains, used, layerOf, y, minY, rows: Math.max(...[...y.values()].map((value) => value - minY), 0) + 1, cols: Math.max(...layerOf.values(), 0) + 1, leadsToError, toolCount };
}

export function RunGraph({ nodes: allNodes, edges: allEdges, selectedId, onSelect }: { nodes: GraphNode[]; edges: GraphEdge[]; selectedId: string | null; onSelect: (id: string | null) => void }) {
  const collapsed = useMemo(() => withFanIn(collapseRetries(allNodes, allEdges)), [allNodes, allEdges]);
  const nodes = collapsed.nodes;
  const layout = useMemo(() => layoutGraph(collapsed.nodes, collapsed.edges), [collapsed]);
  const wrapRef = useRef<HTMLDivElement>(null); const [available, setAvailable] = useState(0);
  useEffect(() => {
    const element = wrapRef.current; if (!element) return;
    const observer = new ResizeObserver(([entry]) => setAvailable(Math.floor(entry.contentRect.width)));
    observer.observe(element); return () => observer.disconnect();
  }, []);
  // Fit the whole topology into the card: derive node width and gap from the measured width (scroll only if it cannot fit).
  const cols = layout.cols; const gap = available ? Math.min(84, Math.max(26, Math.round(available * 0.05))) : 56;
  const fitted = available ? (available - PAD * 2 - (cols - 1) * gap) / cols : MAX_NODE_W;
  const nodeW = Math.round(Math.min(MAX_NODE_W, Math.max(MIN_NODE_W, fitted)));
  const compact = nodeW < 140;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const pos = (id: string) => ({ x: PAD + layout.layerOf.get(id)! * (nodeW + gap), y: PAD + (layout.y.get(id)! - layout.minY) * ROW_H });
  const width = PAD * 2 + cols * nodeW + (cols - 1) * gap; const height = PAD * 2 + (layout.rows - 1) * ROW_H + NODE_H;

  const loops = layout.chains.map((chain, index) => {
    const boxes = chain.ids.map((id) => pos(id)); const left = Math.min(...boxes.map((box) => box.x)) - 9; const top = Math.min(...boxes.map((box) => box.y)) - 12;
    const right = Math.max(...boxes.map((box) => box.x)) + nodeW + 9; const bottom = Math.max(...boxes.map((box) => box.y)) + NODE_H + 10;
    return { key: `loop-${index}`, x: left, y: top, w: right - left, h: bottom - top, transitions: chain.transitions };
  });
  const retryLoops = [...collapsed.groups.entries()].filter(([, members]) => members.length > 1).map(([id, members]) => { const at = pos(id); return { key: `retry-${id}`, x: at.x - 7, y: at.y - 10, w: nodeW + 14, h: NODE_H + 20, count: members.length }; });
  return <div className="rd-graph-scroll" ref={wrapRef}><div className={`rd-graph ${compact ? "compact" : ""}`} style={{ width: Math.max(width, 0), height, margin: width < available ? "0 auto" : undefined }}>
    <svg aria-hidden="true" height={height} width={width}><defs><marker id="rd-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 8 4 0 8Z" fill="#6584a6" /></marker><marker id="rd-arrow-error" markerHeight="6" markerWidth="6" orient="auto" refX="5.5" refY="3"><path d="M0 0 6 3 0 6Z" fill="#ff5a6a" /></marker><marker id="rd-arrow-retry" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 8 4 0 8Z" fill="#a08af5" /></marker></defs>
      {layout.used.map((edge) => {
        const a = pos(edge.source); const b = pos(edge.target); const forward = b.x > a.x;
        const x1 = forward ? a.x + nodeW : a.x + nodeW / 2; const y1 = forward ? a.y + NODE_H / 2 : a.y + NODE_H; const x2 = forward ? b.x - 4 : b.x + nodeW / 2; const y2 = forward ? b.y + NODE_H / 2 : b.y + NODE_H + 4; const mid = (x1 + x2) / 2;
        const error = edge.type === "parent_child" && isErrorNode(byId.get(edge.target)!); const retry = edge.type === "retry" || edge.type === "handoff";
        const d = forward ? `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}` : `M${x1},${y1} C${x1},${y1 + 46} ${x2},${y2 + 46} ${x2},${y2}`;
        return <path className={`rd-link ${edge.type} ${error ? "error" : ""}`} d={d} key={edge.id} markerEnd={`url(#${error ? "rd-arrow-error" : retry ? "rd-arrow-retry" : "rd-arrow"})`}>{edge.type === ("join" as GraphEdge["type"]) && <title>Parallel branches grouped into this step (presentation only, not a recorded edge)</title>}</path>;
      })}
      {retryLoops.map((loop) => <rect className="rd-loop" height={loop.h} key={loop.key} rx="16" width={loop.w} x={loop.x} y={loop.y} />)}
      {loops.map((loop) => <rect className="rd-loop" height={loop.h} key={loop.key} rx="16" width={loop.w} x={loop.x} y={loop.y} />)}
    </svg>
    {retryLoops.map((loop) => <span className="rd-loop-badge" key={`badge-${loop.key}`} style={{ left: loop.x + loop.w / 2, top: loop.y }} title={`${loop.count} attempts recorded for this step`}>↺ Repeated {loop.count}×</span>)}
    {loops.map((loop) => <span className="rd-loop-badge" key={`badge-${loop.key}`} style={{ left: loop.x + loop.w / 2, top: loop.y }} title={`${loop.transitions} repeated transition${loop.transitions === 1 ? "" : "s"} recorded across these steps`}>↺ Repeated {loop.transitions}×</span>)}
    {nodes.map((node) => {
      const { x, y } = pos(node.id); const visual = nodeVisual(node); const error = isErrorNode(node); const tools = layout.toolCount(node.id);
      return <button aria-pressed={selectedId === node.id} className={`rd-node tone-${visual.tone} ${error ? "is-error" : "is-ok"} ${selectedId === node.id ? "selected" : ""}`} key={node.id} onClick={() => onSelect(selectedId === node.id ? null : node.id)} style={{ left: x, top: y, width: nodeW, height: NODE_H }} title={`${nodeLabel(node)} · ${formatDuration(node.duration_ms)}`} type="button">
        <span className="rd-node-icon"><Icon name={visual.icon} /></span>
        <span className="rd-node-text"><strong>{nodeLabel(node)}</strong><small>{formatDuration(node.duration_ms)}</small></span>
        {(tools > 0 || node.retry_index !== null) && <span className="rd-badges">
          {node.retry_index !== null && (collapsed.groups.get(node.id)?.length ?? 0) <= 1 && <span className="rd-pill repeated">retry {node.retry_index}</span>}
          {tools > 0 && <span className="rd-pill">{tools} tool{tools === 1 ? "" : "s"}</span>}
        </span>}
      </button>;
    })}
  </div></div>;
}
