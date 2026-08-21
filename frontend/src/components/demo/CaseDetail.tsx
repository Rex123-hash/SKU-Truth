"use client";

import Image from "next/image";
import { useCallback } from "react";

import { getDemoProduct } from "@/lib/api";
import { CASES, type CaseSlug } from "@/lib/cases";
import { useApi } from "@/lib/useApi";
import type { ProductDetail } from "@/lib/types";
import { REPLAY_EXPLANATION, reasonSentence } from "@/lib/vocab";

import { ApiUnavailable, Skeleton } from "@/components/ApiState";
import { AttributeTable } from "@/components/AttributeTable";
import { CTASection } from "@/components/CTASection";
import { EvidenceComparison } from "@/components/EvidenceComparison";
import { JourneyCounts, JourneyTimeline } from "@/components/JourneyTimeline";
import { ReasonCode, StageBadge, Tooltip } from "@/components/Badges";
import { Breadcrumb, Container, SectionHeading } from "@/components/primitives";
import { Rise } from "@/components/motion";
import { BlockerPanel } from "./BlockerPanel";

/**
 * One demo case, in full.
 *
 * All three cases render through this same component. SATCO and Feit are not a reduced
 * variant of it — they run the identical structure and simply stop where they really
 * stopped, which is what makes the fail-closed behaviour legible: the sections that
 * never got input are visibly present and visibly empty.
 */
export function CaseDetail({ slug }: { slug: CaseSlug }) {
  const meta = CASES[slug];
  const fetchCase = useCallback(() => getDemoProduct(meta.caseId), [meta.caseId]);
  const { data, error, loading, reload } = useApi<ProductDetail>(fetchCase);

  if (error) {
    return (
      <Container className="py-16">
        <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: "Demo", href: "/demo" }, { label: meta.manufacturer }]} />
        <div className="max-w-[620px]">
          <ApiUnavailable error={error} onRetry={reload} />
        </div>
      </Container>
    );
  }

  if (loading || !data) {
    return (
      <Container className="py-16">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="mt-8 h-14 w-[420px]" />
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-[190px]" />
          ))}
        </div>
      </Container>
    );
  }

  const complete = data.attributes.verified.length > 0;

  return (
    <>
      <Container className="pt-10">
        <Breadcrumb
          trail={[
            { label: "Home", href: "/" },
            { label: "Demo", href: "/demo" },
            { label: meta.manufacturer + " " + meta.mpn },
          ]}
        />

        {/* --- header ------------------------------------------------------ */}
        <Rise>
          <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr] lg:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <StageBadge
                  status={complete ? "SUCCESS" : data.source.blocker === "SOURCE_RATE_LIMITED" ? "BLOCKED" : "REVIEW"}
                  label={meta.badge}
                />
                <ReasonCode code={data.case_id} />
              </div>

              <h1 className="display-heading mt-5 text-[38px] text-ink sm:text-[46px]">
                {meta.manufacturer}{" "}
                <span className="text-green">{meta.mpn}</span>
              </h1>

              <p className="mt-4 max-w-[560px] text-[16.5px] leading-relaxed text-muted">
                {data.headline}
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-2.5">
                <Tooltip label={REPLAY_EXPLANATION}>
                  <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3.5 py-1.5 text-[12.5px] text-muted">
                    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-olive" />
                    Served in {data.mode} mode
                  </span>
                </Tooltip>
              </div>
            </div>

            <div className="flex items-center justify-center">
              <Image
                src={meta.art}
                alt={meta.artAlt}
                width={460}
                height={460}
                priority
                sizes="(max-width: 1024px) 50vw, 300px"
                className="h-[220px] w-auto object-contain"
              />
            </div>
          </div>
        </Rise>
      </Container>

      {/* --- the messy input --------------------------------------------- */}
      <Container className="py-14">
        <SectionHeading
          index={1}
          title="The row as the organizer supplied it"
          subtitle="No cleaning, no correction. This is the input."
        />
        <div className="card-surface mt-6 overflow-hidden">
          <dl className="divide-y divide-line-soft">
            <RawRow term="Row number" value={data.product.row_number?.toString() ?? "—"} />
            <RawRow term="MPN" value={data.product.mpn} mono />
            <RawRow term="Description" value={data.product.raw_description || "—"} mono />
            <RawRow term="Manufacturer column" value={data.product.raw_manufacturer || "—"} mono />
            <RawRow
              term="Brand signals"
              value={
                data.product.raw_brand_signals.length
                  ? data.product.raw_brand_signals.join(", ")
                  : "none"
              }
              mono
            />
          </dl>
        </div>
      </Container>

      {/* --- deterministic stages ---------------------------------------- */}
      <Container className="pb-14">
        <SectionHeading
          index={2}
          title="Normalization and classification"
          subtitle="Deterministic. No provider, no network, no model."
        />
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="card-surface p-6">
            <h3 className="text-[15px] font-semibold text-ink">Manufacturer</h3>
            <p className="display-heading mt-2 text-[24px] text-green">
              {data.normalization.manufacturer ?? "—"}
            </p>
            <dl className="mt-4 space-y-2.5 text-[13.5px]">
              <DataRow term="Decision" value={data.normalization.manufacturer_decision} />
              <DataRow term="Reason" value={data.normalization.manufacturer_reason} code />
              <DataRow term="Authority" value={data.normalization.manufacturer_authority ?? "—"} />
            </dl>
            <p className="mt-3.5 text-[13px] leading-relaxed text-muted">
              {reasonSentence(data.normalization.manufacturer_reason) ?? ""}
            </p>

            <div className="mt-5 border-t border-line-soft pt-4">
              <h4 className="text-[13.5px] font-semibold text-ink">Brand</h4>
              <p className="mt-1.5 text-[14px] text-ink">
                {data.normalization.brand ?? "withheld"}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <ReasonCode code={data.normalization.brand_decision} />
                <ReasonCode code={data.normalization.brand_reason} />
              </div>
              <p className="mt-2.5 text-[12.5px] leading-relaxed text-muted">
                {reasonSentence(data.normalization.brand_reason) ?? ""}
              </p>
            </div>
          </div>

          <div className="card-surface p-6">
            <h3 className="text-[15px] font-semibold text-ink">Product family</h3>
            <p className="display-heading mt-2 text-[24px] text-green">
              {data.classification.family ?? "—"}
            </p>
            <dl className="mt-4 space-y-2.5 text-[13.5px]">
              <DataRow term="Decision" value={data.classification.decision} />
              <DataRow term="Reason" value={data.classification.reason} code />
              <DataRow
                term="Cues that fired"
                value={data.classification.cues.join(", ") || "none"}
              />
            </dl>
            <p className="mt-3.5 text-[13px] leading-relaxed text-muted">
              {reasonSentence(data.classification.reason) ?? ""}
            </p>

            <div className="mt-5 border-t border-line-soft pt-4">
              <h4 className="text-[13.5px] font-semibold text-ink">Delivery taxonomy</h4>
              <p className="mt-1.5 text-[14px] text-ink">
                {data.classification.delivery_classpath ?? "not assigned"}
              </p>
              <p className="mt-2 text-[12.5px] leading-relaxed text-muted">
                A classpath is only assigned where an organizer example authorises one.
                Blank is the correct and common answer.
              </p>
            </div>
          </div>
        </div>
      </Container>

      {/* --- discovery and acquisition ------------------------------------ */}
      <Container className="pb-14">
        <SectionHeading
          index={3}
          title="Source discovery and authority"
          subtitle="Only reviewed manufacturer domains are searched at all."
        />
        <div className="card-surface mt-6 p-6">
          <div className="grid gap-6 lg:grid-cols-3">
            <div>
              <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted">
                Discovery
              </p>
              <div className="mt-2.5">
                <StageBadge status={data.source.discovery_status} />
              </div>
              <dl className="mt-4 space-y-2.5 text-[13.5px]">
                <DataRow term="Results returned" value={String(data.source.results_returned)} />
                <DataRow term="Exact candidates" value={String(data.source.exact_candidates)} />
                <DataRow term="Relevance" value={data.source.relevance ?? "—"} code />
              </dl>
            </div>

            <div>
              <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted">
                Authority
              </p>
              <p className="mt-2.5 text-[15px] font-medium text-forest">
                {data.source.authority ?? "—"}
              </p>
              <dl className="mt-4 space-y-2.5 text-[13.5px]">
                <DataRow term="Source kind" value={data.source.source_kind ?? "—"} />
                <DataRow term="Artifact" value={data.source.artifact_kind ?? "none stored"} />
              </dl>
            </div>

            <div className="min-w-0">
              <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted">
                Location
              </p>
              {data.source.discovery_url ? (
                <a
                  href={data.source.discovery_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-2.5 block break-all font-mono text-[12.5px] text-green underline decoration-sage underline-offset-4"
                >
                  {data.source.discovery_url}
                </a>
              ) : (
                <p className="mt-2.5 text-[13.5px] text-muted">
                  No locator established an exact reference.
                </p>
              )}
              {data.source.artifact_sha256 ? (
                <p className="mt-3 break-all font-mono text-[11.5px] text-muted">
                  sha256 {data.source.artifact_sha256}
                </p>
              ) : null}
            </div>
          </div>
        </div>

        {data.source.blocker ? (
          <div className="mt-6">
            <BlockerPanel detail={data} />
          </div>
        ) : null}
      </Container>

      {/* --- identity and model proposal ---------------------------------- */}
      <Container className="pb-14">
        <SectionHeading
          index={4}
          title="Identity and model proposal"
          subtitle="A document has to prove it is about this SKU before anything reads it."
        />
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="card-surface p-6">
            <h3 className="text-[15px] font-semibold text-ink">Artifact identity</h3>
            <p className="display-heading mt-2 text-[24px] text-ink">
              {data.identity.decision === "NOT_RUN" ? "Not run" : data.identity.decision}
            </p>
            <dl className="mt-4 space-y-2.5 text-[13.5px]">
              <DataRow term="Scope" value={data.identity.identity_scope ?? "—"} code />
              <DataRow term="Covers MPN" value={data.identity.covers_mpn ?? "—"} mono />
              <DataRow term="Reason" value={data.identity.reason} code />
            </dl>
            <p className="mt-3.5 text-[13px] leading-relaxed text-muted">
              {reasonSentence(data.identity.reason) ?? ""}
            </p>
          </div>

          <div className="card-surface p-6">
            <h3 className="text-[15px] font-semibold text-ink">Model proposal</h3>
            {data.ai.ran ? (
              <>
                <p className="display-heading mt-2 text-[24px] text-ink">
                  {data.ai.proposal_count} proposals
                </p>
                <dl className="mt-4 space-y-2.5 text-[13.5px]">
                  <DataRow term="Model" value={data.ai.model ?? "—"} mono />
                  <DataRow term="Profile" value={data.ai.profile_id ?? "—"} mono />
                  <DataRow term="Bound to a locator" value={String(data.ai.source_bound_count)} />
                  <DataRow term="Rejected at binding" value={String(data.ai.rejected_count)} />
                </dl>
                <p className="mt-3.5 text-[13px] leading-relaxed text-muted">
                  Proposals are not facts. Each one still has to survive verification
                  against the stored document.
                </p>
              </>
            ) : (
              <>
                <p className="display-heading mt-2 text-[24px] text-muted">Not run</p>
                <p className="mt-3.5 text-[14px] leading-relaxed text-ink">
                  {data.ai.not_run_reason}
                </p>
                <p className="mt-3 text-[13px] leading-relaxed text-muted">
                  No model was called, so there is nothing here that could have been
                  mistaken for a finding.
                </p>
              </>
            )}
          </div>
        </div>
      </Container>

      {/* --- verification ------------------------------------------------- */}
      {complete ? (
        <>
          <Container className="pb-14">
            <SectionHeading
              index={5}
              title="Verification"
              subtitle="Every proposal re-derived from the stored source. Click any row for its evidence."
            />
            <div className="mt-6">
              <AttributeTable attributes={data.attributes} />
            </div>
          </Container>

          <Container className="pb-14">
            <SectionHeading
              index={6}
              title="Proposal, evidence, decision"
              subtitle="The same three columns for all ten proposals."
            />
            <div className="mt-6">
              <EvidenceComparison detail={data} />
            </div>
          </Container>
        </>
      ) : null}

      {/* --- delivery boundary -------------------------------------------- */}
      <Container className="pb-14">
        <SectionHeading
          index={complete ? 7 : 5}
          title="The delivery boundary"
          subtitle="A verified manufacturer fact is still not an authorised delivery value."
        />
        <div className="card-surface mt-6 flex flex-col gap-6 p-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-[620px]">
            <p className="display-heading text-[30px] text-ink">
              {data.delivery.mapped_count} mapped
            </p>
            <div className="mt-2.5">
              <ReasonCode code={data.delivery.mapping_status} />
            </div>
            <p className="mt-3.5 text-[14px] leading-relaxed text-muted">
              {data.delivery.unauthorized_reason}
            </p>
          </div>
          <Image
            src="/art/mascot-delivery.png"
            alt=""
            aria-hidden="true"
            width={620}
            height={619}
            sizes="140px"
            loading="lazy"
            className="w-[110px] shrink-0 opacity-70"
          />
        </div>
      </Container>

      {/* --- the whole timeline ------------------------------------------- */}
      <Container className="pb-16">
        <SectionHeading
          index={complete ? 8 : 6}
          title="Every stage, and where each answer came from"
          subtitle="Stages that never ran are shown unlit rather than hidden."
        />
        <div className="mt-6">
          <JourneyTimeline timeline={data.timeline} />
        </div>
        <div className="mt-4">
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
      </Container>

      <CTASection
        title="Compare it with the other two."
        body="One case completed, one was refused a document, and one never established an exact reference. The difference between them is the product."
        primary={{ href: "/demo", label: "All three cases" }}
        secondary={{ href: "/proof", label: "See the proof page" }}
      />
    </>
  );
}

function RawRow({ term, value, mono = false }: { term: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-baseline sm:gap-6">
      <dt className="w-[190px] shrink-0 text-[13px] text-muted">{term}</dt>
      <dd className={"break-words text-[14.5px] text-ink " + (mono ? "font-mono" : "")}>
        {value}
      </dd>
    </div>
  );
}

function DataRow({
  term,
  value,
  code = false,
  mono = false,
}: {
  term: string;
  value: string;
  code?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-muted">{term}</dt>
      <dd className="min-w-0 text-right">
        {code ? (
          <ReasonCode code={value} />
        ) : (
          <span className={"break-words text-ink " + (mono ? "font-mono text-[12.5px]" : "")}>
            {value}
          </span>
        )}
      </dd>
    </div>
  );
}
