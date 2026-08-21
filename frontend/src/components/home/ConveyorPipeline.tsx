"use client";

import Image from "next/image";

import { Container } from "@/components/primitives";
import { StageConnector } from "@/components/Decor";
import { Rise, Stagger, StaggerItem, motion } from "@/components/motion";

/**
 * The belt arrives from the left once, then stays put.
 *
 * The reveal is a transform and an opacity fade, not a `clip-path` wipe. A clipped
 * wrapper kept Chrome from ever fetching the lazily-loaded image inside it, which left
 * the belt permanently absent — an entry effect must not be able to hide content it is
 * only supposed to introduce.
 */
function BeltReveal() {
  return (
    <motion.div
      className="mt-4"
      initial={{ opacity: 0, x: -28 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.85, ease: [0.22, 0.61, 0.36, 1] }}
    >
      <Image
        src="/art/conveyor-belt.png"
        alt=""
        aria-hidden="true"
        width={1800}
        height={178}
        sizes="(max-width: 768px) 100vw, 1180px"
        className="h-auto w-full"
      />
    </motion.div>
  );
}

/**
 * The signature conveyor. The belt is the supplied illustration; everything riding on it
 * is real DOM, so the copy stays selectable, translatable and reachable by a screen
 * reader. On a narrow screen the row becomes a snap-scrolling track rather than shrinking
 * four cards into illegibility.
 */
const STAGES = [
  {
    n: "01",
    title: "Messy data",
    body: "A part number, forty characters of abbreviation, and three brand columns that are mostly placeholders.",
    art: "/art/stage-messy-data.png",
    alt: "A pile of spreadsheets and documents with warning markers",
  },
  {
    n: "02",
    title: "Discovery",
    body: "Search reviewed manufacturer domains for a page that names this exact reference.",
    art: "/art/mascot-search.png",
    alt: "A magnifying-glass character searching",
  },
  {
    n: "03",
    title: "Verification",
    body: "Re-derive every proposal from the stored document. Anything unproven is withheld.",
    art: "/art/stage-verification.png",
    alt: "A checklist beside a shield",
  },
  {
    n: "04",
    title: "Delivery",
    body: "Verified facts reach the delivery contract. The rest reaches no cell at all.",
    art: "/art/mascot-delivery.png",
    alt: "A parcel character carrying the finished record",
  },
];

export function ConveyorPipeline() {
  return (
    <section id="how-it-works" className="relative py-14 sm:py-20">
      <Container>
        <Rise className="mx-auto max-w-[560px] text-center">
          <h2 className="display-heading text-[30px] text-ink sm:text-[36px]">
            One row in. <span className="text-green">Verified facts out.</span>
          </h2>
          <p className="mt-3.5 text-[16px] leading-relaxed text-muted">
            Every stage can stop the line. That is the point.
          </p>
        </Rise>

        <Stagger
          step={0.09}
          className="mt-11 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-4 sm:grid sm:grid-cols-2 sm:overflow-visible sm:pb-0 lg:grid-cols-4"
        >
          {STAGES.map((stage, index) => (
            <StaggerItem
              key={stage.n}
              className="w-[78vw] shrink-0 snap-center sm:w-auto sm:shrink"
            >
              <article className="card-surface relative flex h-full flex-col p-5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[12px] font-medium tracking-wider text-olive">
                    {stage.n}
                  </span>
                  {index < STAGES.length - 1 ? (
                    <StageConnector className="hidden h-2.5 w-10 lg:block" />
                  ) : null}
                </div>

                <div className="mt-2 flex h-[112px] items-center justify-center">
                  <Image
                    src={stage.art}
                    alt={stage.alt}
                    width={620}
                    height={620}
                    sizes="180px"
                    className="h-full w-auto object-contain"
                  />
                </div>

                <h3 className="display-heading mt-4 text-[19px] text-ink">{stage.title}</h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{stage.body}</p>
              </article>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>

      {/* The belt runs under the cards so the row reads as riding on it, as in the
          approved layouts. It reveals left-to-right on entry and never loops. */}
      <Container>
        <BeltReveal />
      </Container>
    </section>
  );
}
