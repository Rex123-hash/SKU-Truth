"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useRef } from "react";

import type { EvidenceLocatorView, VerifiedAttribute, WithheldAttribute } from "@/lib/types";
import { LOCATOR_KIND_LABEL, reasonSentence } from "@/lib/vocab";
import { ReasonCode } from "./Badges";

/**
 * The evidence behind one attribute.
 *
 * Everything shown here comes from the API's own locator view: the block index, the JSON
 * pointer, the element index, and the short excerpt the server caps at 200 characters.
 * Raw page HTML, stored file paths and cassette names exist on the server and stop there
 * — the response has never carried them, and this drawer does not go looking.
 */

export type DrawerAttribute =
  | { kind: "verified"; attribute: VerifiedAttribute }
  | { kind: "withheld"; attribute: WithheldAttribute };

export function EvidenceDrawer({
  entry,
  onClose,
}: {
  entry: DrawerAttribute | null;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!entry) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Focus moves into the panel so keyboard and screen-reader users land inside it.
    panelRef.current?.focus();
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [entry, onClose]);

  const verified = entry?.kind === "verified" ? entry.attribute : null;
  const withheld = entry?.kind === "withheld" ? entry.attribute : null;
  const locator: EvidenceLocatorView | null =
    verified?.locator ?? withheld?.locator ?? null;

  return (
    <AnimatePresence>
      {entry ? (
        <motion.div
          className="fixed inset-0 z-[70] flex justify-end"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <button
            type="button"
            aria-label="Close evidence panel"
            className="absolute inset-0 bg-[#172019]/25 backdrop-blur-[2px]"
            onClick={onClose}
          />

          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Evidence detail"
            tabIndex={-1}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
            className="relative flex h-full w-full max-w-[520px] flex-col overflow-y-auto border-l border-line bg-card shadow-[var(--shadow-lift)]"
          >
            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line-soft bg-card px-6 py-5">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-olive">
                  Evidence
                </p>
                <h2 className="display-heading mt-1.5 text-[23px] text-ink">
                  {verified?.label ?? withheld?.label}
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="rounded-full border border-line p-2 text-muted transition-colors hover:text-forest"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-6 px-6 py-6">
              <Block title="What the model proposed">
                <Pair
                  label={verified?.label ?? withheld?.label ?? ""}
                  value={verified?.value ?? withheld?.proposed_value ?? ""}
                  uom={withheld?.proposed_uom ?? ""}
                />
              </Block>

              <Block title="What the source says">
                {(verified?.source_label ?? withheld?.source_label) ||
                (verified?.source_value ?? withheld?.source_value) ? (
                  <Pair
                    label={verified?.source_label || withheld?.source_label || "(no property name)"}
                    value={verified?.source_value ?? withheld?.source_value ?? ""}
                    uom={verified?.source_uom ?? ""}
                  />
                ) : (
                  <p className="text-[14px] leading-relaxed text-muted">
                    No labelled property was found at this location.
                  </p>
                )}
              </Block>

              <Block title="Decision">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span
                    className={
                      "display-heading text-[24px] " +
                      (verified ? "text-forest" : "text-[#8a6410]")
                    }
                  >
                    {verified ? "Verified" : "Withheld"}
                  </span>
                  <ReasonCode code={verified?.reason ?? withheld?.reason ?? ""} />
                </div>
                <p className="mt-2.5 text-[14px] leading-relaxed text-ink">
                  {reasonSentence(verified?.reason ?? withheld?.reason ?? "") ?? ""}
                </p>
                {withheld?.detail ? (
                  <p className="mt-2 font-mono text-[12px] text-muted">{withheld.detail}</p>
                ) : null}
              </Block>

              {verified ? (
                <Block title="Authority">
                  <dl className="space-y-2.5 text-[13.5px]">
                    <Row term="Evidence authority" value={verified.authority} />
                    <Row term="Adjudication" value={verified.decision} />
                    <Row term="Delivery mapping" value={verified.unilog_mapping_status} />
                    <Row
                      term="Delivery eligible"
                      value={verified.delivery_eligible ? "Yes" : "No"}
                    />
                  </dl>
                </Block>
              ) : null}

              {locator ? (
                <Block title="Where it was found">
                  <dl className="space-y-2.5 text-[13.5px]">
                    <Row
                      term="Evidence kind"
                      value={LOCATOR_KIND_LABEL[locator.kind] ?? locator.kind}
                    />
                    {locator.jsonld_block_index !== null ? (
                      <Row term="JSON-LD block" value={String(locator.jsonld_block_index)} />
                    ) : null}
                    {locator.json_pointer ? (
                      <Row term="JSON pointer" value={locator.json_pointer} mono />
                    ) : null}
                    {locator.element_index !== null ? (
                      <Row term="Element index" value={String(locator.element_index)} />
                    ) : null}
                    {locator.start_offset !== null && locator.end_offset !== null ? (
                      <Row
                        term="Character range"
                        value={locator.start_offset + "–" + locator.end_offset}
                      />
                    ) : null}
                  </dl>

                  {locator.excerpt ? (
                    <figure className="mt-4">
                      <figcaption className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted">
                        Source excerpt
                      </figcaption>
                      <blockquote className="mt-2 rounded-[10px] border border-line bg-cream px-4 py-3 font-mono text-[13px] leading-relaxed text-ink">
                        {locator.excerpt}
                      </blockquote>
                    </figure>
                  ) : null}
                </Block>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-olive">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Pair({ label, value, uom }: { label: string; value: string; uom?: string }) {
  return (
    <div className="rounded-[12px] border border-line bg-cream-soft/70 px-4 py-3.5">
      <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className="display-heading mt-1 break-words text-[21px] text-ink">
        {value}
        {uom ? <span className="ml-1.5 text-[15px] text-muted">{uom}</span> : null}
      </p>
    </div>
  );
}

function Row({ term, value, mono = false }: { term: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-muted">{term}</dt>
      <dd className={"text-right text-ink " + (mono ? "font-mono text-[12.5px]" : "")}>{value}</dd>
    </div>
  );
}
