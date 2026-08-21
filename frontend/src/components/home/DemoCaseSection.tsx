"use client";

import { getDemoProducts } from "@/lib/api";
import { CASE_ORDER, CASES, slugForCaseId } from "@/lib/cases";
import { useApi } from "@/lib/useApi";
import type { DemoIndex } from "@/lib/types";

import { ApiUnavailable } from "@/components/ApiState";
import { DemoCaseCard } from "@/components/DemoCaseCard";
import { ButtonLink, Container } from "@/components/primitives";
import { Rise, Stagger, StaggerItem } from "@/components/motion";

/**
 * The three real cases. The cards render from static copy so the section is legible even
 * before the API answers; the live counts are layered on once it does, and a failed call
 * is stated rather than papered over.
 */
export function DemoCaseSection() {
  const { data, error, reload } = useApi<DemoIndex>(getDemoProducts);

  const cardFor = (caseId: string) =>
    data?.products.find((product) => product.case_id === caseId);

  return (
    <section id="cases" className="py-14 sm:py-20">
      <Container>
        <Rise className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-[560px]">
            <h2 className="display-heading text-[30px] text-ink sm:text-[36px]">
              See SKUTruth <span className="text-green">in action</span>
            </h2>
            <p className="mt-3.5 text-[16px] leading-relaxed text-muted">
              Three real organizer rows, run end to end. One completed. Two stopped — and
              stopping correctly is the harder result.
            </p>
          </div>
          <ButtonLink href="/demo" variant="secondary">
            Open the demo
          </ButtonLink>
        </Rise>

        {error ? (
          <div className="mt-9 max-w-[560px]">
            <ApiUnavailable error={error} onRetry={reload} compact />
          </div>
        ) : null}

        {data ? (
          <Stagger
            step={0.09}
            className="mt-9 flex snap-x snap-mandatory gap-5 overflow-x-auto pb-4 lg:grid lg:grid-cols-3 lg:overflow-visible lg:pb-0"
          >
            {CASE_ORDER.map((slug) => (
              <StaggerItem key={slug} className="w-[84vw] shrink-0 snap-center lg:w-auto lg:shrink">
                <DemoCaseCard slug={slug} card={cardFor(CASES[slug].caseId)} />
              </StaggerItem>
            ))}
          </Stagger>
        ) : null}

        {data ? (
          <p className="mt-5 text-[13px] text-muted">
            Live from the demo API in{" "}
            <span className="font-mono text-green">{data.mode}</span> mode
            {data.products.length !== CASE_ORDER.length ? (
              <>
                {" "}
                — {data.products.length} case{data.products.length === 1 ? "" : "s"} returned
              </>
            ) : null}
            .
          </p>
        ) : null}

        {/* If the server ever returns a case this build has no route for, say so rather
            than dropping it silently from the page. */}
        {data
          ? data.products
              .filter((product) => slugForCaseId(product.case_id) === null)
              .map((product) => (
                <p key={product.case_id} className="mt-2 text-[13px] text-[#8a6410]">
                  The API returned an additional case this build has no page for:{" "}
                  <span className="font-mono">{product.case_id}</span>.
                </p>
              ))
          : null}
      </Container>
    </section>
  );
}
