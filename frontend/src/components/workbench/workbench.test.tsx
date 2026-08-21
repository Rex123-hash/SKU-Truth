// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyColumnMapping, autoDetectMapping, matrixToParsedCatalog } from "@/lib/catalog";
import { CatalogGrid } from "./CatalogGrid";
import { ResultsWorkspace } from "./ResultsWorkspace";
import { UploadScene } from "./UploadScene";

afterEach(cleanup);

function rows(count: number) {
  const parsed = matrixToParsedCatalog([
    ["MPN", "Manufacturer", "Description"],
    ...Array.from({ length: count }, (_, index) => [`SKU-${index + 1}`, "Acme", `Product ${index + 1}`]),
  ], { fileName: "catalog.csv", fileSize: 100 });
  return applyColumnMapping(parsed, autoDetectMapping(parsed.headers));
}

describe("catalog workbench UI", () => {
  it("keeps a 1,000-row catalog to one 20-row DOM page", () => {
    const catalog = rows(1000);
    const { container } = render(<CatalogGrid rows={catalog} selected={new Set()} results={new Map()} analyzing={new Set()} onToggle={vi.fn()} onToggleAll={vi.fn()} onAnalyze={vi.fn()} onOpen={vi.fn()} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(20);
    expect(screen.getByText("1,000 shown · 0 selected")).toBeTruthy();
  });

  it("supports multi-select and enables bounded analysis", () => {
    const catalog = rows(2);
    const onToggle = vi.fn();
    render(<CatalogGrid rows={catalog} selected={new Set([catalog[0].id, catalog[1].id])} results={new Map()} analyzing={new Set()} onToggle={onToggle} onToggleAll={vi.fn()} onAnalyze={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Analyze selected (2)" })).not.toHaveProperty("disabled", true);
    fireEvent.click(screen.getAllByLabelText("Select SKU-1")[0]);
    expect(onToggle).toHaveBeenCalledWith(catalog[0].id);
  });

  it("submits all six manual organizer fields", () => {
    const onManual = vi.fn();
    render(<UploadScene busy={false} progress="" error="" onFile={vi.fn()} onTrySample={vi.fn()} onManual={onManual} />);
    fireEvent.click(screen.getByRole("button", { name: "Enter product manually" }));
    fireEvent.change(screen.getByLabelText("Manufacturer part number *"), { target: { value: "45297BK" } });
    fireEvent.click(screen.getByRole("button", { name: "Prepare product" }));
    expect(onManual).toHaveBeenCalledWith(expect.objectContaining({ Mfg_Part_Num: "45297BK", Part_Desc: "", Part_Manuf: "" }));
  });

  it("shows an API failure without substituting a result", () => {
    const result = { rowId: "row-1", error: { code: "UNREACHABLE", message: "the SKUTruth demo API could not be reached" } };
    render(<ResultsWorkspace active={result} results={new Map([["row-1", result]])} />);
    expect(screen.getByText("Analysis did not complete")).toBeTruthy();
    expect(screen.getByText("No fallback result was fabricated. Retry from the catalog when the API is available.")).toBeTruthy();
    expect(screen.queryByText("Verified")).toBeNull();
  });
});
