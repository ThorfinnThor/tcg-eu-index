import { describe, expect, it } from "vitest";
import { applyPublicIndexMetadata, canonicalIndexCode, indexAssetCandidates } from "./index-codes";

describe("canonical index codes", () => {
  it("maps renamed singles while retaining legacy asset fallback", () => {
    expect(canonicalIndexCode("OPEU100")).toBe("OPEU500");
    expect(indexAssetCandidates("OPEU500")).toEqual(["OPEU500", "OPEU100"]);
    expect(indexAssetCandidates("OPEU100")).toEqual(["OPEU500", "OPEU100"]);
  });

  it("overrides legacy public metadata with the current methodology", () => {
    expect(applyPublicIndexMetadata({
      code: "OPEU100",
      name: "One Piece Europe 100",
      slug: "one-piece-europe-100",
      target_size: 100
    })).toEqual({
      code: "OPEU500",
      name: "One Piece Europe 500",
      slug: "one-piece-europe-500",
      target_size: 500
    });
  });
});
