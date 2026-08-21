import type { ProductDetail } from "./types";

export interface AnalyzedProduct {
  rowId: string;
  detail?: ProductDetail;
  error?: { code: string; message: string };
}

function quote(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function csvFromRows(headers: string[], rows: unknown[][]): string {
  return "\uFEFF" + [headers, ...rows].map((row) => row.map(quote).join(",")).join("\r\n") + "\r\n";
}

function overallState(detail: ProductDetail): string {
  if (detail.timeline.some((entry) => entry.status === "BLOCKED")) return "BLOCKED";
  if (detail.timeline.some((entry) => entry.status === "WITHHELD")) return "WITHHELD";
  if (detail.timeline.some((entry) => entry.status === "REVIEW")) return "REVIEW";
  if (detail.timeline.some((entry) => entry.status === "NOT_RUN")) return "PARTIAL";
  return "VERIFIED";
}

export function analysisReportCsv(results: AnalyzedProduct[]): string {
  return csvFromRows(
    ["MPN", "Manufacturer", "Classification", "Pipeline State", "Verified Facts", "Withheld", "Blocker", "Reason"],
    results.map((result) => {
      if (!result.detail) return ["", "", "", "ERROR", 0, 0, result.error?.code ?? "ERROR", result.error?.message ?? ""];
      const detail = result.detail;
      const stopping = detail.timeline.find((entry) => ["BLOCKED", "WITHHELD", "REVIEW"].includes(entry.status));
      return [
        detail.product.mpn,
        detail.normalization.manufacturer ?? detail.product.raw_manufacturer,
        detail.classification.family ?? "",
        overallState(detail),
        detail.attributes.verified.length,
        detail.attributes.withheld.length,
        detail.source.blocker ?? "",
        stopping?.reason ?? "",
      ];
    }),
  );
}

export function verifiedFactsCsv(results: AnalyzedProduct[]): string {
  return csvFromRows(
    ["MPN", "Attribute", "Value", "UOM", "Source", "Verification", "Delivery Authority"],
    results.flatMap((result) =>
      (result.detail?.attributes.verified ?? []).map((attribute) => [
        result.detail?.product.mpn ?? "",
        attribute.label,
        attribute.value,
        attribute.uom ?? "",
        attribute.authority,
        attribute.status,
        attribute.delivery_eligible ? "AUTHORIZED" : attribute.unilog_mapping_status,
      ]),
    ),
  );
}

export function downloadText(filename: string, contents: string, mime = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([contents], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
