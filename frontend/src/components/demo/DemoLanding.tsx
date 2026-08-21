"use client";

import { Database, History, ShieldCheck } from "lucide-react";

import { getDemoProducts } from "@/lib/api";
import { CASE_ORDER, CASES } from "@/lib/cases";
import type { DemoIndex } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { REPLAY_EXPLANATION } from "@/lib/vocab";

import { ApiUnavailable, Skeleton } from "@/components/ApiState";
import { CTASection } from "@/components/CTASection";
import { DemoCaseCard } from "@/components/DemoCaseCard";
import { Rise, Stagger, StaggerItem } from "@/components/motion";
import { Breadcrumb, Container, Eyebrow, SectionHeading } from "@/components/primitives";

export function DemoLanding() {
  const { data, error, loading, reload } = useApi<DemoIndex>(getDemoProducts);
  const cardFor = (caseId: string) =>
    data?.products.find((product) => product.case_id === caseId);

  return (
    <>
      <section className="paper-grain relative overflow-hidden pb-14 pt-10 sm:pb-18 sm:pt-14">
        <Container>
          <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: "Demo" }]} />
          <Rise className="max-w-[780px]">
            <Eyebrow>DEMO_REPLAY · three real cases</Eyebrow>
            <h1 className="display-heading mt-6 text-[40px] text-ink sm:text-[52px]">
              See what the pipeline proves—
              <span className="text-green">and where it stops.</span>
            </h1>
            <p className="mt-5 max-w-[690px] text-[17px] leading-relaxed text-muted">
              {REPLAY_EXPLANATION}
            </p>
          </Rise>

          <Rise delay={0.08} className="mt-9 grid gap-4 lg:grid-cols-2">
            <article className="card-surface flex gap-4 p-5 sm:p-6">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sage-soft text-forest">
                <Database className="h-5 w-5" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Re-derived in this demo</h2>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
                  Deterministic stages, recorded provider responses, and Kichler&rsquo;s stored,
                  hashed manufacturer artifact are replayed and checked again now.
                </p>
              </div>
            </article>
            <article className="rounded-[16px] border border-dashed border-amber bg-amber-wash p-5 sm:p-6">
              <div className="flex gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-card text-[#8a6410]">
                  <History className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-[15px] font-semibold text-ink">Recorded observation</h2>
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
                    SATCO&rsquo;s HTTP 429 and Feit&rsquo;s locator representation gap were observed
                    during live runs. They are disclosed as observations, not reconstructed
                    as fresh evidence.
                  </p>
                </div>
              </div>
            </article>
          </Rise>
        </Container>
      </section>

      <Container className="py-14 sm:py-18">
        <SectionHeading
          index={1}
          title="Three outcomes. One trust policy."
          subtitle="A complete path, a blocked acquisition, and a reference the system refused to normalize into a match."
        />

        {error ? (
          <div className="mt-8 max-w-[620px]">
            <ApiUnavailable error={error} onRetry={reload} />
          </div>
        ) : null}

        {loading && !data && !error ? (
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {CASE_ORDER.map((slug) => (
              <Skeleton key={slug} className="h-[470px]" />
            ))}
          </div>
        ) : data ? (
          <Stagger step={0.09} className="mt-8 grid gap-5 md:grid-cols-3">
            {CASE_ORDER.map((slug) => (
              <StaggerItem key={slug} className="h-full">
                <DemoCaseCard slug={slug} card={cardFor(CASES[slug].caseId)} />
              </StaggerItem>
            ))}
          </Stagger>
        ) : null}

        {data ? (
          <Rise className="mt-8 rounded-[16px] border border-line bg-card p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-green" aria-hidden="true" />
                <div>
                  <p className="text-[14px] font-semibold text-ink">API-backed, no local fallback</p>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-muted">
                    The API returned {data.products.length} cases in {data.mode} mode. If it
                    becomes unavailable, this page shows a retry state instead of invented results.
                  </p>
                </div>
              </div>
              <dl className="flex shrink-0 flex-wrap gap-5 text-center">
                <Metric value={data.metrics.kichler_proposals} label="proposals" />
                <Metric value={data.metrics.kichler_verified} label="verified" />
                <Metric value={data.metrics.kichler_withheld} label="withheld" />
              </dl>
            </div>
          </Rise>
        ) : null}
      </Container>

      <CTASection
        title="Start with the completed chain."
        body="Kichler shows the entire path from organizer row to evidence-bound verification—and the final delivery refusal."
        primary={{ href: "/demo/kichler", label: "Open Kichler" }}
        secondary={{ href: "/proof", label: "Read the proof model" }}
      />
    </>
  );
}

function Metric({ value, label }: { value: number | undefined; label: string }) {
  return (
    <div>
      <dd className="display-heading text-[26px] text-forest">{value ?? "—"}</dd>
      <dt className="mt-0.5 text-[11.5px] uppercase tracking-[0.08em] text-muted">{label}</dt>
    </div>
  );
}
