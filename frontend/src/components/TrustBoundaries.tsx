"use client";

import { Container } from "./primitives";
import { Rise, Stagger, StaggerItem } from "./motion";

/**
 * The three distinctions the rest of the interface depends on. They are stated once,
 * plainly, because every other screen assumes the reader already holds them — and
 * because blurring any one of them is how a system like this starts lying.
 */
const BOUNDARIES = [
  {
    left: "Search says EXACT",
    right: "The document covers this SKU",
    body: "A search result naming the reference is a lead. Only the fetched document can prove it describes this exact product.",
  },
  {
    left: "The model proposed it",
    right: "It is a fact",
    body: "A proposal is a plausible reading of a page. It becomes a fact only when the source is re-read mechanically and agrees.",
  },
  {
    left: "Verified manufacturer fact",
    right: "Authorised delivery value",
    body: "A fact can be true and still not be deliverable. The organizer's own vocabulary decides the final format, and it has not spoken here.",
  },
];

export function TrustBoundaries() {
  return (
    <section className="dark-section py-16 sm:py-22">
      <Container>
        <Rise className="max-w-[600px]">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sage">
            Trust boundaries
          </p>
          <h2 className="display-heading mt-3 text-[30px] text-cream sm:text-[36px]">
            Three things this system
            <br />
            refuses to confuse.
          </h2>
        </Rise>

        <Stagger step={0.09} className="mt-11 grid gap-4 lg:grid-cols-3">
          {BOUNDARIES.map((boundary) => (
            <StaggerItem key={boundary.left} className="h-full">
              <div className="dark-card flex h-full flex-col rounded-[16px] p-6">
                <p className="text-[16px] font-medium text-cream">{boundary.left}</p>
                <p
                  aria-label="is not the same as"
                  className="my-2.5 text-[20px] font-light text-amber"
                >
                  ≠
                </p>
                <p className="text-[16px] font-medium text-cream">{boundary.right}</p>
                <p className="mt-5 text-[14.5px] leading-relaxed text-[var(--text-on-dark-secondary)]">{boundary.body}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>
    </section>
  );
}
