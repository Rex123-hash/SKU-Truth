import { describe, expect, it } from "vitest";

import {
  MAX_FILE_BYTES,
  CatalogFileError,
  applyColumnMapping,
  autoDetectMapping,
  knownCaseForMpn,
  matrixToParsedCatalog,
  parseCatalogFile,
} from "./catalog";
import { csvFromRows } from "./exports";

describe("catalog parsing", () => {
  it("parses quoted CSV fields without splitting embedded commas", async () => {
    const file = new File([
      'SKU,Product Name,Manufacturer\n45297BK,"Lantern, black",Kichler\n',
    ], "catalog.csv", { type: "text/csv" });
    const parsed = await parseCatalogFile(file);
    expect(parsed.records[0]["Product Name"]).toBe("Lantern, black");
    expect(parsed.records[0].SKU).toBe("45297BK");
  });

  it("turns an XLSX sheet matrix into bounded catalog records", () => {
    const parsed = matrixToParsedCatalog(
      [["MPN", "Description"], ["A-1", "Pump"], ["A-2", "Valve"]],
      { fileName: "catalog.xlsx", fileSize: 512, sheetNames: ["Products"] },
    );
    expect(parsed.sheetNames).toEqual(["Products"]);
    expect(parsed.records).toHaveLength(2);
    expect(parsed.records[1].MPN).toBe("A-2");
  });

  it("rejects empty, wrong-type, and oversized files", async () => {
    await expect(parseCatalogFile(new File([], "empty.csv"))).rejects.toMatchObject({ code: "EMPTY_FILE" });
    await expect(parseCatalogFile(new File(["select *"], "dump.sql"))).rejects.toMatchObject({ code: "WRONG_FILE_TYPE" });
    const oversized = { name: "huge.csv", size: MAX_FILE_BYTES + 1, text: async () => "" } as File;
    await expect(parseCatalogFile(oversized)).rejects.toMatchObject({ code: "OVERSIZED_FILE" });
  });

  it("requires a header and a product row", () => {
    expect(() => matrixToParsedCatalog([["MPN"]], { fileName: "empty.xlsx", fileSize: 1 })).toThrow(CatalogFileError);
  });
});

describe("mapping and validation", () => {
  it("auto-detects organizer aliases and exposes a missing required MPN", () => {
    const detected = autoDetectMapping(["SKU", "Product Name", "Vendor"]);
    expect(detected.Mfg_Part_Num).toBe("SKU");
    expect(detected.Part_Desc).toBe("Product Name");
    expect(detected.Part_Manuf).toBe("Vendor");
    expect(autoDetectMapping(["Description"]).Mfg_Part_Num).toBe("");
  });

  it("classifies blank MPNs as invalid and duplicates or missing manufacturers for review", () => {
    const parsed = matrixToParsedCatalog([
      ["MPN", "Manufacturer"], ["A-1", "Acme"], ["A-1", "Acme"], ["", "Acme"], ["B-1", ""],
    ], { fileName: "catalog.xlsx", fileSize: 100 });
    const rows = applyColumnMapping(parsed, autoDetectMapping(parsed.headers));
    expect(rows.map((row) => row.status)).toEqual(["REVIEW", "REVIEW", "INVALID", "REVIEW"]);
    expect(rows[0].issues).toContain("Duplicate part number");
    expect(rows[3].issues).toContain("Missing manufacturer");
  });

  it("recognizes all recorded cases without changing the slash-heavy MPN", () => {
    expect(knownCaseForMpn("45297BK")).toBe("KICHLER");
    expect(knownCaseForMpn("62-1875")).toBe("SATCO");
    expect(knownCaseForMpn("SHOP/4X2/840/V1")).toBe("FEIT");
    expect(knownCaseForMpn("SHOP-4X2-840-V1")).toBeNull();
  });
});

describe("CSV export", () => {
  it("quotes commas, quotes, and line breaks", () => {
    const output = csvFromRows(["MPN", "Value"], [["A-1", 'Black, 3" tall\nverified']]);
    expect(output).toContain('A-1,"Black, 3"" tall\nverified"');
  });
});
