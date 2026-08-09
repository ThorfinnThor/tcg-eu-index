import { describe, expect, it } from "vitest";
import { assessFreshness } from "./freshness";

const now = new Date("2026-08-09T18:00:00Z");

describe("assessFreshness", () => {
  it("classifies current, delayed, and stale snapshots", () => {
    expect(assessFreshness("2026-08-09", now).level).toBe("fresh");
    expect(assessFreshness("2026-08-04", now)).toMatchObject({ level: "delayed", ageDays: 5 });
    expect(assessFreshness("2026-07-29", now)).toMatchObject({ level: "stale", ageDays: 11 });
  });

  it("handles unavailable dates without guessing", () => {
    expect(assessFreshness(null, now)).toEqual({ level: "unknown", ageDays: null, label: "Freshness unknown" });
    expect(assessFreshness("2026-08-10", now)).toEqual({ level: "unknown", ageDays: null, label: "Future-dated snapshot" });
  });
});
