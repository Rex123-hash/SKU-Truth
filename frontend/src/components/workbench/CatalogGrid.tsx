"use client";

import { ChevronLeft, ChevronRight, Search, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/primitives";
import { StageBadge } from "@/components/Badges";
import { knownCaseForMpn, type CatalogRow, type CatalogStatus } from "@/lib/catalog";
import type { AnalyzedProduct } from "@/lib/exports";

const PAGE_SIZE = 20;
type SortKey = "mpn" | "manufacturer" | "status";
type OutcomeFilter = "ALL" | "ANALYZED" | "VERIFIED" | "PARTIAL" | "BLOCKED" | "REVIEW" | "NO_EVIDENCE";

function resultMatches(result: AnalyzedProduct | undefined, filter: OutcomeFilter): boolean {
  if (filter === "ALL") return true;
  if (!result) return false;
  if (filter === "ANALYZED") return true;
  if (!result.detail) return filter === "PARTIAL";
  const detail = result.detail;
  if (filter === "VERIFIED") return detail.attributes.verified.length > 0;
  if (filter === "BLOCKED") return detail.timeline.some((entry) => entry.status === "BLOCKED");
  if (filter === "REVIEW") return detail.attributes.withheld.length > 0 || detail.timeline.some((entry) => ["REVIEW", "WITHHELD"].includes(entry.status));
  if (filter === "NO_EVIDENCE") return detail.source.discovery_status === "NOT_RUN" && detail.attributes.verified.length === 0;
  return detail.timeline.some((entry) => entry.status === "NOT_RUN");
}

function recognition(row: CatalogRow) {
  const known = knownCaseForMpn(row.values.Mfg_Part_Num);
  if (known === "KICHLER") return { label: "Full replay available", tone: "text-forest bg-sage-soft border-sage" };
  if (known === "SATCO") return { label: "Recorded blocker case", tone: "text-[#8a6410] bg-amber-wash border-amber-soft" };
  if (known === "FEIT") return { label: "Recorded representation case", tone: "text-[#8a6410] bg-amber-wash border-amber-soft" };
  return null;
}

export function CatalogGrid({ rows, selected, results, analyzing, onToggle, onToggleAll, onAnalyze, onOpen }: {
  rows: CatalogRow[];
  selected: Set<string>;
  results: Map<string, AnalyzedProduct>;
  analyzing: Set<string>;
  onToggle: (id: string) => void;
  onToggleAll: (ids: string[]) => void;
  onAnalyze: (ids: string[]) => void;
  onOpen: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"ALL" | CatalogStatus>("ALL");
  const [manufacturer, setManufacturer] = useState("ALL");
  const [replayOnly, setReplayOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("mpn");
  const [page, setPage] = useState(1);
  const [outcome, setOutcome] = useState<OutcomeFilter>("ALL");

  const manufacturers = useMemo(() => Array.from(new Set(rows.map((row) => row.values.Part_Manuf).filter(Boolean))).sort(), [rows]);
  const resultList = Array.from(results.values());
  const summary: Array<[OutcomeFilter, string, number]> = [
    ["ANALYZED", "Analyzed", resultList.length],
    ["VERIFIED", "Verified products", resultList.filter((r) => resultMatches(r, "VERIFIED")).length],
    ["PARTIAL", "Partial", resultList.filter((r) => resultMatches(r, "PARTIAL")).length],
    ["BLOCKED", "Blocked", resultList.filter((r) => resultMatches(r, "BLOCKED")).length],
    ["REVIEW", "Review", resultList.filter((r) => resultMatches(r, "REVIEW")).length],
    ["NO_EVIDENCE", "No evidence", resultList.filter((r) => resultMatches(r, "NO_EVIDENCE")).length],
  ];

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows
      .filter((row) => !query || [row.values.Mfg_Part_Num, row.values.Part_Desc, row.values.Part_Manuf, row.values.E1_Brand].some((value) => value.toLowerCase().includes(query)))
      .filter((row) => status === "ALL" || row.status === status)
      .filter((row) => manufacturer === "ALL" || row.values.Part_Manuf === manufacturer)
      .filter((row) => !replayOnly || knownCaseForMpn(row.values.Mfg_Part_Num) !== null)
      .filter((row) => resultMatches(results.get(row.id), outcome))
      .sort((a, b) => {
        const av = sort === "mpn" ? a.values.Mfg_Part_Num : sort === "manufacturer" ? a.values.Part_Manuf : a.status;
        const bv = sort === "mpn" ? b.values.Mfg_Part_Num : sort === "manufacturer" ? b.values.Part_Manuf : b.status;
        return av.localeCompare(bv, undefined, { numeric: true });
      });
  }, [rows, search, status, manufacturer, replayOnly, sort, results, outcome]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const selectedAnalyzable = Array.from(selected).filter((id) => rows.find((row) => row.id === id)?.status !== "INVALID");

  const setFilter = <T,>(setter: (value: T) => void, value: T) => { setter(value); setPage(1); };

  return (
    <div className="space-y-5">
      {results.size ? (
        <section aria-label="Batch result summary" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {summary.map(([key, label, count]) => (
            <button key={key} type="button" aria-pressed={outcome === key} onClick={() => setFilter(setOutcome, outcome === key ? "ALL" : key)} className={"rounded-[12px] border p-3 text-left transition-colors " + (outcome === key ? "border-olive bg-sage-soft" : "border-line bg-card hover:border-sage")}>
              <strong className="display-heading block text-[24px] text-forest">{count}</strong><span className="text-[11.5px] text-muted">{label}</span>
            </button>
          ))}
        </section>
      ) : null}

      <section className="card-surface overflow-hidden">
        <header className="border-b border-line-soft p-4 sm:p-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="relative min-w-0 flex-1 xl:max-w-[350px]">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input aria-label="Search catalog" value={search} onChange={(e) => setFilter(setSearch, e.target.value)} placeholder="Search MPN, description, manufacturer…" className="w-full rounded-full border border-line bg-cream-soft py-2.5 pl-10 pr-4 text-[13.5px]" />
            </div>
            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              <select aria-label="Filter by row status" value={status} onChange={(e) => setFilter(setStatus, e.target.value as typeof status)} className="rounded-full border border-line bg-card px-3 py-2 text-[12.5px]"><option value="ALL">All statuses</option><option>READY</option><option>REVIEW</option><option>INVALID</option></select>
              <select aria-label="Filter by manufacturer" value={manufacturer} onChange={(e) => setFilter(setManufacturer, e.target.value)} className="min-w-0 rounded-full border border-line bg-card px-3 py-2 text-[12.5px]"><option value="ALL">All manufacturers</option>{manufacturers.map((name) => <option key={name}>{name}</option>)}</select>
              <select aria-label="Sort catalog" value={sort} onChange={(e) => setFilter(setSort, e.target.value as SortKey)} className="rounded-full border border-line bg-card px-3 py-2 text-[12.5px]"><option value="mpn">Sort: MPN</option><option value="manufacturer">Sort: manufacturer</option><option value="status">Sort: status</option></select>
              <label className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-2 text-[12.5px] text-ink"><input type="checkbox" checked={replayOnly} onChange={(e) => setFilter(setReplayOnly, e.target.checked)} /> Replay available</label>
            </div>
          </div>
          <div className="mt-4 flex flex-col gap-3 border-t border-line-soft pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[13px] text-muted">{filtered.length.toLocaleString()} shown · {selected.size} selected</p>
            <Button type="button" onClick={() => onAnalyze(selectedAnalyzable)} disabled={!selectedAnalyzable.length || analyzing.size > 0} className="w-full sm:w-auto">Analyze selected{selectedAnalyzable.length ? ` (${selectedAnalyzable.length})` : ""}</Button>
          </div>
        </header>

        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[940px] border-separate border-spacing-0 text-left">
            <thead className="bg-sage-soft/65 text-[11.5px] font-semibold uppercase tracking-[.08em] text-green"><tr>
              <th scope="col" className="px-4 py-4"><input type="checkbox" aria-label="Select visible rows" checked={visible.length > 0 && visible.every((row) => selected.has(row.id))} onChange={() => onToggleAll(visible.map((row) => row.id))} /></th>
              <th scope="col" className="px-3 py-4">MPN / evidence</th><th scope="col" className="px-3 py-4">Description</th><th scope="col" className="px-3 py-4">Manufacturer</th><th scope="col" className="px-3 py-4">Classification</th><th scope="col" className="px-3 py-4">Status</th><th scope="col" className="px-4 py-4 text-right">Action</th>
            </tr></thead>
            <tbody className="divide-y divide-line-soft">{visible.map((row) => <CatalogTableRow key={row.id} row={row} selected={selected.has(row.id)} result={results.get(row.id)} busy={analyzing.has(row.id)} onToggle={() => onToggle(row.id)} onAnalyze={() => onAnalyze([row.id])} onOpen={() => onOpen(row.id)} />)}</tbody>
          </table>
        </div>

        <ul className="divide-y divide-line-soft md:hidden">{visible.map((row) => <CatalogCard key={row.id} row={row} selected={selected.has(row.id)} result={results.get(row.id)} busy={analyzing.has(row.id)} onToggle={() => onToggle(row.id)} onAnalyze={() => onAnalyze([row.id])} onOpen={() => onOpen(row.id)} />)}</ul>
        {!visible.length ? <div className="px-6 py-14 text-center"><ShieldAlert className="mx-auto h-8 w-8 text-sage" /><p className="mt-3 text-[14px] text-muted">No catalog rows match this view.</p></div> : null}

        <footer className="flex items-center justify-between border-t border-line-soft px-4 py-3 text-[12.5px] text-muted">
          <span>Page {safePage} of {pageCount}</span><div className="flex gap-2"><button type="button" aria-label="Previous page" disabled={safePage === 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-full border border-line p-2 disabled:opacity-35"><ChevronLeft className="h-4 w-4" /></button><button type="button" aria-label="Next page" disabled={safePage === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} className="rounded-full border border-line p-2 disabled:opacity-35"><ChevronRight className="h-4 w-4" /></button></div>
        </footer>
      </section>
    </div>
  );
}

function ResultStatus({ result }: { result?: AnalyzedProduct }) {
  if (!result) return null;
  if (!result.detail) return <StageBadge status="BLOCKED" label="API error" />;
  if (result.detail.timeline.some((e) => e.status === "BLOCKED")) return <StageBadge status="BLOCKED" />;
  if (result.detail.attributes.verified.length) return <StageBadge status="SUCCESS" label="Analyzed" />;
  if (result.detail.timeline.some((e) => e.status === "REVIEW")) return <StageBadge status="REVIEW" />;
  return <StageBadge status="NOT_RUN" label="Partial" />;
}

function ReplayBadge({ row }: { row: CatalogRow }) { const item = recognition(row); return item ? <span className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[.06em] ${item.tone}`}>{item.label}</span> : <span className="mt-2 block text-[12px] text-muted">No replay evidence</span>; }

function CatalogTableRow({ row, selected, result, busy, onToggle, onAnalyze, onOpen }: { row: CatalogRow; selected: boolean; result?: AnalyzedProduct; busy: boolean; onToggle: () => void; onAnalyze: () => void; onOpen: () => void }) {
  return <tr className="align-top transition-colors hover:bg-sage-soft/25"><td className="px-4 py-5"><input type="checkbox" aria-label={`Select ${row.values.Mfg_Part_Num || `row ${row.sourceIndex}`}`} checked={selected} onChange={onToggle} disabled={row.status === "INVALID"} /></td><td className="px-3 py-5"><code className="text-[13.5px] font-semibold text-ink">{row.values.Mfg_Part_Num || "—"}</code><ReplayBadge row={row} /></td><td className="max-w-[260px] px-3 py-5 text-[13.5px] leading-relaxed text-muted">{row.values.Part_Desc || "—"}</td><td className="px-3 py-5 text-[13.5px] text-ink">{row.values.Part_Manuf || row.values.E1_Brand || "—"}</td><td className="px-3 py-5 text-[13.5px] text-muted">{result?.detail?.classification.family ?? "Not analyzed"}</td><td className="px-3 py-5"><ResultStatus result={result} />{!result ? <StageBadge status={row.status === "READY" ? "SUCCESS" : row.status === "REVIEW" ? "REVIEW" : "BLOCKED"} label={row.status} /> : null}{row.issues.length ? <p title={row.issues.join("; ")} className="mt-2 max-w-[150px] truncate text-[11.5px] text-muted">{row.issues.join(" · ")}</p> : null}</td><td className="px-4 py-5 text-right"><button type="button" disabled={row.status === "INVALID" || busy} onClick={result ? onOpen : onAnalyze} className="text-[13px] font-semibold text-green underline decoration-sage underline-offset-4 disabled:text-muted">{busy ? "Analyzing…" : result ? "Open result" : "Analyze"}</button></td></tr>;
}

function CatalogCard(props: Parameters<typeof CatalogTableRow>[0]) {
  const { row, selected, result, busy, onToggle, onAnalyze, onOpen } = props;
  return <li className="p-5"><div className="flex items-start justify-between gap-3"><label className="flex min-w-0 items-start gap-3"><input type="checkbox" checked={selected} onChange={onToggle} disabled={row.status === "INVALID"} className="mt-1" /><span className="min-w-0"><code className="block break-all text-[14px] font-semibold">{row.values.Mfg_Part_Num || "—"}</code><span className="mt-1 block text-[13px] text-muted">{row.values.Part_Manuf || row.values.E1_Brand || "No manufacturer"}</span></span></label><ResultStatus result={result} /></div><p className="mt-3 line-clamp-2 text-[13.5px] leading-relaxed text-muted">{row.values.Part_Desc || "No description"}</p><ReplayBadge row={row} /><div className="mt-4 flex items-center justify-between"><span>{!result ? <StageBadge status={row.status === "READY" ? "SUCCESS" : row.status === "REVIEW" ? "REVIEW" : "BLOCKED"} label={row.status} /> : null}</span><button type="button" disabled={row.status === "INVALID" || busy} onClick={result ? onOpen : onAnalyze} className="text-[13px] font-semibold text-green">{busy ? "Analyzing…" : result ? "Open result" : "Analyze"}</button></div></li>;
}
