"use client";

import Image from "next/image";
import { Database, FileCheck2, Plus, Rows3, ShieldCheck } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Container, Eyebrow } from "@/components/primitives";
import { MetricCard } from "@/components/MetricCard";
import { analyzeRow, SkuTruthApiError } from "@/lib/api";
import {
  BATCH_ANALYSIS_LIMIT,
  CATALOG_FIELDS,
  applyColumnMapping,
  autoDetectMapping,
  emptyMapping,
  matrixToParsedCatalog,
  parseCatalogFile,
  toAnalyzeRequest,
  type CatalogField,
  type CatalogRow,
  type ColumnMapping,
  type ParsedCatalog,
  type WorkspaceState,
} from "@/lib/catalog";
import type { AnalyzedProduct } from "@/lib/exports";
import { CatalogGrid } from "./CatalogGrid";
import { ResultsWorkspace, ReviewQueue } from "./ResultsWorkspace";
import { SchemaReview } from "./SchemaReview";
import { UploadScene, type ManualValues } from "./UploadScene";

const stateLabel: Record<WorkspaceState, string> = {
  EMPTY: "Waiting for catalog", PARSING: "Reading catalog", SCHEMA_REVIEW: "Review schema", READY: "Catalog ready", ANALYZING: "Analyzing", RESULTS: "Results ready", PARTIAL: "Partial results", ERROR: "Import error",
};

export function WorkbenchShell() {
  const [state, setState] = useState<WorkspaceState>("EMPTY");
  const [progress, setProgress] = useState("");
  const [message, setMessage] = useState("");
  const [parsed, setParsed] = useState<ParsedCatalog | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>(emptyMapping());
  const [rows, setRows] = useState<CatalogRow[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<Map<string, AnalyzedProduct>>(new Map());
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set());
  const [activeRowId, setActiveRowId] = useState<string>();

  const counts = useMemo(() => ({
    ready: rows.filter((row) => row.status === "READY").length,
    review: rows.filter((row) => row.status === "REVIEW").length,
    invalid: rows.filter((row) => row.status === "INVALID").length,
    replay: rows.filter((row) => ["45297BK", "62-1875", "SHOP/4X2/840/V1"].includes(row.values.Mfg_Part_Num.trim().toUpperCase())).length,
  }), [rows]);

  const importFile = useCallback(async (file: File) => {
    setState("PARSING"); setMessage(""); setProgress("Reading file");
    try {
      const next = await parseCatalogFile(file);
      setProgress("Checking fields");
      const detected = autoDetectMapping(next.headers);
      setParsed(next); setMapping(detected);
      try { sessionStorage.setItem("skutruth:last-mapping", JSON.stringify(detected)); sessionStorage.setItem("skutruth:last-import", JSON.stringify({ name: file.name, rows: next.records.length })); } catch { /* storage is optional */ }
      setState("SCHEMA_REVIEW"); setProgress("");
    } catch (error) {
      setState("ERROR"); setProgress(""); setMessage(error instanceof Error ? error.message : "The catalog could not be read.");
    }
  }, []);

  const trySample = useCallback(async () => {
    setState("PARSING"); setProgress("Loading the safe sample catalog"); setMessage("");
    try {
      const response = await fetch("/sample-catalog.csv");
      if (!response.ok) throw new Error("The sample catalog is unavailable.");
      await importFile(new File([await response.blob()], "sample-catalog.csv", { type: "text/csv" }));
    } catch (error) {
      setState("ERROR"); setProgress(""); setMessage(error instanceof Error ? error.message : "The sample catalog is unavailable.");
    }
  }, [importFile]);

  const prepareRows = useCallback(() => {
    if (!parsed) return;
    setProgress("Preparing rows");
    const nextRows = applyColumnMapping(parsed, mapping);
    setRows(nextRows); setSelected(new Set()); setResults(new Map()); setActiveRowId(undefined); setState("READY"); setProgress(""); setMessage("");
  }, [parsed, mapping]);

  const prepareManual = useCallback((values: ManualValues) => {
    const next = matrixToParsedCatalog([CATALOG_FIELDS as unknown as string[], CATALOG_FIELDS.map((field) => values[field])], { fileName: "Manual product", fileSize: 0 });
    const nextRows = applyColumnMapping(next, Object.fromEntries(CATALOG_FIELDS.map((field) => [field, field])) as ColumnMapping);
    setParsed(next); setMapping(autoDetectMapping(next.headers)); setRows(nextRows); setSelected(new Set([nextRows[0].id])); setResults(new Map()); setActiveRowId(undefined); setMessage(""); setState("READY");
  }, []);

  const analyze = useCallback(async (ids: string[]) => {
    const requested = ids.slice(0, BATCH_ANALYSIS_LIMIT);
    if (ids.length > BATCH_ANALYSIS_LIMIT) setMessage(`Public batch analysis is limited to ${BATCH_ANALYSIS_LIMIT} products. The first ${BATCH_ANALYSIS_LIMIT} were queued.`); else setMessage("");
    setState("ANALYZING"); setAnalyzing(new Set(requested));
    if (requested.length) setActiveRowId(requested[0]);
    let partial = false;
    for (const id of requested) {
      const row = rows.find((item) => item.id === id);
      if (!row || row.status === "INVALID") { setAnalyzing((current) => { const next = new Set(current); next.delete(id); return next; }); continue; }
      try {
        const detail = await analyzeRow(toAnalyzeRequest(row));
        if (detail.timeline.some((entry) => entry.status !== "SUCCESS")) partial = true;
        setResults((current) => new Map(current).set(id, { rowId: id, detail }));
      } catch (error) {
        partial = true;
        const failure = error instanceof SkuTruthApiError ? { code: error.code, message: error.message } : { code: "UNEXPECTED_ERROR", message: error instanceof Error ? error.message : "Analysis failed." };
        setResults((current) => new Map(current).set(id, { rowId: id, error: failure }));
      } finally {
        setAnalyzing((current) => { const next = new Set(current); next.delete(id); return next; });
      }
    }
    setState(partial ? "PARTIAL" : "RESULTS");
  }, [rows]);

  const reset = useCallback(() => {
    if (results.size && !window.confirm("Clear this catalog and its current analysis results?")) return;
    setState("EMPTY"); setParsed(null); setMapping(emptyMapping()); setRows([]); setSelected(new Set()); setResults(new Map()); setAnalyzing(new Set()); setActiveRowId(undefined); setMessage("");
  }, [results.size]);

  const toggle = (id: string) => setSelected((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const toggleAll = (ids: string[]) => setSelected((current) => { const next = new Set(current); const allSelected = ids.every((id) => next.has(id)); ids.forEach((id) => allSelected ? next.delete(id) : next.add(id)); return next; });
  const active = activeRowId ? results.get(activeRowId) : undefined;
  const activeRow = rows.find((row) => row.id === activeRowId);
  const hasCatalog = !["EMPTY", "PARSING", "ERROR", "SCHEMA_REVIEW"].includes(state);

  return (
    <>
      <section className="dark-section relative overflow-hidden border-b border-[var(--border-dark-soft)] py-9 sm:py-11">
        <Container>
          <div className="flex items-center justify-between gap-6">
            <div><Eyebrow className="border-[var(--border-dark)] bg-cream/10 text-cream">Product workspace</Eyebrow><h1 className="display-heading mt-4 text-[37px] sm:text-[46px]">Catalog Workbench</h1><p className="mt-3 max-w-[650px] text-[16px] leading-relaxed text-[var(--text-on-dark-secondary)]">Bring organizer data into the real SKUTruth pipeline. What can be verified is shown; what cannot is visibly withheld.</p></div>
            <Image src="/art/crate-sku.png" alt="" aria-hidden="true" width={620} height={620} className="hidden w-[150px] opacity-80 sm:block" />
          </div>
        </Container>
      </section>

      <Container className="py-7 sm:py-9">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-[12.5px] text-muted"><span className={"h-2.5 w-2.5 rounded-full " + (state === "ERROR" ? "bg-amber" : state === "ANALYZING" ? "animate-pulse bg-amber" : "bg-olive")} /><span aria-live="polite">{stateLabel[state]}</span></div>
          {hasCatalog ? <button type="button" onClick={reset} className="inline-flex items-center gap-2 self-start text-[13px] font-semibold text-green"><Plus className="h-4 w-4" />New catalog</button> : null}
        </div>

        {state === "EMPTY" || state === "PARSING" || state === "ERROR" ? <UploadScene busy={state === "PARSING"} progress={progress} error={message} onFile={importFile} onTrySample={trySample} onManual={prepareManual} /> : null}
        {state === "SCHEMA_REVIEW" && parsed ? <SchemaReview parsed={parsed} mapping={mapping} onChange={(field: CatalogField, header: string) => setMapping((value) => ({ ...value, [field]: header }))} onReset={() => setMapping(autoDetectMapping(parsed.headers))} onContinue={prepareRows} onBack={reset} /> : null}

        {hasCatalog ? <div className="space-y-7">
          <section className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {[[Rows3, rows.length, "Rows"], [FileCheck2, counts.ready, "Ready"], [Database, counts.review, "Review"], [Database, counts.invalid, "Invalid"], [ShieldCheck, counts.replay, "Replay evidence"]].map(([Icon, value, label]) => { const IconComponent = Icon as typeof Rows3; return <MetricCard key={String(label)} eyebrow="Catalog" value={String(value)} label={String(label)} className="p-4" detail={<IconComponent className="h-4 w-4 text-olive" />} />; })}
          </section>
          {message ? <p role="status" className="rounded-[10px] border border-amber-soft bg-amber-wash px-4 py-3 text-[13px] text-[#73530d]">{message}</p> : null}
          <CatalogGrid rows={rows} selected={selected} results={results} analyzing={analyzing} onToggle={toggle} onToggleAll={toggleAll} onAnalyze={analyze} onOpen={setActiveRowId} />
          <div id="results" className="scroll-mt-24"><ResultsWorkspace active={active} row={activeRow} results={results} /></div>
          {results.size ? <ReviewQueue results={results} onOpen={(id) => { setActiveRowId(id); document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }); }} /> : null}
        </div> : null}
      </Container>
    </>
  );
}
