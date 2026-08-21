"use client";

import { motion } from "framer-motion";

import type { TimelineEntry } from "@/lib/types";
import { STAGE_BLURB, STAGE_LABEL, STATUS_LABEL } from "@/lib/vocab";
import { ReasonCode, StageBadge, Tooltip, TrustBasisBadge } from "./Badges";

/**
 * The eight stages, in order, with the state each actually reached.
 *
 * `NOT_RUN` stages are drawn as clearly unlit rather than hidden. A judge should be able
 * to see exactly where a case stopped and that nothing after that point was attempted —
 * for SATCO and Feit, the empty half of this strip is the result.
 */

const DOT_STYLE = {
  SUCCESS: "bg-green border-green",
  REVIEW: "bg-amber border-amber",
  WITHHELD: "bg-amber border-amber",
  BLOCKED: "bg-amber border-amber",
  NOT_RUN: "bg-cream border-line",
} as const;

export function JourneyTimeline({ timeline }: { timeline: TimelineEntry[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {timeline.map((entry, index) => {
        const dim = entry.status === "NOT_RUN";
        return (
          <motion.li
            key={entry.stage}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.45, delay: index * 0.085, ease: [0.22, 0.61, 0.36, 1] }}
            className={
              "relative rounded-[14px] border p-4 " +
              (dim ? "border-dashed border-line bg-cream-soft/50" : "border-line bg-card")
            }
          >
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={"h-2.5 w-2.5 rounded-full border " + DOT_STYLE[entry.status]}
              />
              <span className="font-mono text-[11px] text-muted">
                {String(index + 1).padStart(2, "0")}
              </span>
            </div>

            <h3
              className={
                "mt-2.5 text-[15px] font-semibold " + (dim ? "text-muted" : "text-ink")
              }
            >
              {STAGE_LABEL[entry.stage]}
            </h3>

            <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">
              {entry.detail || STAGE_BLURB[entry.stage]}
            </p>

            <div className="mt-3.5 flex flex-wrap items-center gap-1.5">
              <StageBadge status={entry.status} />
            </div>

            {entry.reason ? (
              <div className="mt-2">
                <ReasonCode code={entry.reason} />
              </div>
            ) : null}

            <div className="mt-2.5">
              <TrustBasisBadge basis={entry.evidence} />
            </div>

            <span className="sr-only">
              {STAGE_LABEL[entry.stage]}: {STATUS_LABEL[entry.status]}
            </span>
          </motion.li>
        );
      })}
    </ol>
  );
}

/**
 * The counts under the journey. `0 mapped` is not a failure and must not read like one:
 * the manufacturer evidence was verified, and the organizer's own lighting vocabulary
 * simply is not in the supplied pack, so nothing is authorised for delivery yet.
 */
export function JourneyCounts({
  proposals,
  sourceBound,
  verified,
  withheld,
  mapped,
  mappingStatus,
  unauthorizedReason,
}: {
  proposals: number;
  sourceBound: number;
  verified: number;
  withheld: number;
  mapped: number;
  mappingStatus: string;
  unauthorizedReason: string;
}) {
  const items = [
    { value: proposals, label: "AI proposals", tone: "ink" as const },
    { value: sourceBound, label: "Source-bound", tone: "ink" as const },
    { value: verified, label: "Verified", tone: "green" as const },
    { value: withheld, label: "Withheld", tone: "amber" as const },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="rounded-[14px] border border-line bg-card p-5">
          <p
            className={
              "display-heading text-[34px] " +
              (item.tone === "green"
                ? "text-forest"
                : item.tone === "amber"
                  ? "text-[#8a6410]"
                  : "text-ink")
            }
          >
            {item.value}
          </p>
          <p className="mt-1 text-[13px] text-muted">{item.label}</p>
        </div>
      ))}

      <div className="rounded-[14px] border border-dashed border-line bg-cream-soft/60 p-5">
        <p className="display-heading text-[34px] text-muted">{mapped}</p>
        <p className="mt-1 text-[13px] text-muted">Delivery-mapped</p>
        {/* Zero here is a boundary, not a breakage, so the explanation sits one hover
            away rather than shouting a paragraph of caveat next to the number. */}
        <div className="mt-2">
          <Tooltip
            label={
              unauthorizedReason ||
              "Manufacturer evidence was verified, but no organizer-authorised lighting vocabulary exists to map it into."
            }
          >
            <span className="inline-flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-[0.08em] text-[#8a6410] underline decoration-dotted underline-offset-4">
              {mappingStatus}
            </span>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}
