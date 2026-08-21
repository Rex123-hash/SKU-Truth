"use client";

import Image from "next/image";
import { FileSpreadsheet, Keyboard, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/primitives";
import { MAX_FILE_BYTES } from "@/lib/catalog";

const inputClass = "w-full rounded-[10px] border border-line bg-card px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted/70";

export interface ManualValues {
  Mfg_Part_Num: string;
  Part_Desc: string;
  E1_Brand: string;
  Unilog_Brand: string;
  DIB_Brand: string;
  Part_Manuf: string;
}

const EMPTY_MANUAL: ManualValues = {
  Mfg_Part_Num: "", Part_Desc: "", E1_Brand: "", Unilog_Brand: "", DIB_Brand: "", Part_Manuf: "",
};

export function UploadScene({
  busy,
  progress,
  error,
  onFile,
  onTrySample,
  onManual,
}: {
  busy: boolean;
  progress: string;
  error: string;
  onFile: (file: File) => void;
  onTrySample: () => void;
  onManual: (values: ManualValues) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manual, setManual] = useState(EMPTY_MANUAL);

  const acceptFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
      <section
        className={
          "card-surface relative overflow-hidden border-2 border-dashed p-6 transition-colors sm:p-10 " +
          (dragging ? "border-olive bg-sage-soft/60" : "border-line")
        }
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFiles(event.dataTransfer.files); }}
      >
        <div className="relative z-10 max-w-[520px]">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-[14px] bg-sage-soft text-forest">
            <FileSpreadsheet className="h-6 w-6" aria-hidden="true" />
          </span>
          <h2 className="display-heading mt-5 text-[30px] text-ink sm:text-[36px]">Drop your catalog</h2>
          <p className="mt-2 text-[15px] leading-relaxed text-muted">CSV or XLSX · up to {MAX_FILE_BYTES / 1024 / 1024} MB · processed in your browser</p>

          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            onChange={(event) => acceptFiles(event.target.files)}
            disabled={busy}
          />
          <div className="mt-7 flex flex-wrap gap-3">
            <Button type="button" onClick={() => fileRef.current?.click()} disabled={busy}>
              <Upload className="h-4 w-4" aria-hidden="true" />
              Browse files
            </Button>
            <a href="/sample-catalog.csv" download className="inline-flex items-center justify-center rounded-full border border-line bg-card px-5 py-3 text-[14px] font-medium text-forest hover:border-sage">
              Download sample CSV
            </a>
          </div>
          <button type="button" onClick={onTrySample} disabled={busy} className="mt-4 text-[13.5px] font-medium text-green underline decoration-sage underline-offset-4 disabled:opacity-50">
            Try the sample catalog instantly
          </button>

          <div className="mt-7 min-h-7" aria-live="polite">
            {busy ? <p className="inline-flex items-center gap-2 text-[13.5px] font-medium text-forest"><span className="h-2 w-2 animate-pulse rounded-full bg-olive" />{progress}</p> : null}
            {error ? <p role="alert" className="rounded-[10px] border border-amber-soft bg-amber-wash px-4 py-3 text-[13.5px] text-[#73530d]">{error}</p> : null}
          </div>
        </div>
        <Image src="/art/mascot-barcode.png" alt="" aria-hidden="true" width={620} height={620} className="pointer-events-none absolute -bottom-12 -right-10 hidden w-[230px] opacity-80 sm:block" />
      </section>

      <section className="card-surface p-6 sm:p-7">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] bg-amber-wash text-[#8a6410]"><Keyboard className="h-5 w-5" aria-hidden="true" /></span>
        <h2 className="display-heading mt-4 text-[24px] text-ink">One product instead?</h2>
        <p className="mt-2 text-[14px] leading-relaxed text-muted">Enter a single organizer-style row and run the same trusted pipeline.</p>
        <button type="button" onClick={() => setManualOpen((open) => !open)} className="mt-5 text-[14px] font-semibold text-green underline decoration-sage underline-offset-4">
          {manualOpen ? "Close manual entry" : "Enter product manually"}
        </button>

        {manualOpen ? (
          <form className="mt-5 space-y-3" onSubmit={(event) => { event.preventDefault(); onManual(manual); }}>
            {([
              ["Mfg_Part_Num", "Manufacturer part number *"], ["Part_Desc", "Description"], ["Part_Manuf", "Manufacturer"],
              ["E1_Brand", "E1 brand"], ["Unilog_Brand", "Unilog brand"], ["DIB_Brand", "DIB brand"],
            ] as const).map(([field, label]) => (
              <label key={field} className="block text-[12.5px] font-medium text-muted">
                {label}
                <input required={field === "Mfg_Part_Num"} value={manual[field]} onChange={(event) => setManual((value) => ({ ...value, [field]: event.target.value }))} className={inputClass + " mt-1.5"} />
              </label>
            ))}
            <Button type="submit" className="mt-2 w-full">Prepare product</Button>
          </form>
        ) : null}
      </section>
    </div>
  );
}
