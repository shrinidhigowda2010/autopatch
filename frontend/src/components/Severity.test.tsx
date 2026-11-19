import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SeverityBadge from "./Severity";

describe("SeverityBadge", () => {
  it("shows the severity word", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("critical")).toBeTruthy();
  });
});
