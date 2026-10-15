import { Graph, layout } from "@dagrejs/dagre";

import type { PlannerGraph } from "../../api/types";
import { END_NODE, nodeLabel, START_NODE } from "./plannerNodes";

export type NodeKind = "start" | "end" | "step";

export interface LayoutNode {
  id: string;
  label: string;
  kind: NodeKind;
  // Top-left corner (dagre gives the centre).
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LayoutEdge {
  source: string;
  target: string;
  conditional: boolean;
  points: { x: number; y: number }[];
}

export interface GraphLayout {
  width: number;
  height: number;
  nodes: LayoutNode[];
  edges: LayoutEdge[];
}

const PILL_WIDTH = 96; // also has to fit "Plan ready"
const PILL_HEIGHT = 28;
const STEP_HEIGHT = 44; // room for a second line, "Waiting for you"
const STEP_MIN_WIDTH = 136;
const CHAR_WIDTH = 8;
const STEP_PADDING = 32;
const MARGIN = 8;

function kindOf(id: string): NodeKind {
  if (id === START_NODE) return "start";
  if (id === END_NODE) return "end";
  return "step";
}

// The sizes are estimated, not measured, so this stays pure (no DOM) and testable.
// A long unknown name still gets a wide enough box.
function boxSize(id: string, kind: NodeKind): { width: number; height: number } {
  if (kind !== "step") return { width: PILL_WIDTH, height: PILL_HEIGHT };
  const width = Math.max(STEP_MIN_WIDTH, CHAR_WIDTH * nodeLabel(id).length + STEP_PADDING);
  return { width, height: STEP_HEIGHT };
}

// dagre ranks the nodes top to bottom, breaks the approve -> pick cycle and routes
// the long edges into the end: drawing is all we keep.
export function layoutGraph(graph: PlannerGraph): GraphLayout {
  const g = new Graph();
  g.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 40, marginx: MARGIN, marginy: MARGIN });
  g.setDefaultEdgeLabel(() => ({}));

  for (const id of graph.nodes) {
    g.setNode(id, boxSize(id, kindOf(id)));
  }
  for (const edge of graph.edges) {
    g.setEdge(edge.source, edge.target);
  }
  layout(g);

  const nodes: LayoutNode[] = graph.nodes.map((id) => {
    const placed = g.node(id);
    return {
      id,
      label: nodeLabel(id),
      kind: kindOf(id),
      x: (placed.x ?? 0) - placed.width / 2,
      y: (placed.y ?? 0) - placed.height / 2,
      width: placed.width,
      height: placed.height,
    };
  });
  const edges: LayoutEdge[] = graph.edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    conditional: edge.conditional,
    points: g.edge(edge.source, edge.target).points ?? [],
  }));

  const info = g.graph();
  return { width: info.width ?? 0, height: info.height ?? 0, nodes, edges };
}

export function edgePath(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
}
