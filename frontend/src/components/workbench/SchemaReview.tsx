"use client";

import { CheckCircle2, CircleDashed, RotateCcw } from "lucide-react";

import { Button } from "@/components/primitives";
import { CATALOG_FIELDS, FIELD_LABELS, type CatalogField, type ColumnMapping, type ParsedCatalog } from "@/lib/catalog";

export function SchemaReview({ parsed, mapping, onChange, onReset, onContinue, onBack }: {
  parsed: ParsedCatalog;
  mapping: ColumnMapping;
  onChange: (field: CatalogField, header: string) => void;
  onReset: () => void;
  onContinue: () => void;
  onBack: () => void;
}) {
  const minimumReady = Boolean(mapping.Mfg_Part_Num);
  const mapped = new Set(Object.values(mapping).filter(Boolean));
  const extras = parsed.headers.filter((header) => !mapped.has(header));

  return (
    <section className="card-surface overflow-hidden">
      <header className="flex flex-col gap-4 border-b border-line-soft p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[.14em] text-olive">Schema review</p>
          <h2 className="display-heading mt-1.5 text-[27px] text-ink">Match your catalog fields</h2>
          <p className="mt-1 text-[13.5px] text-muted">{parsed.fileName} · {parsed.records.length.toLocaleString()} rows · {parsed.headers.length} columns</p>
        </div>
        <button type="button" onClick={onReset} className="inline-flex items-center gap-2 text-[13px] font-medium text-green"><RotateCcw className="h-4 w-4" />Auto-detect again</button>
      </header>

      <div className="grid gap-3 p-6 lg:grid-cols-2">
        {CATALOG_FIELDS.map((field) => {
          const match = mapping[field];
          return (
            <label key={field} className="rounded-[12px] border border-line-soft bg-cream-soft/50 p-4">
              <span className="flex items-center justify-between gap-3">
                <span className="text-[13.5px] font-semibold text-ink">{FIELD_LABELS[field]}{field === "Mfg_Part_Num" ? " *" : ""}</span>
                <span className={"inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[.08em] " + (match ? "text-forest" : "text-muted")}>
                  {match ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleDashed className="h-3.5 w-3.5" />}{match ? (match === field ? "Matched" : "Mapped") : "Missing"}
                </span>
              </span>
              <select aria-label={`Map ${FIELD_LABELS[field]}`} value={match} onChange={(event) => onChange(field, event.target.value)} className="mt-3 w-full rounded-[9px] border border-line bg-card px-3 py-2.5 text-[13.5px] text-ink">
                <option value="">Not mapped</option>
                {parsed.headers.map((header) => <option key={header} value={header}>{header}</option>)}
              </select>
            </label>
          );
        })}
      </div>

      <div className="border-t border-line-soft px-6 py-5">
        <p className="text-[12px] font-semibold uppercase tracking-[.09em] text-muted">Extra columns preserved ({extras.length})</p>
        <p className="mt-2 text-[13px] text-muted">{extras.length ? extras.join(", ") : "None"}</p>
        {parsed.warnings.map((warning) => <p key={warning} className="mt-2 text-[13px] text-[#8a6410]">{warning}</p>)}
        {!minimumReady ? <p role="alert" className="mt-3 text-[13.5px] text-[#8a6410]">Map a manufacturer part number before continuing.</p> : null}
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onBack}>Choose another file</Button>
          <Button type="button" onClick={onContinue} disabled={!minimumReady}>Prepare catalog</Button>
        </div>
      </div>
    </section>
  );
}
