"use client";

import Image from "next/image";

import { Container } from "@/components/primitives";
import { Rise, Stagger, StaggerItem } from "@/components/motion";

/**
 * The five principles.
 *
 * The supplied artwork for these came as finished cards with their headline and body
 * copy baked into the pixels. Only the illustration band is used; the words are real
 * HTML so they stay selectable, responsive, translatable and reachable by assistive
 * technology. Each crop keeps the card's own cream ground, so the well behind it is
 * painted the same colour and no seam shows.
 */
const FEATURES = [
  {
    title: "Verified by design",
    body: "Evidence before enrichment. A value with no source never becomes a fact.",
    art: "/art/feature-verified.png",
    ground: "#FCFAF2",
    alt: "A shield and padlock guarding a location marker",
  },
  {
    title: "Source first",
    body: "Every accepted fact points back to the exact place it came from.",
    art: "/art/feature-source-first.png",
    ground: "#FCF8F2",
    alt: "A magnifying-glass character checking a document against a shield",
  },
  {
    title: "AI with guardrails",
    body: "Models propose. Deterministic rules verify. The two never swap roles.",
    art: "/art/feature-guardrails.png",
    ground: "#FCF9F1",
    alt: "An AI chip on a circuit board beside a verification shield",
  },
  {
    title: "Built for integration",
    body: "Typed contracts at every boundary, and a delivery schema that is explicit.",
    art: "/art/feature-integration.png",
    ground: "#F8F6ED",
    alt: "Two puzzle pieces joining code and storage",
  },
  {
    title: "Trust that scales",
    body: "Failures stay visible instead of quietly becoming invented data.",
    art: "/art/crate-sku.png",
    ground: "#FFFDF8",
    alt: "A crate of parts carrying a printed SKU tag",
  },
];

export function FeatureCards() {
  return (
    <section className="py-14 sm:py-20">
      <Container>
        <Rise className="mx-auto max-w-[560px] text-center">
          <h2 className="display-heading text-[30px] text-ink sm:text-[36px]">
            Built to <span className="text-green">refuse</span>, not to guess.
          </h2>
          <p className="mt-3.5 text-[16px] leading-relaxed text-muted">
            Five properties that decide whether product data can be trusted into a PIM.
          </p>
        </Rise>

        <Stagger step={0.07} className="mt-11 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <StaggerItem key={feature.title} className="h-full">
              <article className="card-surface flex h-full flex-col overflow-hidden">
                <div
                  className="flex h-[168px] items-center justify-center"
                  style={{ backgroundColor: feature.ground }}
                >
                  <Image
                    src={feature.art}
                    alt={feature.alt}
                    width={760}
                    height={500}
                    sizes="(max-width: 640px) 90vw, 380px"
                    loading="lazy"
                    className="h-full w-full object-contain"
                  />
                </div>
                <div className="flex flex-1 flex-col p-5">
                  <h3 className="display-heading text-[20px] text-ink">{feature.title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-muted">{feature.body}</p>
                </div>
              </article>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>
    </section>
  );
}
