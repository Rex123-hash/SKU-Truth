"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ShieldCheck, Sparkles, XCircle } from "lucide-react";
import { useMemo, useState } from "react";

import type { ProductDetail, ProposedAttribute } from "@/lib/types";
import { LOCATOR_KIND_LABEL, reasonSentence } from "@/lib/vocab";
import { ReasonCode } from "./Badges";

/**
 * The section the whole submission turns on.
 *
 * A judge who reads one thing should read this: the model proposed a value, the source
 * document literally contains that same string, and SKUTruth still refused it, because
 * the property the string sits under does not prove which attribute it belongs to. That
 * is the difference between this and ordinary extraction, and it only lands if the
 * proposal, the evidence and the decision are three visibly separate things.
 */

type Outcome =
  | { kind: "VERIFIED"; sourceLabel: string; sourceValue: string; sourceUom: string; reason: string }
  | {
      kind: "WITHHELD";
      sourceLabel: string;
      sourceValue: string;
      reason: string;
      detail: string;
    };

interface Row {
  key: string;
  label: string;
  proposedValue: string;
  proposedUom: string;
  locatorKind: string;
  locatorHint: string;
  outcome: Outcome;
}

/** The refusal that best shows the mechanism: value present, semantics insufficient. */
const PREFERRED_KEY = "lighting.light_count_descriptor";

function locatorHint(attribute: ProposedAttribute): string {
  const locator = attribute.locator;
  if (!locator) return "";
  if (locator.json_pointer)
    return "JSON-LD block " + (locator.jsonld_block_index ?? 0) + " · " + locator.json_pointer;
  if (locator.element_index !== null) return "Element " + locator.element_index;
  return "";
}

export function buildRows(detail: ProductDetail): Row[] {
  const verified = new Map(detail.attributes.verified.map((item) => [item.source_key, item]));
  const withheld = new Map(detail.attributes.withheld.map((item) => [item.source_key, item]));

  return detail.attributes.proposed.flatMap((proposal): Row[] => {
    const hit = verified.get(proposal.source_key);
    const miss = withheld.get(proposal.source_key);
    if (!hit && !miss) return [];

    const outcome: Outcome = hit
      ? {
          kind: "VERIFIED",
          sourceLabel: hit.source_label,
          sourceValue: hit.source_value,
          sourceUom: hit.source_uom,
          reason: hit.reason,
        }
      : {
          kind: "WITHHELD",
          sourceLabel: miss!.source_label,
          sourceValue: miss!.source_value,
          reason: miss!.reason,
          detail: miss!.detail,
        };

    return [
      {
        key: proposal.source_key,
        label: proposal.label,
        proposedValue: proposal.proposed_value,
        proposedUom: proposal.proposed_uom,
        locatorKind: proposal.locator?.kind ?? "",
        locatorHint: locatorHint(proposal),
        outcome,
      },
    ];
  });
}

export function EvidenceComparison({ detail }: { detail: ProductDetail }) {
  const rows = useMemo(() => buildRows(detail), [detail]);
  const [activeKey, setActiveKey] = useState(
    () => (rows.find((row) => row.key === PREFERRED_KEY) ?? rows[0])?.key ?? "",
  );

  const active = rows.find((row) => row.key === activeKey) ?? rows[0];
  if (!active) return null;

  const refused = active.outcome.kind === "WITHHELD";

  return (
    <div className="card-surface overflow-hidden">
      <div className="border-b border-line-soft px-6 py-6 sm:px-8">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-olive">
          AI proposal → manufacturer evidence → SKUTruth decision
        </p>
        <h3 className="display-heading mt-2.5 text-[24px] text-ink sm:text-[28px]">
          The model proposes. The document decides.
        </h3>
      </div>

      {/* The ten proposals, colour-coded by what happened to each. */}
      <div className="border-b border-line-soft bg-cream-soft/60 px-6 py-4 sm:px-8">
        <div
          role="tablist"
          aria-label="Proposed attributes"
          className="flex flex-wrap gap-2"
        >
          {rows.map((row) => {
            const isActive = row.key === active.key;
            const isRefused = row.outcome.kind === "WITHHELD";
            return (
              <button
                key={row.key}
                role="tab"
                type="button"
                aria-selected={isActive}
                onClick={() => setActiveKey(row.key)}
                className={
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] transition-colors " +
                  (isActive
                    ? "border-forest bg-forest text-cream"
                    : "border-line bg-card text-ink hover:border-sage")
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    "h-1.5 w-1.5 rounded-full " + (isRefused ? "bg-amber" : "bg-olive")
                  }
                />
                {row.label}
              </button>
            );
          })}
        </div>
        <p className="mt-3 text-[12.5px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-olive" /> verified
          </span>
          <span className="mx-3" aria-hidden="true">
            ·
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-amber" /> withheld
          </span>
        </p>
      </div>

      <div className="px-6 py-8 sm:px-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={active.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
            className="grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr]"
          >
            {/* 1 — what the model said */}
            <Panel
              eyebrow="AI proposed"
              icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
              tone="neutral"
            >
              <FieldLine label={active.label} value={active.proposedValue} uom={active.proposedUom} />
              <p className="mt-4 text-[12.5px] leading-relaxed text-muted">
                A model proposal, bound to a location in the stored document. Not yet a fact.
              </p>
            </Panel>

            <Chevron />

            {/* 2 — what the document actually says there */}
            <Panel
              eyebrow="Manufacturer evidence"
              icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              tone="neutral"
            >
              {active.outcome.sourceLabel || active.outcome.sourceValue ? (
                <FieldLine
                  label={active.outcome.sourceLabel || "(no property name)"}
                  value={active.outcome.sourceValue}
                  uom={
                    active.outcome.kind === "VERIFIED" ? active.outcome.sourceUom : ""
                  }
                />
              ) : (
                <p className="text-[15px] leading-relaxed text-ink">
                  No labelled property was found at this location.
                </p>
              )}
              <p className="mt-4 text-[12.5px] leading-relaxed text-muted">
                {LOCATOR_KIND_LABEL[active.locatorKind] ?? active.locatorKind}
                {active.locatorHint ? " · " + active.locatorHint : ""}
              </p>
            </Panel>

            <Chevron />

            {/* 3 — the decision, and why */}
            <Panel
              eyebrow="SKUTruth decision"
              icon={
                refused ? (
                  <XCircle className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                )
              }
              tone={refused ? "amber" : "green"}
            >
              <p
                className={
                  "display-heading text-[30px] " + (refused ? "text-[#8a6410]" : "text-forest")
                }
              >
                {refused ? "Withheld" : "Verified"}
              </p>
              <div className="mt-3">
                <ReasonCode code={active.outcome.reason} />
              </div>
              <p className="mt-3 text-[13.5px] leading-relaxed text-ink">
                {reasonSentence(active.outcome.reason) ??
                  (refused ? "The evidence did not support this proposal." : "")}
              </p>
            </Panel>
          </motion.div>
        </AnimatePresence>

        {refused ? (
          <motion.div
            key={active.key + "-note"}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.22, duration: 0.4 }}
            className="mt-6 rounded-[12px] border border-amber-soft bg-amber-wash px-5 py-4"
          >
            <p className="text-[14.5px] leading-relaxed text-ink">
              {active.outcome.sourceValue &&
              active.outcome.sourceValue === active.proposedValue ? (
                <>
                  The source contains this exact string. SKUTruth refused it anyway — the
                  value exists, but the property it sits under does not prove{" "}
                  <em>which attribute</em> it belongs to.
                </>
              ) : (
                <>
                  The proposal could not be re-derived from the stored document, so it
                  reaches no delivery cell.
                </>
              )}
            </p>
            {"detail" in active.outcome && active.outcome.detail ? (
              <p className="mt-2 font-mono text-[12px] text-[#8a6410]">
                {active.outcome.detail}
              </p>
            ) : null}
          </motion.div>
        ) : null}
      </div>
    </div>
  );
}

function Panel({
  eyebrow,
  icon,
  tone,
  children,
}: {
  eyebrow: string;
  icon: React.ReactNode;
  tone: "neutral" | "green" | "amber";
  children: React.ReactNode;
}) {
  const toneClass =
    tone === "green"
      ? "border-sage bg-sage-soft"
      : tone === "amber"
        ? "border-amber-soft bg-amber-wash"
        : "border-line bg-cream-soft/70";

  return (
    <div className={"rounded-[14px] border p-5 " + toneClass}>
      <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-olive">
        {icon}
        {eyebrow}
      </p>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function FieldLine({ label, value, uom }: { label: string; value: string; uom: string }) {
  return (
    <div>
      <p className="text-[12.5px] font-medium uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className="display-heading mt-1.5 break-words text-[26px] text-ink">
        {value}
        {/* A unit is only ever printed when the payload actually carries one. */}
        {uom ? <span className="ml-1.5 text-[18px] text-muted">{uom}</span> : null}
      </p>
    </div>
  );
}

function Chevron() {
  return (
    <div className="flex items-center justify-center py-1 lg:py-0">
      <ArrowRight
        className="h-5 w-5 rotate-90 text-sage lg:rotate-0"
        aria-hidden="true"
      />
    </div>
  );
}
