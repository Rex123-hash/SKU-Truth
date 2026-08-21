import type { Metadata } from "next";
import Image from "next/image";
import { AlertTriangle, Boxes, Building2, FileCheck2, FileInput, PackageCheck, Search, ShieldCheck, ShoppingBag, Sparkles, XCircle } from "lucide-react";

import { CTASection } from "@/components/CTASection";
import { ReasonCode } from "@/components/Badges";
import { ConnectedRail, type ConnectedStep } from "@/components/marketing/ConnectedRail";
import { ProductPageHero } from "@/components/marketing/ProductPageHero";
import { StorySection } from "@/components/marketing/StorySection";
import { Rise, Stagger, StaggerItem } from "@/components/motion";
import { ButtonLink } from "@/components/primitives";

export const metadata: Metadata = {
  title: "SKUTruth Solutions — Product Data Verification",
  description: "See how evidence-first product verification supports industrial distribution, marketplace, private-label, and manufacturer catalog workflows.",
};

const WORKFLOW: ConnectedStep[] = [
  { label: "01", title: "Input", body: "Messy organizer row or catalog.", Icon: FileInput },
  { label: "02", title: "Trusted source", body: "Reviewed manufacturer authority.", Icon: Search },
  { label: "03", title: "Proposal", body: "Source-bound model candidate.", Icon: Sparkles },
  { label: "04", title: "Verification", body: "Mechanical evidence check.", Icon: ShieldCheck },
  { label: "05", title: "Review", body: "Typed refusal or evidence inspection.", Icon: FileCheck2 },
  { label: "06", title: "Output", body: "Structured, authorized result.", Icon: PackageCheck },
];

const USE_CASES = [
  { title: "Marketplace operations", Icon: ShoppingBag, art: "/art/robot-inspector.png", problem: "Seller-provided fields, duplicate listings, ambiguous identifiers, and unsafe enrichment.", actions: ["Prefer official-source evidence", "Require exact SKU identity", "Route ambiguous facts into review"] },
  { title: "Private label & catalog operations", Icon: Boxes, art: "/art/mascot-delivery.png", problem: "Multiple source documents, inconsistent terminology, manual content work, and approval boundaries.", actions: ["Carry evidence provenance", "Separate verified facts from proposals", "Export controlled outcomes"] },
  { title: "Manufacturer catalog teams", Icon: Building2, art: "/art/stage-verification.png", problem: "Specifications are split across product pages, technical PDFs, JSON-LD, and distributor records.", actions: ["Extract traceable candidates", "Bind every proposal to a locator", "Let evidence—not the model—decide"] },
] as const;

export default function SolutionsPage() {
  return <div className="premium-page">
    <ProductPageHero eyebrow="Solutions" title={<>Product data breaks differently. <span className="underline-swash text-green">Trust does not.</span></>} body="SKUTruth gives catalog teams a source-first verification layer between messy inputs and structured product content." primary={{ href: "/workbench", label: "Analyze catalog" }} secondary={{ href: "/platform", label: "See the pipeline" }} note="Built for messy industrial catalogs." art={[
      { src: "/art/crate-sku.png", alt: "Industrial crate containing components and an SKU tag", className: "absolute right-[3%] top-[8%] w-[73%]" },
      { src: "/art/mascot-barcode.png", alt: "Barcode catalog mascot", className: "absolute bottom-[2%] left-[2%] z-10 w-[34%]" },
    ]} />

    <StorySection index={1} title="Industrial distribution" subtitle="Normalize supplier inputs and make source-backed product onboarding reviewable.">
      <div className="grid gap-5 overflow-hidden rounded-[20px] border border-line bg-card lg:grid-cols-[1.05fr_.95fr]">
        <div className="p-7 sm:p-9"><span className="premium-icon-frame flex h-11 w-11 items-center justify-center rounded-[13px] text-forest"><Boxes className="h-5 w-5" /></span><h2 className="display-heading mt-5 text-[30px]">Large catalogs magnify small data defects.</h2><p className="mt-4 text-[14px] leading-relaxed text-muted">Manufacturer aliases, cryptic descriptions, and missing attributes enter at row level and become expensive at catalog scale.</p><ul className="mt-6 grid gap-3 sm:grid-cols-2">{["Normalize manufacturer signals", "Classify deterministic cues", "Find reviewed official sources", "Export typed outcomes"].map((item) => <li key={item} className="flex gap-2.5 text-[13px] text-ink"><FileCheck2 className="mt-0.5 h-4 w-4 shrink-0 text-olive" />{item}</li>)}</ul><ButtonLink href="/platform#pipeline" variant="secondary" className="mt-7">See pipeline</ButtonLink></div>
        <div className="group relative min-h-[330px] overflow-hidden bg-cream-soft">
          <div aria-hidden="true" className="absolute inset-x-[8%] top-[12%] h-[58%] rounded-full bg-[radial-gradient(ellipse_at_center,rgba(165,185,149,.22),transparent_70%)]" />
          <span className="absolute left-6 top-6 rounded-full border border-line bg-card/85 px-3 py-1.5 font-mono text-[10px] font-semibold tracking-[.08em] text-green shadow-[var(--shadow-soft)]">SOURCE → VERIFY → DELIVER</span>
          <Image src="/art/product-kichler.png" alt="" aria-hidden="true" width={286} height={460} sizes="120px" className="absolute bottom-[58px] left-[16%] h-[150px] w-auto object-contain drop-shadow-[0_12px_16px_rgba(23,32,25,.14)] transition-transform duration-500 group-hover:-translate-y-1" />
          <Image src="/art/product-satco.png" alt="" aria-hidden="true" width={231} height={460} sizes="90px" className="absolute bottom-[58px] left-[47%] h-[135px] w-auto object-contain drop-shadow-[0_12px_16px_rgba(23,32,25,.12)] transition-transform delay-75 duration-500 group-hover:-translate-y-1" />
          <Image src="/art/product-feit.png" alt="" aria-hidden="true" width={460} height={455} sizes="145px" className="absolute bottom-[62px] right-[8%] h-[115px] w-auto -rotate-12 object-contain drop-shadow-[0_12px_16px_rgba(23,32,25,.1)] transition-transform delay-100 duration-500 group-hover:-translate-y-1 group-hover:-rotate-6" />
          <Image src="/art/conveyor-belt.png" alt="Industrial products moving through a catalog verification pipeline" width={950} height={520} sizes="(min-width: 1024px) 600px, 100vw" className="absolute bottom-0 right-0 z-10 w-full object-contain drop-shadow-[0_8px_12px_rgba(23,32,25,.14)]" />
        </div>
      </div>
    </StorySection>

    <StorySection index={2} title="A verification layer for different catalog teams" subtitle="Use-case positioning, not customer claims. Each team keeps its own authority and workflow." tone="soft">
      <Stagger className="grid gap-4 lg:grid-cols-3" step={.07}>{USE_CASES.map(({ title, Icon, art, problem, actions }, index) => <StaggerItem key={title} className="h-full"><article className={`card-surface relative h-full overflow-hidden p-6 ${index === 1 ? "lg:translate-y-6" : ""}`}><div className="flex items-center gap-3"><span className="premium-icon-frame flex h-10 w-10 items-center justify-center rounded-[12px] text-forest"><Icon className="h-5 w-5" /></span><h3 className="display-heading text-[22px] text-ink">{title}</h3></div><p className="mt-4 min-h-[72px] text-[13px] leading-relaxed text-muted">{problem}</p><ul className="mt-4 space-y-2.5">{actions.map((item) => <li key={item} className="flex gap-2 text-[12.5px] text-ink"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-olive" />{item}</li>)}</ul><div className="mt-5 h-[130px]"><Image src={art} alt="" aria-hidden="true" width={500} height={500} className="ml-auto h-full w-auto object-contain" /></div></article></StaggerItem>)}</Stagger>
    </StorySection>

    <StorySection index={3} title="One common workflow" subtitle="The same evidence boundary carries the record from input to output.">
      <ConnectedRail steps={WORKFLOW} compact />
    </StorySection>

    <StorySection index={4} title={<span className="text-cream">What SKUTruth refuses</span>} subtitle={<span className="text-[var(--text-on-dark-secondary)]">Stopping is an explicit outcome, not a hidden failure.</span>} tone="dark">
      <div className="grid gap-4 md:grid-cols-2">
        <Refusal title="No exact source?" action="Stop discovery." reason="NO_EXACT_SOURCE" art="/art/product-feit.png" />
        <Refusal title="HTTP source blocked?" action="Stop acquisition." reason="SOURCE_RATE_LIMITED" art="/art/product-satco.png" />
        <Refusal title="Source property ambiguous?" action="Withhold the proposal." reason="SOURCE_PROPERTY_NOT_AUTHORIZED" />
        <Refusal title="Delivery vocabulary unauthorized?" action="Leave the delivery field blank." reason="UNAUTHORIZED" />
      </div>
    </StorySection>

    <CTASection title="Try it on a catalog." body="Bring CSV, XLSX, or one product row into the public deterministic workbench." primary={{ href: "/workbench", label: "Analyze catalog" }} secondary={{ href: "/demo", label: "See recorded cases" }} />
  </div>;
}

function Refusal({ title, action, reason, art }: { title: string; action: string; reason: string; art?: string }) {
  const dimensions = art ? productDimensions(art) : undefined;
  return <Rise><article className="dark-card relative min-h-[190px] overflow-hidden rounded-[16px] p-6"><AlertTriangle className="relative z-10 h-5 w-5 text-amber-soft" /><h3 className="display-heading relative z-10 mt-4 text-[24px] text-cream">{title}</h3><p className="relative z-10 mt-1 text-[15px] font-medium text-amber-soft">{action}</p><div className="relative z-10 mt-4"><ReasonCode code={reason} className="border-[var(--border-dark)] bg-forest-deep/70 text-cream" /></div>{art && dimensions ? <Image src={art} alt="" aria-hidden="true" width={dimensions.width} height={dimensions.height} sizes="30vw" className="absolute bottom-0 right-4 h-[88%] w-auto max-w-[30%] object-contain object-bottom opacity-85" /> : <XCircle className="absolute bottom-5 right-5 h-12 w-12 text-cream/20" />}</article></Rise>;
}
function productDimensions(art: string) { return art.includes("satco") ? { width: 231, height: 460 } : { width: 460, height: 455 }; }
