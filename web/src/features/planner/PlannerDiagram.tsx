import { useMemo } from "react";

import type { PlannerGraph } from "../../api/types";
import { edgePath, layoutGraph, type LayoutNode } from "./graphLayout";
import styles from "./PlannerDiagram.module.css";
import { END_NODE } from "./plannerNodes";
import { stopLabel } from "./plannerText";
import { edgeKey, type RunPath } from "./runPath";

interface PlannerDiagramProps {
  graph: PlannerGraph;
  path: RunPath;
}

function nodeClasses(node: LayoutNode, path: RunPath): string {
  const classes = [styles.node];
  const visited = (path.visits.get(node.id) ?? 0) > 0;
  if (node.kind === "end" && path.stop?.node === END_NODE) {
    classes.push(path.stop.outcome === "planned" ? styles.planned : styles.noPlan);
  } else if (path.stop?.node === node.id && path.stop.outcome === "waiting") {
    classes.push(styles.paused);
  } else if (visited) {
    classes.push(styles.visited);
  }
  if (path.current === node.id) classes.push(styles.current);
  return classes.join(" ");
}

// The text under the label: only the node the run is stopped at has one.
function markFor(node: LayoutNode, path: RunPath): string | null {
  if (path.stop?.node !== node.id) return null;
  return stopLabel(path.stop.outcome);
}

function describe(path: RunPath, stepCount: number): string {
  const ending = path.stop ? `, ${stopLabel(path.stop.outcome).toLowerCase()}` : "";
  return `Planner diagram, ${stepCount} ${stepCount === 1 ? "step" : "steps"}${ending}`;
}

function PlannerDiagram({ graph, path }: PlannerDiagramProps) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  const stepCount = [...path.visits.entries()].reduce(
    (sum, [node, count]) => (node === "__start__" || node === END_NODE ? sum : sum + count),
    0,
  );

  return (
    <div className={styles.diagram}>
      <div className={styles.scroller}>
        <svg
          className={styles.svg}
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          role="img"
        >
          <title>{describe(path, stepCount)}</title>
          <defs>
            <marker id="planner-arrow" className={styles.arrow} viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" />
            </marker>
            <marker id="planner-arrow-taken" className={styles.arrowTaken} viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" />
            </marker>
          </defs>

          {layout.edges.map((edge) => {
            const taken = path.taken.has(edgeKey(edge.source, edge.target));
            const classes = [styles.edge, edge.conditional ? styles.conditional : "", taken ? styles.taken : ""];
            return (
              <path
                key={`${edge.source}-${edge.target}`}
                className={classes.join(" ")}
                d={edgePath(edge.points)}
                markerEnd={`url(#${taken ? "planner-arrow-taken" : "planner-arrow"})`}
              />
            );
          })}

          {layout.nodes.map((node) => {
            const visits = path.visits.get(node.id) ?? 0;
            const mark = markFor(node, path);
            // The End box shows the outcome instead of its name.
            const label = node.kind === "end" && mark ? mark : node.label;
            const showMark = mark !== null && node.kind === "step";
            const centreX = node.x + node.width / 2;
            const centreY = node.y + node.height / 2;
            return (
              <g key={node.id} className={nodeClasses(node, path)}>
                <title>{node.id}</title>
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={node.kind === "step" ? 10 : node.height / 2}
                />
                <text className={styles.label} x={centreX} y={showMark ? centreY - 4 : centreY} textAnchor="middle" dominantBaseline="middle">
                  {label}
                </text>
                {showMark && (
                  <text className={styles.mark} x={centreX} y={centreY + 12} textAnchor="middle" dominantBaseline="middle">
                    {mark}
                  </text>
                )}
                {visits >= 2 && (
                  <text className={styles.badge} x={node.x + node.width - 8} y={node.y + 12} textAnchor="end" dominantBaseline="middle">
                    ×{visits}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <ul className={styles.legend}>
        <li><span className={styles.sampleSolid} aria-hidden="true" /> Solid: always the next step.</li>
        <li><span className={styles.sampleDashed} aria-hidden="true" /> Dashed: the run decides.</li>
        <li><span className={styles.sampleTaken} aria-hidden="true" /> Highlighted: the path this run took.</li>
      </ul>
    </div>
  );
}

export default PlannerDiagram;
