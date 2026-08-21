"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import type { AttributesView, VerifiedAttribute, WithheldAttribute } from "@/lib/types";
import { reasonSentence } from "@/lib/vocab";
import { ReasonCode } from "./Badges";
import { EvidenceDrawer, type DrawerAttribute } from "./EvidenceDrawer";

/**
 * Verified facts and withheld proposals, as two separate lists.
 *
 * They are never merged into one table with a status column. A verified manufacturer
 * fact and a refused model proposal are different kinds of thing, and putting them in
 * the same list invites exactly the skim-reading this product is built to prevent.
 *
 * On a narrow screen each row becomes a card; the markup is the same either way.
 */
export function AttributeTable({ attributes }: { attributes: AttributesView }) {
  const [open, setOpen] = useState<DrawerAttribute | null>(null);

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <header className="flex items-baseline gap-2.5">
            <h3 className="display-heading text-[21px] text-ink">Verified facts</h3>
            <span className="rounded-full border border-sage bg-sage-soft px-2.5 py-0.5 text-[12px] font-medium text-forest">
              {attributes.verified.length}
            </span>
          </header>
          <p className="mt-1.5 text-[13.5px] text-muted">
            Each one re-derived from the stored manufacturer document.
          </p>

          <ul className="mt-4 space-y-2.5">
            {attributes.verified.map((attribute) => (
              <VerifiedRow
                key={attribute.source_key}
                attribute={attribute}
                onOpen={() => setOpen({ kind: "verified", attribute })}
              />
            ))}
          </ul>
        </section>

        <section>
          <header className="flex items-baseline gap-2.5">
            <h3 className="display-heading text-[21px] text-ink">Withheld proposals</h3>
            <span className="rounded-full border border-amber-soft bg-amber-wash px-2.5 py-0.5 text-[12px] font-medium text-[#8a6410]">
              {attributes.withheld.length}
            </span>
          </header>
          <p className="mt-1.5 text-[13.5px] text-muted">
            Bound to a location, and still not established as facts.
          </p>

          <ul className="mt-4 space-y-2.5">
            {attributes.withheld.map((attribute) => (
              <WithheldRow
                key={attribute.source_key}
                attribute={attribute}
                onOpen={() => setOpen({ kind: "withheld", attribute })}
              />
            ))}
          </ul>
        </section>
      </div>

      <EvidenceDrawer entry={open} onClose={() => setOpen(null)} />
    </>
  );
}

export function VerifiedRow({
  attribute,
  onOpen,
}: {
  attribute: VerifiedAttribute;
  onOpen: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="group flex w-full items-center justify-between gap-4 rounded-[12px] border border-line bg-card px-4 py-3.5 text-left transition-colors hover:border-sage hover:bg-cream-soft/60"
      >
        <span className="min-w-0">
          <span className="block text-[13px] text-muted">{attribute.label}</span>
          <span className="mt-0.5 block truncate text-[16px] font-medium text-ink">
            {attribute.value}
            {/* The unit prints only when the verified payload carries one. The Kichler
                wattage verifies as 100 with no normalised unit; the source's own "W"
                belongs to the evidence, not to the fact. */}
            {attribute.uom ? (
              <span className="ml-1.5 text-[13px] text-muted">{attribute.uom}</span>
            ) : null}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="hidden text-[12px] text-muted sm:inline">
            {attribute.source_label}
          </span>
          <ChevronRight
            className="h-4 w-4 text-sage transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
      </button>
    </li>
  );
}

export function WithheldRow({
  attribute,
  onOpen,
}: {
  attribute: WithheldAttribute;
  onOpen: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="group flex w-full items-start justify-between gap-4 rounded-[12px] border border-dashed border-amber-soft bg-amber-wash/50 px-4 py-3.5 text-left transition-colors hover:bg-amber-wash"
      >
        <span className="min-w-0">
          <span className="block text-[13px] text-muted">{attribute.label}</span>
          <span className="mt-0.5 block truncate text-[16px] font-medium text-ink line-through decoration-[#8a6410]/40">
            {attribute.proposed_value}
          </span>
          <span className="mt-2 block">
            <ReasonCode code={attribute.reason} />
          </span>
          <span className="mt-1.5 block text-[12.5px] leading-relaxed text-muted">
            {reasonSentence(attribute.reason) ?? attribute.detail}
          </span>
        </span>
        <ChevronRight
          className="mt-1 h-4 w-4 shrink-0 text-amber transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </button>
    </li>
  );
}
