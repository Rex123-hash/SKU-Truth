"use client";

import { OctagonPause, Route } from "lucide-react";

import type { ProductDetail } from "@/lib/types";
import { reasonSentence } from "@/lib/vocab";
import { ReasonCode, TrustBasisBadge } from "@/components/Badges";

/**
 * Why a case stopped.
 *
 * Blocked is a result, not an error screen. It gets amber and a calm explanation rather
 * than red alarm styling, because refusing to continue on insufficient evidence is the
 * behaviour this project is arguing for — dressing it as a fault would undercut the
 * whole claim.
 */
const COPY: Record<string, { title: string; lede: string; Icon: typeof Route }> = {
  SOURCE_RATE_LIMITED: {
    title: "The fetch was refused",
    lede: "Discovery had already established a trusted, exact source. The manufacturer's site answered the acquisition request with HTTP 429, so no document was stored — and every stage after acquisition needs that document.",
    Icon: OctagonPause,
  },
  NO_EXACT_SOURCE: {
    title: "No exact reference was established",
    lede: "Official manufacturer pages were found under approved authority. None of them spelled the reference the way the organizer row does, and the relevance policy does not treat a slash and a hyphen as the same character.",
    Icon: Route,
  },
};

export function BlockerPanel({ detail }: { detail: ProductDetail }) {
  const blocker = detail.source.blocker;
  if (!blocker) return null;

  const copy = COPY[blocker] ?? {
    title: "This case stopped here",
    lede: detail.source.blocker_detail,
    Icon: OctagonPause,
  };
  const { Icon } = copy;

  // The stage that actually carries the blocker, so its evidence basis is the one shown.
  const stage = detail.timeline.find(
    (entry) => entry.status === "BLOCKED" || entry.status === "REVIEW",
  );

  return (
    <section className="rounded-[18px] border border-amber-soft bg-amber-wash p-7 sm:p-9">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-[640px]">
          <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a6410]">
            <Icon className="h-4 w-4" aria-hidden="true" />
            Stopped on purpose
          </p>
          <h2 className="display-heading mt-3 text-[26px] text-ink sm:text-[30px]">
            {copy.title}
          </h2>
          <p className="mt-3.5 text-[15.5px] leading-relaxed text-ink/80">{copy.lede}</p>

          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <ReasonCode code={blocker} />
            {stage ? <TrustBasisBadge basis={stage.evidence} /> : null}
          </div>

          {reasonSentence(blocker) ? (
            <p className="mt-4 text-[13.5px] text-muted">{reasonSentence(blocker)}</p>
          ) : null}
        </div>

        <ul className="w-full max-w-[330px] shrink-0 space-y-2.5 rounded-[14px] border border-amber-soft/70 bg-card/70 p-5">
          <li className="text-[12px] font-semibold uppercase tracking-[0.1em] text-[#8a6410]">
            What did not happen
          </li>
          {detail.timeline
            .filter((entry) => entry.status === "NOT_RUN")
            .map((entry) => (
              <li key={entry.stage} className="text-[13.5px] leading-relaxed text-muted">
                <span className="font-medium text-ink">{entry.stage}</span> — {entry.detail}
              </li>
            ))}
          <li className="pt-1 text-[13px] leading-relaxed text-ink">
            No value was estimated, inferred or carried over from a similar product.
          </li>
        </ul>
      </div>
    </section>
  );
}
