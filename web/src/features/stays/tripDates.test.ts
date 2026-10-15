import { describe, expect, it } from "vitest";

import { formatDay } from "./tripDates";

describe("formatDay", () => {
  it("reads YYYY-MM-DD as a local date", () => {
    expect(formatDay("2026-10-17")).toBe("Sat 17 Oct");
    expect(formatDay("2026-10-19")).toBe("Mon 19 Oct");
  });
});
