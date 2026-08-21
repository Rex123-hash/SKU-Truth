"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Check, Minus } from "lucide-react";

import { CASES, type CaseSlug } from "@/lib/cases";
import type { ProductCard } from "@/lib/types";
import { StageBadge, TrustBasisBadge } from "./Badges";

/**
 * One demo case, as a card. The three cases are not three grades of the same success —
 * they are a completed path, a blocked fetch and a refused match — so the card shows the
 * terminal state plainly rather than dressing two of them up as partial wins.
 */

const BADGE_STATUS = {
  kichler: "SUCCESS",
  satco: "BLOCKED",
  feit: "REVIEW",
} as const;

/** Kichler's outcome was re-derived from stored evidence; the other two were watched. */
const BASIS = {
  kichler: "STORED_ARTIFACT",
  satco: "RECORDED_OBSERVATION",
  feit: "RECORDED_OBSERVATION",
} as const;

const FACTS: Record<CaseSlug, string[]> = {
  kichler: ["Exact SKU identified", "10 AI proposals, all source-bound", "7 verified · 3 withheld"],
  satco: ["Exact source found", "HTTP 429 at acquisition", "No fake enrichment"],
  feit: [
    "Official sources found",
    "Site spells the reference with hyphens",
    "Exact reference not established",
  ],
};

export function DemoCaseCard({ slug, card }: { slug: CaseSlug; card?: ProductCard }) {
  const meta = CASES[slug];
  const complete = slug === "kichler";

  return (
    <Link
      href={"/demo/" + slug}
      className="group card-surface flex h-full flex-col p-6 transition-all duration-200 hover:-translate-y-[3px] hover:shadow-[var(--shadow-lift)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="display-heading text-[24px] uppercase tracking-tight text-ink">
            {meta.manufacturer}
          </p>
          <p className="mt-1 font-mono text-[13px] text-muted">{meta.mpn}</p>
        </div>
        <StageBadge status={BADGE_STATUS[slug]} label={meta.badge} />
      </div>

      <div className="mt-5 flex h-[128px] items-center justify-center">
        <Image
          src={meta.art}
          alt={meta.artAlt}
          width={460}
          height={460}
          sizes="200px"
          className="h-full w-auto object-contain"
        />
      </div>

      <ul className="mt-5 space-y-2.5">
        {FACTS[slug].map((fact, index) => (
          <li key={fact} className="flex items-start gap-2.5 text-[14px] leading-snug text-ink">
            {complete || index === 0 ? (
              <Check className="mt-[3px] h-4 w-4 shrink-0 text-green" aria-hidden="true" />
            ) : (
              <Minus className="mt-[3px] h-4 w-4 shrink-0 text-amber" aria-hidden="true" />
            )}
            {fact}
          </li>
        ))}
      </ul>

      {card ? (
        <p className="mt-4 text-[13px] text-muted">
          <span className="font-medium text-forest">{card.verified_count}</span> verified ·{" "}
          <span className="font-medium text-[#8a6410]">{card.withheld_count}</span> withheld
        </p>
      ) : null}

      <div className="mt-auto flex items-center justify-between gap-3 pt-6">
        <TrustBasisBadge basis={BASIS[slug]} interactive={false} />
        <span className="inline-flex items-center gap-1.5 text-[14px] font-medium text-forest">
          Explore
          <ArrowRight
            className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
      </div>
    </Link>
  );
}
