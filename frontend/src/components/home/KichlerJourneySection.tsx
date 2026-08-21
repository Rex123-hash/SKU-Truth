"use client";

import Image from "next/image";
import { useCallback } from "react";

import { getDemoProduct } from "@/lib/api";
import { CASES } from "@/lib/cases";
import { useApi } from "@/lib/useApi";
import type { ProductDetail } from "@/lib/types";

import { ApiUnavailable, Skeleton } from "@/components/ApiState";
import { EvidenceComparison } from "@/components/EvidenceComparison";
import { JourneyCounts, JourneyTimeline } from "@/components/JourneyTimeline";
import { ButtonLink, Container } from "@/components/primitives";
import { Rise } from "@/components/motion";

/**
 * The hero case, on the homepage. One request feeds both halves: the eight-stage journey
 * and the proposal-versus-evidence comparison underneath it, so a judge sees the whole
 * argument without leaving the front page.
 */
export function KichlerJourneySection() {
  const fetchCase = useCallback(() => getDemoProduct(CASES.kichler.caseId), []);
  const { data, error, loading, reload } = useApi<ProductDetail>(fetchCase);

  return (
    <section id="journey" className="bg-cream-soft py-14 sm:py-20">
      <Container>
        <Rise className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-[620px]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-olive">
              Featured journey
            </p>
            <h2 className="display-heading mt-3 text-[30px] text-ink sm:text-[38px]">
              Inside the SKUTruth journey:
              <br />
              <span className="text-green">Kichler 45297BK</span>
            </h2>
            <p className="mt-4 text-[16px] leading-relaxed text-muted">
              A wall light from row 371 of the organizer file. Eight stages, ten model
              proposals, and a document that settles every one of them.
            </p>
          </div>

          <div className="flex items-end gap-6">
            <Image
              src="/art/robot-inspector.png"
              alt=""
              aria-hidden="true"
              width={815}
              height={820}
              sizes="180px"
              className="hidden w-[132px] shrink-0 lg:block"
            />
            <ButtonLink href="/demo/kichler">Open the full case</ButtonLink>
          </div>
        </Rise>

        {error ? (
          <div className="mt-9 max-w-[620px]">
            <ApiUnavailable error={error} onRetry={reload} />
          </div>
        ) : null}

        {loading && !data ? (
          <div className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-[180px]" />
            ))}
          </div>
        ) : null}

        {data ? (
          <>
            <div className="mt-10">
              <JourneyTimeline timeline={data.timeline} />
            </div>

            <div className="mt-6">
              <JourneyCounts
                proposals={data.ai.proposal_count}
                sourceBound={data.ai.source_bound_count}
                verified={data.attributes.verified.length}
                withheld={data.attributes.withheld.length}
                mapped={data.delivery.mapped_count}
                mappingStatus={data.delivery.mapping_status}
                unauthorizedReason={data.delivery.unauthorized_reason}
              />
            </div>

            <div className="mt-14">
              <EvidenceComparison detail={data} />
            </div>
          </>
        ) : null}
      </Container>
    </section>
  );
}
