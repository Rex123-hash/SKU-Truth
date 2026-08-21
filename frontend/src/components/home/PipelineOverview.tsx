"use client";

import { getSchema } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { SchemaResponse } from "@/lib/types";

import { ApiUnavailable, Skeleton } from "@/components/ApiState";
import { Tooltip } from "@/components/Badges";
import { Container } from "@/components/primitives";
import { Rise, Stagger, StaggerItem } from "@/components/motion";
import { REPLAY_EXPLANATION } from "@/lib/vocab";

/**
 * Real project numbers only.
 *
 * The concept artwork for this section carried a "98% confidence" dial and a live
 * counter reading 2.4M records. Neither exists. Every figure below is either served by
 * `/api/schema` or is a count of things committed in this repository, and the two the
 * server does not supply are labelled as counts rather than as performance claims.
 */
export function PipelineOverview() {
  const { data, error, loading, reload } = useApi<SchemaResponse>(getSchema);

  const cards = [
    {
      value: data ? data.organizer_rows.toLocaleString("en-US") : null,
      label: "Organizer rows",
      note: "The supplied distributor file, in full.",
    },
    {
      value: data ? String(data.delivery_columns) : null,
      label: "Delivery fields",
      note: "The official delivery record's column count.",
    },
    {
      value: data ? String(data.attribute_triplets) : null,
      label: "Attribute triplets",
      note: "Label, value and unit slots per product.",
    },
    {
      value: "3",
      label: "Manufacturer cases",
      note: "Kichler, SATCO and Feit — run end to end.",
    },
    {
      value: "7",
      label: "Verified Kichler facts",
      note: "From ten proposals. Three were refused.",
    },
  ];

  return (
    <section className="py-14 sm:py-20">
      <Container>
        <Rise className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-[560px]">
            <h2 className="display-heading text-[30px] text-ink sm:text-[36px]">
              The numbers that are <span className="text-green">actually ours</span>.
            </h2>
            <p className="mt-3.5 text-[16px] leading-relaxed text-muted">
              No accuracy percentages, no record counts we cannot show you. These come
              from the delivery contract and the committed demo record.
            </p>
          </div>

          <Tooltip label={REPLAY_EXPLANATION}>
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3.5 py-2 text-[12.5px] text-muted">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-olive" />
              What does replay mode mean?
            </span>
          </Tooltip>
        </Rise>

        {error ? (
          <div className="mt-9 max-w-[560px]">
            <ApiUnavailable error={error} onRetry={reload} compact />
          </div>
        ) : null}

        <Stagger step={0.06} className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {cards.map((card) => (
            <StaggerItem key={card.label}>
              <div className="card-surface h-full p-5">
                {card.value === null && loading ? (
                  <Skeleton className="h-[42px] w-20" />
                ) : (
                  <p className="display-heading text-[36px] leading-none text-forest">
                    {card.value ?? "—"}
                  </p>
                )}
                <p className="mt-3 text-[14px] font-medium text-ink">{card.label}</p>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{card.note}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>

        {data ? (
          <Rise>
            <p className="mt-6 max-w-[760px] rounded-[12px] border border-line bg-card px-5 py-4 text-[13.5px] leading-relaxed text-muted">
              {data.trust_note}
            </p>
          </Rise>
        ) : null}
      </Container>
    </section>
  );
}
