import { describe, expect, it } from "vitest";

import { CASES, caseIdForSlug, isCaseSlug, slugForCaseId } from "./cases";
import { reasonSentence } from "./vocab";

describe("stable demo routes", () => {
  it("maps every public slug to the API case id and back", () => {
    for (const [slug, meta] of Object.entries(CASES)) {
      expect(isCaseSlug(slug)).toBe(true);
      expect(caseIdForSlug(slug)).toBe(meta.caseId);
      expect(slugForCaseId(meta.caseId)).toBe(slug);
    }
  });

  it("never treats the slash-bearing Feit MPN as a route slug", () => {
    expect(caseIdForSlug(CASES.feit.mpn)).toBeNull();
    expect(CASES.feit.mpn).toBe("SHOP/4X2/840/V1");
  });
});

describe("judge-facing reason copy", () => {
  it("explains the strongest withheld Kichler proposal", () => {
    expect(reasonSentence("SOURCE_PROPERTY_NOT_AUTHORIZED")).toContain(
      "source property does not prove",
    );
  });
});
