import type { Metadata } from "next";
import Image from "next/image";
import { Braces, Database, FileWarning, GitBranch, Hand, Scale, SearchCheck, ShieldCheck, Sparkles } from "lucide-react";

import { CTASection } from "@/components/CTASection";
import { MetricCard } from "@/components/MetricCard";
import { ProductPageHero } from "@/components/marketing/ProductPageHero";
import { StorySection } from "@/components/marketing/StorySection";
import { Rise, Stagger, StaggerItem } from "@/components/motion";
import { ReasonCode, StageBadge } from "@/components/Badges";

export const metadata: Metadata = {
  title: "About SKUTruth — Why Evidence Comes Before Enrichment",
  description: "Why SKUTruth separates discovery, identity, model proposals, verified facts, and delivery authority in messy industrial catalog workflows.",
};

const PRINCIPLES = [
  [ShieldCheck, "Fail closed", "When evidence ends, the pipeline says so and stops."],
  [SearchCheck, "Source first", "Reviewed manufacturer authority comes before enrichment."],
  [Braces, "Deterministic where possible", "Normalization, classification, verification, and delivery rules remain mechanical."],
  [Sparkles, "Model where useful", "AI drafts candidates only after exact evidence exists."],
  [GitBranch, "Typed boundaries", "Proposals, facts, evidence, and delivery values are different shapes."],
  [Database, "Replayable evidence", "Stored interactions and artifacts make the public cases reproducible."],
  [Hand, "Human review where required", "Review inspects evidence without rewriting truth."],
] as const;

export default function CompanyPage() {
  return <div className="premium-page">
    <ProductPageHero eyebrow="Why SKUTruth exists" title={<>Trust should survive contact with <span className="underline-swash text-green">messy data.</span></>} body="SKUTruth was built around one idea: useful product intelligence is not just about extracting more fields. It is about knowing which fields deserve to survive." primary={{ href: "/demo", label: "Launch demo" }} secondary={{ href: "/workbench", label: "Analyze catalog" }} note="Useful intelligence knows when to stop." art={[
      { src: "/art/robot-inspector.png", alt: "SKUTruth verification robot examining product information", className: "absolute left-[19%] top-[5%] w-[58%]" },
      { src: "/art/mascot-barcode.png", alt: "Barcode mascot representing a raw catalog identifier", className: "absolute bottom-[1%] left-[0%] z-10 w-[29%]" },
      { src: "/art/crate-sku.png", alt: "Industrial crate containing components and an SKU tag", className: "absolute bottom-[0%] right-[0%] z-10 w-[35%]" },
    ]} />

    <StorySection index={1} title="The problem begins in ordinary catalog rows" subtitle="Short descriptions, manufacturer aliases, partial brands, and fragmented sources are normal—not edge cases.">
      <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <div className="card-surface overflow-hidden"><div className="border-b border-line-soft bg-cream-soft px-5 py-3 text-[11px] font-semibold uppercase tracking-[.1em] text-muted">Organizer inputs</div><dl className="divide-y divide-line-soft"><MessyRow term="Mfg_Part_Num" value="SHOP/4X2/840/V1" /><MessyRow term="Part_Desc" value={'62-1875 10" Led Ceiling Lt Bn'} /><MessyRow term="Part_Manuf" value="Kichler Lighting (KICLI)" /><MessyRow term="Brand signals" value="E1 / Unilog / DIB may disagree" /></dl></div>
        <Rise className="relative min-h-[300px] overflow-hidden rounded-[18px] border border-line bg-cream-soft"><Image src="/art/stage-messy-data.png" alt="A stack of inconsistent catalog documents" width={720} height={720} className="absolute inset-x-0 bottom-0 mx-auto w-[330px] object-contain" /><div className="absolute left-5 top-5 rounded-[10px] border border-amber-soft bg-amber-wash px-3 py-2 text-[11px] font-semibold text-[#73530d]"><FileWarning className="mr-1.5 inline h-3.5 w-3.5" />Input is not evidence</div></Rise>
      </div>
    </StorySection>

    <StorySection index={2} title={<span className="text-cream">AI should propose. Evidence should decide.</span>} subtitle={<span className="text-[var(--text-on-dark-secondary)]">Three separations keep useful automation from becoming invented certainty.</span>} tone="dark">
      <div className="grid gap-4 lg:grid-cols-3"><Boundary left="Discovery says EXACT" right="Artifact proves EXACT_SKU" /><Boundary left="Model proposal" right="Verified manufacturer fact" /><Boundary left="Verified fact" right="Authorized delivery value" /></div>
    </StorySection>

    <StorySection index={3} title="How we build" subtitle="The engineering principles are visible in both the code and the product states.">
      <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" step={.055}>{PRINCIPLES.map(([Icon, title, body], index) => <StaggerItem key={title} className={index === 6 ? "sm:col-span-2 lg:col-span-2" : ""}><article className="card-surface flex h-full gap-4 p-5"><span className="premium-icon-frame flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] text-forest"><Icon className="h-5 w-5" /></span><div><h3 className="text-[14px] font-semibold text-ink">{title}</h3><p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{body}</p></div></article></StaggerItem>)}</Stagger>
    </StorySection>

    <StorySection index={4} title="Real engineering proof" subtitle="Current repository facts, not commercial traction or invented confidence scores." tone="soft">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5"><Metric value="1,000" label="organizer rows" /><Metric value="252" label="delivery columns" /><Metric value="50" label="attribute triplets" /><Metric value="3" label="recorded manufacturers" /><Metric value="10 / 7 / 3" label="Kichler proposed / verified / withheld" wide /></div>
    </StorySection>

    <StorySection index={5} title="Success is not the only proof" subtitle="A trustworthy system must also know when to stop.">
      <div className="grid gap-4 lg:grid-cols-3"><Case name="Kichler" mpn="45297BK" status="SUCCESS" message="Full path: exact SKU, ten proposals, seven verified, three withheld." reason="FACT_VERIFIED" art="/art/product-kichler.png" /><Case name="SATCO" mpn="62-1875" status="BLOCKED" message="Trusted source discovered; acquisition stopped on recorded HTTP 429." reason="SOURCE_RATE_LIMITED" art="/art/product-satco.png" /><Case name="Feit" mpn="SHOP/4X2/840/V1" status="REVIEW" message="Official results observed; slash and hyphen representations stayed distinct." reason="NO_EXACT_SOURCE" art="/art/product-feit.png" /></div>
    </StorySection>

    <CTASection title="See the system make the decision." body="Compare the recorded cases, then try the deterministic workbench on your own catalog row." primary={{ href: "/demo", label: "Launch demo" }} secondary={{ href: "/workbench", label: "Analyze catalog" }} />
  </div>;
}

function MessyRow({ term, value }: { term: string; value: string }) { return <div className="grid gap-1 px-5 py-4 sm:grid-cols-[170px_1fr]"><dt className="font-mono text-[11.5px] text-green">{term}</dt><dd className="break-words text-[13.5px] text-ink">{value}</dd></div>; }
function Boundary({ left, right }: { left: string; right: string }) { return <article className="dark-card rounded-[16px] p-6"><Scale className="h-6 w-6 text-amber-soft" /><p className="mt-5 text-[16px] font-medium text-cream">{left}</p><p className="my-3 text-[25px] text-amber">≠</p><p className="text-[16px] font-medium text-cream">{right}</p></article>; }
function Metric({ value, label, wide = false }: { value: string; label: string; wide?: boolean }) { return <Rise className={wide ? "col-span-2 lg:col-span-1" : ""}><MetricCard eyebrow="Repository fact" value={value} label={label} /></Rise>; }
function Case({ name, mpn, status, message, reason, art }: { name: string; mpn: string; status: "SUCCESS" | "BLOCKED" | "REVIEW"; message: string; reason: string; art: string }) { const dimensions = productDimensions(art); return <Rise><article className="card-surface relative min-h-[325px] overflow-hidden p-6"><StageBadge status={status} label={status === "SUCCESS" ? "Complete path" : status === "BLOCKED" ? "Safe blocker" : "Representation gap"} /><h3 className="display-heading relative z-10 mt-5 text-[27px] text-ink">{name}</h3><code className="relative z-10 mt-1 block break-all text-[12px] text-green">{mpn}</code><p className="relative z-10 mt-4 max-w-[245px] text-[12.5px] leading-relaxed text-muted">{message}</p><ReasonCode code={reason} className="relative z-10 mt-3" /><Image src={art} alt={`${name} ${mpn} product`} width={dimensions.width} height={dimensions.height} sizes="(min-width: 1024px) 190px, 42vw" className="absolute bottom-0 right-3 h-[58%] w-auto max-w-[46%] object-contain object-bottom opacity-90" /></article></Rise>; }
function productDimensions(art: string) { return art.includes("kichler") ? { width: 286, height: 460 } : art.includes("satco") ? { width: 231, height: 460 } : { width: 460, height: 455 }; }
