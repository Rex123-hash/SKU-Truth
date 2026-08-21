import Papa from "papaparse";

export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MAX_WORKBOOK_SHEETS = 5;
export const MAX_CATALOG_ROWS = 5_000;
export const MAX_CATALOG_COLUMNS = 100;
export const BATCH_ANALYSIS_LIMIT = 25;

export const CATALOG_FIELDS = [
  "Mfg_Part_Num",
  "Part_Desc",
  "E1_Brand",
  "Unilog_Brand",
  "DIB_Brand",
  "Part_Manuf",
] as const;

export type CatalogField = (typeof CATALOG_FIELDS)[number];
export type CatalogStatus = "READY" | "REVIEW" | "INVALID";
export type WorkspaceState =
  | "EMPTY"
  | "PARSING"
  | "SCHEMA_REVIEW"
  | "READY"
  | "ANALYZING"
  | "RESULTS"
  | "PARTIAL"
  | "ERROR";

export const FIELD_LABELS: Record<CatalogField, string> = {
  Mfg_Part_Num: "Manufacturer Part Number",
  Part_Desc: "Description",
  E1_Brand: "E1 Brand",
  Unilog_Brand: "Unilog Brand",
  DIB_Brand: "DIB Brand",
  Part_Manuf: "Manufacturer",
};

export interface ParsedCatalog {
  fileName: string;
  fileSize: number;
  headers: string[];
  records: Record<string, string>[];
  sheetNames: string[];
  warnings: string[];
}

export type ColumnMapping = Record<CatalogField, string>;

export interface CatalogRow {
  id: string;
  sourceIndex: number;
  values: Record<CatalogField, string>;
  extra: Record<string, string>;
  status: CatalogStatus;
  issues: string[];
}

export class CatalogFileError extends Error {
  constructor(
    message: string,
    readonly code:
      | "WRONG_FILE_TYPE"
      | "OVERSIZED_FILE"
      | "EMPTY_FILE"
      | "TOO_MANY_SHEETS"
      | "TOO_MANY_ROWS"
      | "TOO_MANY_COLUMNS"
      | "MALFORMED_FILE",
  ) {
    super(message);
    this.name = "CatalogFileError";
  }
}

const aliases: Record<CatalogField, string[]> = {
  Mfg_Part_Num: ["mfg part num", "manufacturer part number", "manufacturer part no", "mpn", "sku", "part number", "part no"],
  Part_Desc: ["part desc", "description", "product description", "product name", "item description"],
  E1_Brand: ["e1 brand", "e1brand"],
  Unilog_Brand: ["unilog brand", "unilogbrand"],
  DIB_Brand: ["dib brand", "dibbrand"],
  Part_Manuf: ["part manuf", "manufacturer", "manufacturer name", "mfg", "vendor"],
};

const placeholderPattern = /^(?:n\/?a|none|null|unknown|tbd|test|-+)$/i;

function normalizedHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[_\-.\/]+/g, " ").replace(/\s+/g, " ");
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).trim();
}

export function autoDetectMapping(headers: string[]): ColumnMapping {
  const used = new Set<string>();
  return Object.fromEntries(
    CATALOG_FIELDS.map((field) => {
      const names = new Set([normalizedHeader(field), ...aliases[field].map(normalizedHeader)]);
      const match = headers.find((header) => !used.has(header) && names.has(normalizedHeader(header))) ?? "";
      if (match) used.add(match);
      return [field, match];
    }),
  ) as ColumnMapping;
}

export function emptyMapping(): ColumnMapping {
  return Object.fromEntries(CATALOG_FIELDS.map((field) => [field, ""])) as ColumnMapping;
}

export function matrixToParsedCatalog(
  matrix: unknown[][],
  meta: Pick<ParsedCatalog, "fileName" | "fileSize"> & Partial<Pick<ParsedCatalog, "sheetNames" | "warnings">>,
): ParsedCatalog {
  const nonEmpty = matrix.filter((row) => row.some((cell) => cellText(cell) !== ""));
  if (nonEmpty.length < 2) {
    throw new CatalogFileError("The file needs a header row and at least one product row.", "EMPTY_FILE");
  }
  if (nonEmpty.length - 1 > MAX_CATALOG_ROWS) {
    throw new CatalogFileError(`This catalog has more than ${MAX_CATALOG_ROWS.toLocaleString()} rows. Split it into smaller files.`, "TOO_MANY_ROWS");
  }
  if (nonEmpty[0].length > MAX_CATALOG_COLUMNS) {
    throw new CatalogFileError(`This catalog has more than ${MAX_CATALOG_COLUMNS} columns. Remove unrelated columns and try again.`, "TOO_MANY_COLUMNS");
  }

  const seen = new Map<string, number>();
  const headers = nonEmpty[0].map((cell, index) => {
    const base = cellText(cell) || `Column ${index + 1}`;
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return count === 1 ? base : `${base} (${count})`;
  });
  const records = nonEmpty.slice(1).map((row) =>
    Object.fromEntries(headers.map((header, index) => [header, cellText(row[index])])),
  );
  return {
    fileName: meta.fileName,
    fileSize: meta.fileSize,
    headers,
    records,
    sheetNames: meta.sheetNames ?? [],
    warnings: meta.warnings ?? [],
  };
}

export async function parseCatalogFile(file: File): Promise<ParsedCatalog> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !["csv", "xlsx"].includes(extension)) {
    throw new CatalogFileError("Only .csv and .xlsx catalog files are accepted. Executables, HTML, SQL, and archives are refused.", "WRONG_FILE_TYPE");
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new CatalogFileError(`Files must be ${MAX_FILE_BYTES / 1024 / 1024} MB or smaller.`, "OVERSIZED_FILE");
  }
  if (file.size === 0) throw new CatalogFileError("This file is empty.", "EMPTY_FILE");

  try {
    if (extension === "csv") {
      const parsed = Papa.parse<string[]>(await file.text(), {
        skipEmptyLines: "greedy",
        delimiter: "",
      });
      if (parsed.errors.some((error) => error.type === "Quotes")) {
        throw new CatalogFileError("The CSV contains an unclosed or malformed quoted field.", "MALFORMED_FILE");
      }
      return matrixToParsedCatalog(parsed.data, { fileName: file.name, fileSize: file.size });
    }

    const workbook = await import("read-excel-file/browser");
    const sheets = await workbook.default(file);
    const sheetNames = sheets.map((sheet) => sheet.sheet);
    if (sheets.length > MAX_WORKBOOK_SHEETS) {
      throw new CatalogFileError(`Workbooks may contain at most ${MAX_WORKBOOK_SHEETS} sheets.`, "TOO_MANY_SHEETS");
    }
    const firstSheet = sheets[0];
    if (!firstSheet) throw new CatalogFileError("This workbook has no readable sheets.", "EMPTY_FILE");
    return matrixToParsedCatalog(firstSheet.data, {
      fileName: file.name,
      fileSize: file.size,
      sheetNames,
      warnings: sheetNames.length > 1 ? [`Imported the first sheet, “${sheetNames[0]}”.`] : [],
    });
  } catch (error) {
    if (error instanceof CatalogFileError) throw error;
    throw new CatalogFileError("The file could not be read as a valid catalog.", "MALFORMED_FILE");
  }
}

export function applyColumnMapping(parsed: ParsedCatalog, mapping: ColumnMapping): CatalogRow[] {
  const preliminary = parsed.records.map((record, index) => {
    const values = Object.fromEntries(
      CATALOG_FIELDS.map((field) => [field, mapping[field] ? record[mapping[field]] ?? "" : ""]),
    ) as Record<CatalogField, string>;
    const mappedHeaders = new Set(Object.values(mapping).filter(Boolean));
    const extra = Object.fromEntries(Object.entries(record).filter(([header]) => !mappedHeaders.has(header)));
    return { id: `row-${index + 1}`, sourceIndex: index + 1, values, extra };
  });

  const counts = new Map<string, number>();
  for (const row of preliminary) {
    const mpn = row.values.Mfg_Part_Num.trim().toUpperCase();
    if (mpn) counts.set(mpn, (counts.get(mpn) ?? 0) + 1);
  }

  return preliminary.map((row) => {
    const issues: string[] = [];
    const mpn = row.values.Mfg_Part_Num.trim();
    const manufacturer = row.values.Part_Manuf.trim();
    if (!mpn) issues.push("Blank manufacturer part number");
    if (mpn && placeholderPattern.test(mpn)) issues.push("Placeholder part number");
    if (mpn && (counts.get(mpn.toUpperCase()) ?? 0) > 1) issues.push("Duplicate part number");
    if (!manufacturer) issues.push("Missing manufacturer");
    if (manufacturer && placeholderPattern.test(manufacturer)) issues.push("Placeholder manufacturer");
    const invalid = issues.some((issue) => issue.includes("Blank") || issue.includes("Placeholder part number"));
    return { ...row, issues, status: invalid ? "INVALID" : issues.length ? "REVIEW" : "READY" };
  });
}

export function knownCaseForMpn(mpn: string): "KICHLER" | "SATCO" | "FEIT" | null {
  const value = mpn.trim().toUpperCase();
  if (value === "45297BK") return "KICHLER";
  if (value === "62-1875") return "SATCO";
  if (value === "SHOP/4X2/840/V1") return "FEIT";
  return null;
}

export function toAnalyzeRequest(row: CatalogRow) {
  return {
    mpn: row.values.Mfg_Part_Num,
    description: row.values.Part_Desc,
    e1_brand: row.values.E1_Brand,
    unilog_brand: row.values.Unilog_Brand,
    dib_brand: row.values.DIB_Brand,
    manufacturer: row.values.Part_Manuf,
  };
}
