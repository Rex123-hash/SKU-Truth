"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, Info, ShieldCheck, XCircle } from "lucide-react";
import { useId, useState } from "react";
import type { ReactNode } from "react";

import type { EvidenceBasis, StageStatus } from "@/lib/types";
import { EVIDENCE_LABEL, EVIDENCE_TOOLTIP, STATUS_LABEL } from "@/lib/vocab";

/**
 * A blocked outcome is a feature of this system, not an embarrassment, so nothing here
 * is red-on-red alarm styling. Blocked and withheld are amber: the calm colour of "we
 * stopped on purpose", distinct from success green and from a genuine failure.
 */
const STATUS_STYLE: Record<StageStatus, { className: string; Icon: typeof CheckCircle2 }> = {
  SUCCESS: { className: "border-sage bg-sage-soft text-forest", Icon: CheckCircle2 },
  REVIEW: { className: "border-amber-soft bg-amber-wash text-[#8a6410]", Icon: AlertTriangle },
  WITHHELD: { className: "border-amber-soft bg-amber-wash text-[#8a6410]", Icon: XCircle },
  BLOCKED: { className: "border-amber-soft bg-amber-wash text-[#8a6410]", Icon: AlertTriangle },
  NOT_RUN: { className: "border-line bg-cream-soft text-muted", Icon: CircleDashed },
};

export function StageBadge({ status, label }: { status: StageStatus; label?: string }) {
  const { className, Icon } = STATUS_STYLE[status];
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium " +
        className
      }
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label ?? STATUS_LABEL[status]}
    </span>
  );
}

/**
 * Where a stage's reported outcome came from. `RECORDED_OBSERVATION` deliberately gets
 * its own outline treatment: an HTTP 429 cannot be replayed, and the UI must never let
 * an operator's written-down observation look like something the server re-derived.
 */
const BASIS_STYLE: Record<EvidenceBasis, string> = {
  DETERMINISTIC: "border-line bg-cream-soft text-muted",
  STORED_CASSETTE: "border-line bg-cream-soft text-muted",
  STORED_ARTIFACT: "border-sage bg-sage-soft text-forest",
  RECORDED_OBSERVATION: "border-dashed border-amber bg-amber-wash text-[#8a6410]",
};

export function TrustBasisBadge({
  basis,
  interactive = true,
}: {
  basis: EvidenceBasis;
  interactive?: boolean;
}) {
  const badge = (
    <span
      title={interactive ? undefined : EVIDENCE_TOOLTIP[basis]}
      className={
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium " +
        BASIS_STYLE[basis]
      }
    >
      {basis === "RECORDED_OBSERVATION" ? (
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {EVIDENCE_LABEL[basis]}
    </span>
  );

  return interactive ? <Tooltip label={EVIDENCE_TOOLTIP[basis]}>{badge}</Tooltip> : badge;
}

/** A keyboard-reachable tooltip. Hover alone would hide this from half the audience. */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-label={label}
        className="inline-flex cursor-help"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
      >
        {children}
      </button>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-40 mb-2 w-[248px] -translate-x-1/2 rounded-[10px] border border-line bg-card p-3 text-left text-[12.5px] leading-relaxed text-ink shadow-[var(--shadow-lift)]"
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}

/** The chip that names the code the pipeline actually emitted, verbatim. */
export function ReasonCode({ code, className = "" }: { code: string; className?: string }) {
  if (!code) return null;
  return (
    <code
      className={
        "inline-block max-w-full break-all rounded-md border border-line-soft bg-cream px-1.5 py-0.5 font-mono text-[11.5px] text-green " +
        className
      }
    >
      {code}
    </code>
  );
}
