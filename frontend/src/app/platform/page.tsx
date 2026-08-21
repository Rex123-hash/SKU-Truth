import type { Metadata } from "next";
import Image from "next/image";
import { Bot, Braces, Database, FileSearch, FileText, Fingerprint, LockKeyhole, MapPin, PackageCheck, SearchCheck, ShieldCheck, Sparkles, Tags, XCircle } from "lucide-react";

import { CTASection } from "@/components/CTASection";
import { ReasonCode, StageBadge } from "@/components/Badges";
import { ConnectedRail, type ConnectedStep } from "@/components/marketing/ConnectedRail";
import { ProductPageHero } from "@/components/marketing/ProductPageHero";
import { StorySection } from "@/components/marketing/StorySection";
import { Rise, Stagger, StaggerItem } from "@/components/motion";

export const metadata: Metadata = {
  title: "SKUTruth Platform — Evidence-First Product Intelligence",
  description: "See how SKUTruth normalizes, discovers, identifies, verifies, and delivers product data without turning model output into fact.",
};

const PIPELINE: ConnectedStep[] = [
  { label: "01", title: "Normalize", body: "Resolve messy manufacturer and brand signals.", boundary: "A proposal can still require review.", Icon: Tags },
  { label: "02", title: "Classify", body: "Determine the internal product family from deterministic cues.", boundary: "Unknown remains unknown.", Icon: Braces },
  { label: "03", title: "Discover", body: "Locate official manufacturer evidence on reviewed domains.", boundary: "Search EXACT is not artifact identity.", Icon: FileSearch },
  { label: "04", title: "Acquire", body: "Fetch safely and store a bounded HTML or PDF artifact.", boundary: "Blocked sources stop the path.", Icon: Database },
  { label: "05", title: "Identify", body: "Prove the stored source covers the exact organizer SKU.", boundary: "Representation gaps are not corrected away.", Icon: Fingerprint },
  { label: "06", title: "AI Propose", body: "Draft attributes and bind each one to a source locator.", boundary: "A proposal is not a fact.", Icon: Sparkles },
  { label: "07", title: "Verify", body: "Mechanically re-derive the proposed value from cited evidence.", boundary: "Ambiguous properties are withheld.", Icon: ShieldCheck },
  { label: "08", title: "Deliver", body: "Populate only fields allowed by the delivery contract.", boundary: "Verified does not mean authorized.", Icon: PackageCheck },
];

const EVIDENCE = [
  [FileText, "Official manufacturer HTML", "Visible text, tables, and metadata from a reviewed manufacturer domain."],
  [FileText, "Official PDF", "A safely acquired document whose identity is established before extraction."],
  [Braces, "JSON-LD", "Structured product properties addressed by block index and JSON pointer."],
  [SearchCheck, "Visible page structure", "Labelled elements and tables with stable element or character locators."],
  [MapPin, "Source locator", "The exact place a proposal points to, carried into review."],
  [LockKeyhole, "Artifact provenance", "Kind, final URL, and SHA-256 identify the stored evidence artifact."],
] as const;

const GUARDRAILS = [
  "Exact SKU before extraction",
  "Manufacturer-owned evidence first",
  "AI output starts as proposal",
  "Mechanical verification",
  "Explicit withholding",
  "No silent live-to-replay fallback",
  "No invented delivery mapping",
];

export default function PlatformPage() {
  return (
      <div className="premium-page">
      <ProductPageHero
        eyebrow="Evidence-first platform"
        title={<>One platform for <span className="underline-swash text-green">product truth.</span></>}
        body="Normalize, discover, verify and deliver — without turning model output into fact."
        primary={{ href: "/workbench", label: "Analyze catalog" }}
        secondary={{ href: "/demo", label: "Explore real demo" }}
        note="AI proposes. Evidence decides."
        art={[
          { src: "/art/hero-cluster.png", alt: "A barcode character and industrial crate carrying product identifiers", className: "absolute left-[2%] top-[15%] w-[88%]" },
          { src: "/art/robot-inspector.png", alt: "SKUTruth verification robot", className: "absolute bottom-[1%] right-[1%] z-10 w-[29%]" },
        ]}
      />

      <StorySection index={1} id="pipeline" title="The SKUTruth pipeline" subtitle="Eight connected stages. Each one has a typed result and a boundary the next stage cannot skip.">
        <ConnectedRail steps={PIPELINE} />
      </StorySection>

      <StorySection index={2} title="Verification is a comparison, not a score" subtitle="The model proposal, manufacturer evidence, and SKUTruth decision remain visibly separate." tone="soft">
        <div className="relative grid gap-5 lg:grid-cols-[.8fr_1.2fr] lg:items-center">
          <Rise className="relative min-h-[330px] overflow-hidden rounded-[18px] border border-line bg-card">
            <Image src="/art/product-kichler.png" alt="Kichler 45297BK outdoor wall lantern" width={286} height={460} sizes="(min-width: 1024px) 280px, 70vw" className="absolute bottom-0 left-1/2 h-[90%] w-auto max-w-[70%] -translate-x-1/2 object-contain object-bottom" />
            <div className="absolute left-5 top-5 rounded-full border border-sage bg-sage-soft px-3 py-1 text-[11px] font-semibold uppercase tracking-[.1em] text-forest">Stored manufacturer artifact</div>
            <div className="card-surface absolute bottom-5 right-5 px-4 py-3"><strong className="display-heading text-[27px] text-forest">7</strong><span className="ml-2 text-[12px] text-muted">verified facts</span></div>
          </Rise>
          <Stagger className="space-y-4" step={.09}>
            <StaggerItem><DecisionRow proposal="Black" evidence="Finish = Black" status="verified" reason="FACT_VERIFIED" /></StaggerItem>
            <StaggerItem><DecisionRow proposal="3-Light" evidence="Attribute = 3-Light" status="withheld" reason="SOURCE_PROPERTY_NOT_AUTHORIZED" /></StaggerItem>
            <StaggerItem><div className="rounded-[14px] border border-line bg-card p-5"><p className="text-[13.5px] leading-relaxed text-muted">A source may contain the same text and still fail to authorize the proposed meaning. SKUTruth preserves that distinction instead of converting similarity into confidence.</p></div></StaggerItem>
          </Stagger>
        </div>
      </StorySection>

      <StorySection index={3} title="Evidence types with provenance" subtitle="Official manufacturer evidence is privileged; arbitrary web pages are not treated as equivalent sources.">
        <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" step={.06}>
          {EVIDENCE.map(([Icon, title, body]) => <StaggerItem key={title} className="h-full"><article className="card-surface flex h-full gap-4 p-5"><span className="premium-icon-frame flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] text-forest"><Icon className="h-5 w-5" /></span><div><h3 className="text-[14px] font-semibold text-ink">{title}</h3><p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{body}</p></div></article></StaggerItem>)}
        </Stagger>
      </StorySection>

      <StorySection index={4} title="Truth first. Delivery authority second." subtitle="Verification establishes a manufacturer fact. The organizer contract separately decides where that fact may go." tone="dark">
        <div className="grid gap-6 lg:grid-cols-[1.12fr_.88fr]">
          <article className="dark-card rounded-[18px] p-6 sm:p-8">
            <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-dark-soft)] pb-5">
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-[.14em] text-amber-soft">Delivery contract</p>
                <h3 className="display-heading mt-2 text-[26px] text-cream">Ordered attribute structure</h3>
              </div>
              <span className="rounded-full border border-[var(--border-dark)] bg-forest-deep/55 px-3 py-1.5 font-mono text-[12px] font-semibold text-[var(--text-on-dark-secondary)]">×50 triplets</span>
            </header>
            <div className="mt-5 space-y-3">
              {Array.from({ length: 3 }).map((_, index) => <div key={index} className="grid gap-3 rounded-[13px] border border-[var(--border-dark-soft)] bg-forest-deep/35 p-4 sm:grid-cols-[112px_1fr] sm:items-center"><p className="font-mono text-[12px] font-semibold text-amber-soft">ATTRIBUTE {String(index + 1).padStart(2, "0")}</p><div className="grid grid-cols-[1fr_1.2fr_.72fr] gap-2">{["LABEL", "VALUE", "UOM"].map((item) => <div key={item} className="rounded-[9px] border border-[var(--border-dark-soft)] bg-[var(--surface-dark-raised)] px-3 py-3"><span className="block text-[11px] font-semibold tracking-[.08em] text-[var(--text-on-dark-secondary)]">{item}</span><span aria-hidden="true" className="mt-2 block h-1.5 rounded-full bg-sage/30" /></div>)}</div></div>)}
            </div>
            <p className="mt-5 max-w-[65ch] text-[14px] leading-relaxed text-[var(--text-on-dark-secondary)]">The structure continues through 50 ordered triplets. When delivery authority is absent, a blank cell is the correct—and explicit—result.</p>
          </article>
          <div className="grid grid-cols-2 gap-4">
            <Metric eyebrow="Delivery contract" value="252" label="ordered columns" />
            <Metric eyebrow="Attribute structure" value="50" label="LABEL · VALUE · UOM triplets" />
            <article className="col-span-2 rounded-[16px] border border-amber/65 bg-amber/[.1] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
              <p className="text-[12px] font-semibold uppercase tracking-[.13em] text-amber-soft">Current Kichler boundary</p>
              <p className="display-heading mt-3 text-[44px] leading-none text-cream">0</p>
              <p className="mt-2 text-[15px] font-medium text-[var(--text-on-dark-primary)]">authorized delivery mappings</p>
              <ReasonCode code="UNAUTHORIZED" className="mt-4 border-amber/70 bg-forest-deep/65 px-3 py-1.5 text-[13px] text-amber-soft" />
              <p className="mt-4 max-w-[52ch] text-[14px] leading-relaxed text-[var(--text-on-dark-secondary)]">Verified manufacturer facts remain blank in delivery output until an approved mapping exists.</p>
            </article>
          </div>
        </div>
      </StorySection>

      <StorySection index={5} title="Guardrails built into the product" subtitle="The boundaries are not policy copy around the system. They are represented in its types and stage results.">
        <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
          <div className="grid gap-4 sm:grid-cols-2">
            {["/art/feature-source-first.png", "/art/feature-guardrails.png", "/art/feature-verified.png", "/art/feature-integration.png"].map((src, index) => <Rise key={src} delay={index * .05}><div className="card-surface relative min-h-[205px] overflow-hidden p-5"><p className="relative z-10 max-w-[150px] text-[14px] font-semibold text-ink">{GUARDRAILS[index]}</p><Image src={src} alt="" aria-hidden="true" width={420} height={420} className="absolute bottom-0 right-0 max-h-[145px] w-[170px] object-contain object-bottom" /></div></Rise>)}
          </div>
          <div className="dark-section rounded-[18px] border border-[var(--border-dark-soft)] p-6 sm:p-8"><Bot className="h-8 w-8 text-amber-soft" /><h3 className="display-heading mt-5 text-[27px]">A useful refusal is a product result.</h3><ul className="mt-6 space-y-4">{GUARDRAILS.slice(4).map((item) => <li key={item} className="flex gap-3 text-[14.5px] text-[var(--text-on-dark-secondary)]"><XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-soft" />{item}</li>)}</ul></div>
        </div>
      </StorySection>

      <CTASection title="Bring your catalog into the pipeline." body="Upload CSV or XLSX, review the schema, run deterministic analysis, inspect evidence, and export the result." primary={{ href: "/workbench", label: "Analyze catalog" }} secondary={{ href: "/demo", label: "Explore real demo" }} />
      </div>
  );
}

function DecisionRow({ proposal, evidence, status, reason }: { proposal: string; evidence: string; status: "verified" | "withheld"; reason: string }) {
  return <article className="card-surface overflow-hidden"><div className="grid sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center"><Cell label="AI proposal" value={proposal} /><span className="hidden text-sage sm:block">→</span><Cell label="Manufacturer evidence" value={evidence} /><div className="border-t border-line-soft p-4 sm:border-l sm:border-t-0"><StageBadge status={status === "verified" ? "SUCCESS" : "WITHHELD"} label={status === "verified" ? "Verified" : "Withheld"} /><div className="mt-2"><ReasonCode code={reason} /></div></div></div></article>;
}
function Cell({ label, value }: { label: string; value: string }) { return <div className="p-4"><p className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted">{label}</p><p className="display-heading mt-2 text-[20px] text-ink">{value}</p></div>; }
function Metric({ eyebrow, value, label }: { eyebrow: string; value: string; label: string }) { return <article className="dark-card rounded-[16px] p-5 sm:p-6"><p className="text-[11px] font-semibold uppercase tracking-[.12em] text-[var(--status-success)]">{eyebrow}</p><p className="display-heading mt-3 text-[42px] leading-none text-cream">{value}</p><p className="mt-2 text-[14px] font-medium leading-relaxed text-[var(--text-on-dark-secondary)]">{label}</p></article>; }
