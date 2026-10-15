import { describe, expect, it } from "vitest";

import { edgePath, layoutGraph } from "./graphLayout";
import { PLANNER_GRAPH } from "./planner.fixtures";

describe("layoutGraph", () => {
  it("gives every node a box inside the drawing", () => {
    const layout = layoutGraph(PLANNER_GRAPH);
    expect(layout.nodes).toHaveLength(9);
    for (const node of layout.nodes) {
      for (const value of [node.x, node.y, node.width, node.height]) {
        expect(Number.isFinite(value)).toBe(true);
      }
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.x + node.width).toBeLessThanOrEqual(layout.width);
      expect(node.y + node.height).toBeLessThanOrEqual(layout.height);
    }
  });

  it("keeps every edge with its conditional flag and at least two points", () => {
    const layout = layoutGraph(PLANNER_GRAPH);
    expect(layout.edges).toHaveLength(11);
    expect(layout.edges.map(({ source, target, conditional }) => ({ source, target, conditional })))
      .toEqual(PLANNER_GRAPH.edges);
    expect(layout.edges.some((e) => e.source === "approve_sector" && e.target === "pick_sector")).toBe(true);
    for (const edge of layout.edges) {
      expect(edge.points.length).toBeGreaterThanOrEqual(2);
    }
  });

  it("draws the start above the first step and the end below the last", () => {
    const y = Object.fromEntries(layoutGraph(PLANNER_GRAPH).nodes.map((n) => [n.id, n.y]));
    expect(y["__start__"]).toBeLessThan(y["merge_preferences"]);
    expect(y["merge_preferences"]).toBeLessThan(y["propose_plan"]);
    expect(y["propose_plan"]).toBeLessThan(y["__end__"]);
  });

  it("lays out a node it has never seen, labelled with its raw name and wide enough", () => {
    // Long enough that the estimated width exceeds the minimum box.
    const name = "a_rather_long_mystery_node";
    const layout = layoutGraph({
      nodes: ["__start__", name, "pick_sector", "__end__"],
      edges: [
        { source: "__start__", target: name, conditional: false },
        { source: name, target: "pick_sector", conditional: false },
        { source: "pick_sector", target: "__end__", conditional: false },
      ],
    });
    const mystery = layout.nodes.find((n) => n.id === name);
    const pick = layout.nodes.find((n) => n.id === "pick_sector");
    expect(mystery?.label).toBe(name);
    expect(mystery!.width).toBeGreaterThan(pick!.width);
  });

  it("edgePath draws a line through the points", () => {
    expect(edgePath([{ x: 0, y: 0 }, { x: 10, y: 5 }, { x: 20, y: 10 }])).toBe("M0,0 L10,5 L20,10");
  });
});
