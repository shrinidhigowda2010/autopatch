import { describe, expect, it } from "vitest";
import { explanationFor, needsReview, percent } from "./format";

describe("format helpers", () => {
  it("renders confidence as a percentage", () => {
    expect(percent(0.86)).toBe("86%");
  });

  it("uses the simpler sentence in student mode", () => {
    const bug = {
      root_cause: "The divisor is unchecked.",
      student_explanation: "Dividing by zero crashes it.",
      explanation_kn: "ಕನ್ನಡ",
      explanation_hi: "हिन्दी",
    };
    expect(explanationFor(true, "en", bug)).toBe("Dividing by zero crashes it.");
    expect(explanationFor(false, "en", bug)).toBe("The divisor is unchecked.");
    expect(explanationFor(false, "kn", bug)).toBe("ಕನ್ನಡ");
    expect(explanationFor(true, "hi", bug)).toBe("हिन्दी");
  });

  it("flags low confidence for a human", () => {
    expect(needsReview(0.74, false)).toBe(true);
    expect(needsReview(0.9, false)).toBe(false);
    expect(needsReview(0.95, true)).toBe(true);
  });
});
