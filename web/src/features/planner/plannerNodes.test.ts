import { describe, expect, it } from "vitest";

import { nodeLabel } from "./plannerNodes";

describe("nodeLabel", () => {
  it("labels known nodes in plain words and unknown nodes by their raw name", () => {
    expect(nodeLabel("__start__")).toBe("Start");
    expect(nodeLabel("__end__")).toBe("End");
    expect(nodeLabel("merge_preferences")).toBe("Merge preferences");
    expect(nodeLabel("search_sectors")).toBe("Search sectors");
    expect(nodeLabel("pick_sector")).toBe("Pick a sector");
    expect(nodeLabel("approve_sector")).toBe("Group decides");
    expect(nodeLabel("find_stays")).toBe("Find stays");
    expect(nodeLabel("propose_plan")).toBe("Propose plan");
    expect(nodeLabel("explain_conflicts")).toBe("Explain conflicts");
    expect(nodeLabel("mystery_node")).toBe("mystery_node");
  });
});
