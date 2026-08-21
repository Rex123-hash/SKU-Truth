import type { Metadata } from "next";
import { Braces, Database, Eye, ShieldCheck } from "lucide-react";

import { CTASection } from "@/components/CTASection";
import { MetricCard } from "@/components/MetricCard";
import { Rise, Stagger, StaggerItem } from "@/components/motion";
import { ButtonLink, Container, Eyebrow, SectionHeading } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Proof",
  description: "The evidence bases, trust boundaries, API contract, and real metrics behind the SKUTruth demo.",
};

const EVIDENCE = [
  {
    title: "Deterministic computation",
    body: "Normalization, classification, verification rules, and delivery mapping are recomputed from committed code and data.",
    Icon: Braces,
  },
  {
    title: "Replayed recording",
    body: "Recorded provider interactions make discovery and model output repeatable without claiming they happened live today.",
    Icon: Database,
  },
  {
    title: "Stored artifact",
    body: "Kichler verification is re-derived from a hashed manufacturer document. The document, not the model, settles the value.",
    Icon: ShieldCheck,
  },
  {
    title: "Recorded observation",
    body: "Live-run conditions that cannot be replayed—such as SATCO's HTTP 429—remain explicitly labelled observations.",
    Icon: Eye,
  },
];

const BOUNDARIES = [
  ["Search says EXACT", "The document covers this SKU"],
  ["The model proposed it", "It is a manufacturer fact"],
  ["Verified manufacturer fact", "Authorised delivery value"],
];

const ENDPOINTS = [
  "GET /api/health",
  "GET /api/demo/products",
  "GET /api/demo/products/{case_id_or_mpn}",
  "POST /api/analyze",
  "GET /api/schema",
];

export default function ProofPage() {
  return (
    <>
      <section className="paper-grain relative overflow-hidden py-14 sm:py-20">
        <Container>
          <Rise className="max-w-[790px]">
            <Eyebrow>Inspect the boundary, not a confidence score</Eyebrow>
            <h1 className="display-heading mt-6 text-[40px] text-ink sm:text-[52px]">
              Every claim shows
              <span className="text-green"> what made it trustworthy.</span>
            </h1>
            <p className="mt-5 max-w-[700px] text-[17px] leading-relaxed text-muted">
              SKUTruth keeps proposals, evidence, verified facts, and delivery values as
              separate types. The interface mirrors those boundaries instead of flattening
              them into one confidence score.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="/demo/kichler">Inspect the full chain</ButtonLink>
              <ButtonLink href="/demo" variant="secondary">Compare all cases</ButtonLink>
            </div>
          </Rise>

          <Stagger step={0.06} className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["1,000", "organizer rows"],
              ["252", "delivery columns"],
              ["50", "attribute triplets"],
              ["3", "manufacturer cases"],
            ].map(([value, label]) => (
              <StaggerItem key={label}>
                <MetricCard eyebrow="Repository fact" value={value} label={label} />
              </StaggerItem>
            ))}
          </Stagger>
        </Container>
      </section>

      <Container id="evidence" className="scroll-mt-24 py-14 sm:py-18">
        <SectionHeading
          index={1}
          title="Four evidence bases"
          subtitle="The badge on each stage tells you whether the answer was recomputed, replayed, re-derived from a document, or only observed during a live run."
        />
        <Stagger step={0.07} className="mt-8 grid gap-4 sm:grid-cols-2">
          {EVIDENCE.map(({ title, body, Icon }) => (
            <StaggerItem key={title} className="h-full">
              <article className="card-surface flex h-full gap-4 p-6">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sage-soft text-forest">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{body}</p>
                </div>
              </article>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>

      <section id="boundaries" className="dark-section scroll-mt-24 py-16 sm:py-22">
        <Container>
          <SectionHeading
            index={2}
            title={<span className="text-cream">The three lines SKUTruth will not cross</span>}
            subtitle={<span className="text-[var(--text-on-dark-secondary)]">Each side can be true without proving the other.</span>}
          />
          <Stagger step={0.08} className="mt-8 grid gap-4 lg:grid-cols-3">
            {BOUNDARIES.map(([left, right]) => (
              <StaggerItem key={left} className="h-full">
                <div className="dark-card h-full rounded-[16px] p-6">
                  <p className="text-[16px] font-medium text-cream">{left}</p>
                  <p className="my-3 text-[22px] text-amber" aria-label="is not the same as">≠</p>
                  <p className="text-[16px] font-medium text-cream">{right}</p>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
        </Container>
      </section>

      <Container id="api" className="scroll-mt-24 py-14 sm:py-18">
        <SectionHeading
          index={3}
          title="A small, typed API surface"
          subtitle="The frontend reads one configurable base URL and never substitutes a fabricated local result."
        />
        <div className="card-surface mt-8 overflow-hidden">
          <ul className="divide-y divide-line-soft">
            {ENDPOINTS.map((endpoint) => (
              <li key={endpoint} className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                <code className="break-all font-mono text-[13px] text-green">{endpoint}</code>
                <span className="text-[12.5px] text-muted">typed JSON · explicit failure</span>
              </li>
            ))}
          </ul>
        </div>
      </Container>

      <CTASection
        title="The refusal is part of the proof."
        body="Compare the completed Kichler case with the stages that deliberately never ran for SATCO and Feit."
        primary={{ href: "/demo", label: "Open all cases" }}
        secondary={{ href: "/demo/kichler", label: "Inspect Kichler" }}
      />
    </>
  );
}
