import { describe, expect, it } from "vitest";
// The generator stays executable in plain Node while its deterministic core is covered here.
// @ts-expect-error The repository intentionally does not emit declarations for build scripts.
import { buildWeeklyReport, isoWeekBounds, reportMarkdown, weeklyIndexHighlight } from "../scripts/lib/report-generator.mjs";

const index = { code: "OPEU500", name: "One Piece Europe 500", breadth: 0.58 };
const history = [
  { value_date: "2026-08-02", index_value: 1000, n_capped: 0, n_carried_forward: 0 },
  { value_date: "2026-08-03", index_value: 1010, n_capped: 1, n_carried_forward: 0 },
  { value_date: "2026-08-09", index_value: 1050, n_capped: 0, n_carried_forward: 2 }
];

describe("weekly report generator", () => {
  it("calculates ISO week bounds", () => {
    expect(isoWeekBounds("2026-W32")).toEqual({ start: "2026-08-03", end: "2026-08-09" });
  });

  it("uses the last prior observation as its baseline", () => {
    const highlight = weeklyIndexHighlight(index, history, "2026-W32");
    expect(highlight.weeklyReturn).toBe(0.05);
    expect(highlight.observations).toBe(2);
    expect(highlight.notableEvents).toHaveLength(2);
    expect(highlight.chartPath).toBe("/reports/2026-W32/OPEU500.png");
  });

  it("produces a draft with an editor placeholder", () => {
    const report = buildWeeklyReport([index], { OPEU500: history }, "2026-W32");
    expect(report.status).toBe("draft");
    expect(reportMarkdown(report)).toContain("## Editor's notes");
  });
});
