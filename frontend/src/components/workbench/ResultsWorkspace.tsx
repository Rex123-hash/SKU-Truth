"use client";

import Link from "next/link";
import { Download, ExternalLink, FileWarning, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { AttributeTable } from "@/components/AttributeTable";
import { ReasonCode, StageBadge, TrustBasisBadge } from "@/components/Badges";
import { JourneyCounts, JourneyTimeline } from "@/components/JourneyTimeline";
import { Button } from "@/components/primitives";
import type { CatalogRow } from "@/lib/catalog";
import { analysisReportCsv, downloadText, verifiedFactsCsv, type AnalyzedProduct } from "@/lib/exports";
import { slugForCaseId } from "@/lib/cases";

type Tab = "VERIFIED" | "WITHHELD" | "BLOCKED" | "DELIVERY" | "RAW";

export function ResultsWorkspace({ active, row, results }: { active?: AnalyzedProduct; row?: CatalogRow; results: Map<string, AnalyzedProduct> }) {
  const [tab, setTab] = useState<Tab>("VERIFIED");
  const allResults = Array.from(results.values());

  if (!active) {
    return <section className="card-surface p-7 text-center"><ShieldCheck className="mx-auto h-9 w-9 text-sage" /><h2 className="display-heading mt-3 text-[23px]">Analysis results open here</h2><p className="mt-2 text-[13.5px] text-muted">Analyze a ready product, then inspect its stages, evidence, and delivery boundary.</p></section>;
  }

  if (!active.detail) {
    return <section className="rounded-[16px] border border-amber-soft bg-amber-wash p-6"><FileWarning className="h-7 w-7 text-[#8a6410]" /><h2 className="display-heading mt-3 text-[24px]">Analysis did not complete</h2><ReasonCode code={active.error?.code ?? "UNREACHABLE"} className="mt-3" /><p className="mt-3 text-[14px] leading-relaxed text-ink">{active.error?.message}</p><p className="mt-2 text-[13px] text-muted">No fallback result was fabricated. Retry from the catalog when the API is available.</p></section>;
  }

  const detail = active.detail;
  const slug = slugForCaseId(detail.case_id);
  const unknown = detail.source.discovery_status === "NOT_RUN" && detail.attributes.verified.length === 0;
  const blocked = detail.timeline.filter((entry) => entry.status === "BLOCKED");

  return (
    <section className="space-y-5" aria-live="polite">
      <div className="card-surface overflow-hidden">
        <header className="border-b border-line-soft bg-forest px-5 py-5 text-cream sm:px-7">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10.5px] font-semibold uppercase tracking-[.14em] text-cream/65">Pipeline result</p>
              <h2 className="display-heading mt-1.5 break-all text-[29px]">{detail.product.mpn}</h2>
              <p className="mt-1.5 text-[13.5px] text-cream/75">{(detail.normalization.manufacturer ?? detail.product.raw_manufacturer) || "Manufacturer withheld"} · {detail.classification.family ?? "Classification withheld"}</p>
            </div>
            <div className="flex flex-wrap gap-2"><span className="rounded-full border border-cream/25 px-3 py-1 text-[11px]">{detail.mode}</span>{detail.timeline.some((entry) => entry.evidence === "RECORDED_OBSERVATION") ? <span className="rounded-full border border-amber-soft bg-amber-wash px-3 py-1 text-[11px] font-semibold text-[#73530d]">Recorded observation</span> : null}</div>
          </div>
        </header>

        <div className="p-5 sm:p-7">
          <p className="text-[14px] leading-relaxed text-ink">{detail.headline}</p>
          {unknown ? <div className="mt-4 rounded-[12px] border border-line bg-cream-soft p-4 text-[13.5px] leading-relaxed text-muted"><strong className="text-ink">No replay evidence exists for this product.</strong> SKUTruth completed the deterministic stages available in this public demo. Source-backed enrichment was not invented.</div> : null}
          {slug ? <Link href={`/demo/${slug}`} className="mt-4 inline-flex items-center gap-2 text-[13px] font-semibold text-green underline decoration-sage underline-offset-4">Inspect the full evidence case <ExternalLink className="h-3.5 w-3.5" /></Link> : null}

          <div className="mt-6"><JourneyTimeline timeline={detail.timeline} /></div>
          <div className="mt-5"><JourneyCounts proposals={detail.ai.proposal_count} sourceBound={detail.ai.source_bound_count} verified={detail.attributes.verified.length} withheld={detail.attributes.withheld.length} mapped={detail.delivery.mapped_count} mappingStatus={detail.delivery.mapping_status} unauthorizedReason={detail.delivery.unauthorized_reason} /></div>
        </div>
      </div>

      <div className="card-surface overflow-hidden">
        <div role="tablist" aria-label="Result views" className="flex overflow-x-auto border-b border-line-soft px-3 pt-2">
          {(["VERIFIED", "WITHHELD", "BLOCKED", "DELIVERY", "RAW"] as Tab[]).map((item) => <button key={item} role="tab" aria-selected={tab === item} type="button" onClick={() => setTab(item)} className={"whitespace-nowrap border-b-2 px-3 py-3 text-[12.5px] font-semibold " + (tab === item ? "border-olive text-forest" : "border-transparent text-muted")}>{item === "RAW" ? "Raw input" : item[0] + item.slice(1).toLowerCase()}</button>)}
        </div>
        <div role="tabpanel" className="p-5 sm:p-7">
          {tab === "VERIFIED" ? detail.attributes.verified.length ? <AttributeTable view="verified" attributes={detail.attributes} /> : <Empty text="No verified manufacturer facts exist for this product." /> : null}
          {tab === "WITHHELD" ? detail.attributes.withheld.length ? <AttributeTable view="withheld" attributes={detail.attributes} /> : <Empty text="No withheld attribute proposals exist for this product." /> : null}
          {tab === "BLOCKED" ? blocked.length ? <ul className="space-y-3">{blocked.map((entry) => <li key={entry.stage} className="rounded-[12px] border border-amber-soft bg-amber-wash/60 p-4"><div className="flex flex-wrap items-center gap-2"><StageBadge status="BLOCKED" /><strong className="text-[14px] text-ink">{entry.stage.replaceAll("_", " ")}</strong><ReasonCode code={entry.reason} /></div><p className="mt-2 text-[13px] leading-relaxed text-muted">{entry.detail}</p><div className="mt-3"><TrustBasisBadge basis={entry.evidence} interactive={false} /></div></li>)}</ul> : <Empty text="No blocked pipeline stages exist for this product." /> : null}
          {tab === "DELIVERY" ? <div><div className="flex items-center gap-3"><strong className="display-heading text-[32px] text-forest">{detail.delivery.mapped_count}</strong><span className="text-[13px] text-muted">authorized delivery mappings</span></div><ReasonCode code={detail.delivery.mapping_status} className="mt-3" /><p className="mt-3 max-w-[700px] text-[13.5px] leading-relaxed text-muted">{detail.delivery.unauthorized_reason || "Only fields authorized by the backend delivery contract can appear here."}</p><p className="mt-4 rounded-[10px] border border-line bg-cream-soft p-3 text-[12.5px] text-muted">The public API does not expose a complete 252-column DeliveryRecord for this workflow, so SKUTruth does not fabricate a frontend-only Unilog export.</p></div> : null}
          {tab === "RAW" ? <dl className="grid gap-3 sm:grid-cols-2">{Object.entries(row?.values ?? {}).map(([key, value]) => <div key={key} className="rounded-[10px] border border-line-soft bg-cream-soft p-3"><dt className="font-mono text-[10.5px] text-muted">{key}</dt><dd className="mt-1 break-words text-[13.5px] text-ink">{value || "—"}</dd></div>)}</dl> : null}
        </div>
      </div>

      <section className="card-surface p-5 sm:p-7">
        <h2 className="display-heading text-[24px] text-ink">Export structured results</h2>
        <p className="mt-2 text-[13.5px] text-muted">Exports include only current API results. Verified facts remain separate from delivery authority.</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button type="button" onClick={() => downloadText("skutruth-analysis-report.csv", analysisReportCsv(allResults))}><Download className="h-4 w-4" />Analysis CSV</Button>
          <Button type="button" variant="secondary" onClick={() => downloadText("skutruth-verified-facts.csv", verifiedFactsCsv(allResults))}><Download className="h-4 w-4" />Verified facts CSV</Button>
        </div>
      </section>
    </section>
  );
}

function Empty({ text }: { text: string }) { return <div className="rounded-[12px] border border-dashed border-line bg-cream-soft/50 px-5 py-9 text-center text-[13.5px] text-muted">{text}</div>; }

export function ReviewQueue({ results, onOpen }: { results: Map<string, AnalyzedProduct>; onOpen: (rowId: string) => void }) {
  const items = useMemo(() => Array.from(results.values()).flatMap((result) => {
    const detail = result.detail;
    if (!detail) return [{ key: `${result.rowId}-api`, rowId: result.rowId, mpn: "Unknown row", stage: "API", value: "Analysis unavailable", reason: result.error?.code ?? "UNREACHABLE", evidence: "Not available" }];
    const withheld = detail.attributes.withheld.map((attribute) => ({ key: `${result.rowId}-${attribute.source_key}`, rowId: result.rowId, mpn: detail.product.mpn, stage: "Verification", value: `${attribute.label}: ${attribute.proposed_value}`, reason: attribute.reason, evidence: attribute.locator ? "Manufacturer locator available" : "No source-backed evidence" }));
    const blockers = detail.timeline.filter((entry) => ["BLOCKED", "REVIEW", "WITHHELD"].includes(entry.status)).map((entry) => ({ key: `${result.rowId}-${entry.stage}`, rowId: result.rowId, mpn: detail.product.mpn, stage: entry.stage.replaceAll("_", " "), value: entry.detail, reason: entry.reason, evidence: entry.evidence.replaceAll("_", " ") }));
    return [...withheld, ...blockers];
  }), [results]);

  return <section className="card-surface p-5 sm:p-7"><div className="flex items-baseline gap-3"><h2 className="display-heading text-[25px] text-ink">Review Queue</h2><span className="rounded-full border border-amber-soft bg-amber-wash px-2.5 py-0.5 text-[12px] font-semibold text-[#8a6410]">{items.length}</span></div><p className="mt-2 text-[13.5px] text-muted">Withheld facts and blocked or review stages. Actions inspect the truth; they never override it.</p>{items.length ? <ul className="mt-5 grid gap-3 lg:grid-cols-2">{items.map((item) => <li key={item.key} className="rounded-[12px] border border-line bg-cream-soft/55 p-4"><div className="flex items-start justify-between gap-3"><div><code className="text-[12px] font-semibold text-green">{item.mpn}</code><p className="mt-1 text-[11px] font-semibold uppercase tracking-[.08em] text-muted">{item.stage}</p></div><ReasonCode code={item.reason} /></div><p className="mt-3 text-[13px] leading-relaxed text-ink">{item.value}</p><p className="mt-2 text-[11.5px] text-muted">Evidence: {item.evidence}</p><button type="button" onClick={() => onOpen(item.rowId)} className="mt-3 text-[12.5px] font-semibold text-green underline decoration-sage underline-offset-4">Open product</button></li>)}</ul> : <Empty text="No withheld or blocked items in this view." />}</section>;
}
