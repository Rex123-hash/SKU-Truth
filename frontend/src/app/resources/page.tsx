import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, BookOpen, Boxes, Braces, Code2, FileJson, GitBranch, PlayCircle, RotateCcw, ShieldCheck, TerminalSquare } from "lucide-react";

import { CTASection } from "@/components/CTASection";
import { ProductPageHero } from "@/components/marketing/ProductPageHero";
import { StorySection } from "@/components/marketing/StorySection";
import { Rise, Stagger, StaggerItem } from "@/components/motion";

export const metadata: Metadata = {
  title: "SKUTruth Resources — Architecture, Trust & API",
  description: "Explore the real SKUTruth architecture, trust model, API routes, replay design, demo cases, and developer quickstart.",
};

const REPO = "https://github.com/Rex123-hash/SKU-Truth";

const START = [
  { title: "How SKUTruth works", body: "Follow the eight stages and the boundary each one enforces.", href: "/platform#pipeline", Icon: PlayCircle },
  { title: "Trust model", body: "Understand evidence bases, typed refusals, and delivery authority.", href: "/proof", Icon: ShieldCheck },
  { title: "Real demo cases", body: "Compare a complete path, an acquisition blocker, and a representation gap.", href: "/demo", Icon: Boxes },
  { title: "Catalog Workbench", body: "Upload or enter product rows and export structured outcomes.", href: "/workbench", Icon: FileJson },
];

const TECHNICAL = [
  { title: "Architecture", href: `${REPO}#pipeline`, note: "README pipeline and trust boundaries", Icon: Braces },
  { title: "API reference", href: `${REPO}/blob/main/backend/skutruth/api/README.md#routes`, note: "Submission API contract", Icon: Code2 },
  { title: "Delivery schema", href: "/proof#api", note: "252 columns and 50 triplets", Icon: FileJson },
  { title: "Evidence & verification", href: "/proof#evidence", note: "Evidence bases and factual checks", Icon: ShieldCheck },
  { title: "Replay design", href: `${REPO}/blob/main/backend/skutruth/api/README.md#why-the-demo-record-is-committed`, note: "Why recorded cases remain deterministic", Icon: RotateCcw },
  { title: "GitHub repository", href: REPO, note: "Source, data, tests, and scripts", Icon: GitBranch },
];

const ENDPOINTS = ["GET /api/health", "GET /api/demo/products", "GET /api/demo/products/{mpn}", "POST /api/analyze", "GET /api/schema"];

const GLOSSARY = [
  ["EXACT", "Search relevance says a result contains the literal requested reference."],
  ["EXACT_SKU", "Artifact identity proves the stored source covers this specific SKU."],
  ["MODEL_PROPOSAL", "A model-generated candidate. It is not yet a fact."],
  ["MANUFACTURER_EVIDENCE", "Evidence re-derived from a reviewed manufacturer source."],
  ["VERIFIED", "A proposed value mechanically matches its authorized source structure."],
  ["WITHHELD", "The system deliberately refuses to promote a proposal to fact."],
  ["BLOCKED", "A stage could not continue, so downstream stages do not run."],
  ["UNAUTHORIZED", "A fact lacks permission to populate a delivery field."],
  ["RECORDED_OBSERVATION", "A live-run condition recorded by an operator, not replayed as if it happened now."],
  ["DEMO_REPLAY", "Deterministic public execution using committed interactions and artifacts without external calls."],
];

export default function ResourcesPage() {
  return <div className="premium-page">
    <ProductPageHero eyebrow="Knowledge hub" title={<>Resources for <span className="underline-swash text-green">evidence-first</span> product intelligence.</>} body="Start with the product, inspect the trust model, then go as deep as the real API and repository allow." primary={{ href: "#start", label: "Start here" }} secondary={{ href: REPO, label: "Explore GitHub" }} note="Real routes. Real cases. No invented library." art={[
      { src: "/art/stage-messy-data.png", alt: "A stack of messy catalog documents ready for review", className: "absolute left-[2%] top-[12%] w-[66%]" },
      { src: "/art/robot-inspector.png", alt: "Verification robot inspecting product documentation", className: "absolute bottom-[0%] right-[2%] z-10 w-[38%]" },
    ]} />

    <StorySection id="start" index={1} title="Start here" subtitle="Four working surfaces, ordered from product overview to hands-on analysis.">
      <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" step={.07}>{START.map(({ title, body, href, Icon }, index) => <StaggerItem key={title} className="h-full"><Link href={href} className={`card-surface group block h-full p-6 transition-transform hover:-translate-y-1 ${index === 0 ? "lg:col-span-1 lg:row-span-1" : ""}`}><span className="premium-icon-frame flex h-11 w-11 items-center justify-center rounded-[13px] text-forest"><Icon className="h-5.5 w-5.5" /></span><h2 className="display-heading mt-5 text-[22px] text-ink">{title}</h2><p className="mt-2 text-[13px] leading-relaxed text-muted">{body}</p><span className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-green">Open resource <ArrowUpRight className="h-3.5 w-3.5" /></span></Link></StaggerItem>)}</Stagger>
    </StorySection>

    <StorySection index={2} title="Technical resources" subtitle="Every destination below exists today—in the product, proof page, or public repository." tone="soft">
      <div className="grid gap-4 lg:grid-cols-[1.15fr_.85fr]">
        <Stagger className="grid gap-3 sm:grid-cols-2" step={.055}>{TECHNICAL.map(({ title, href, note, Icon }) => <StaggerItem key={title}><Link href={href} target={href.startsWith("http") ? "_blank" : undefined} rel={href.startsWith("http") ? "noreferrer" : undefined} className="group flex h-full items-center gap-4 rounded-[14px] border border-line bg-card p-4 hover:border-sage"><span className="premium-icon-frame flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] text-forest"><Icon className="h-5 w-5" /></span><span className="min-w-0"><strong className="block text-[14px] text-ink">{title}</strong><span className="mt-1 block text-[11.5px] leading-relaxed text-muted">{note}</span></span><ArrowUpRight className="ml-auto h-4 w-4 shrink-0 text-sage" /></Link></StaggerItem>)}</Stagger>
        <Rise className="dark-section relative min-h-[320px] overflow-hidden rounded-[18px] border border-[var(--border-dark-soft)] p-6"><BookOpen className="h-7 w-7 text-amber-soft" /><h3 className="display-heading mt-5 max-w-[260px] text-[28px]">The documentation follows the same trust boundary as the product.</h3><p className="mt-3 max-w-[300px] text-[14.5px] leading-relaxed text-[var(--text-on-dark-secondary)]">Terms describe actual types and behavior. No confidence theatre, customer fiction, or unsupported integration claims.</p><Image src="/art/mascot-search.png" alt="" aria-hidden="true" width={520} height={520} className="absolute -bottom-10 -right-8 w-[210px] opacity-80" /></Rise>
      </div>
    </StorySection>

    <StorySection index={3} title="Three cases, three kinds of proof" subtitle="Success is one case. Safe refusal and preserved ambiguity are the other two.">
      <div className="grid gap-4 lg:grid-cols-3"><Case href="/demo/kichler" name="Kichler" mpn="45297BK" outcome="Complete evidence chain" art="/art/product-kichler.png" /><Case href="/demo/satco" name="SATCO" mpn="62-1875" outcome="Acquisition blocker" art="/art/product-satco.png" /><Case href="/demo/feit" name="Feit" mpn="SHOP/4X2/840/V1" outcome="Representation gap" art="/art/product-feit.png" /></div>
    </StorySection>

    <StorySection index={4} title="Developer quickstart" subtitle="Commands copied from the current README and frontend package scripts." tone="dark">
      <div className="grid min-w-0 gap-4 lg:grid-cols-2"><CodeBlock title="Run the API" lines={["python -m uvicorn skutruth.api.asgi:app --app-dir backend --port 8000"]} /><CodeBlock title="Run the frontend" lines={["cd frontend", "npm install", "npm run dev"]} /></div>
    </StorySection>

    <StorySection index={5} title="Submission API overview" subtitle="A small typed surface. Unknown analysis gets deterministic stages and honest NOT_RUN downstream results.">
      <div className="card-surface overflow-hidden"><ul className="divide-y divide-line-soft">{ENDPOINTS.map((endpoint) => <li key={endpoint} className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><code className="break-all font-mono text-[13px] text-green">{endpoint}</code><span className="text-[11.5px] text-muted">typed JSON · explicit failure</span></li>)}</ul></div>
    </StorySection>

    <StorySection index={6} title="Trust glossary" subtitle="The vocabulary used by the backend and the user interface.">
      <dl className="grid gap-3 md:grid-cols-2">{GLOSSARY.map(([term, definition]) => <div key={term} className="rounded-[13px] border border-line bg-card p-4"><dt><code className="font-mono text-[12px] font-semibold text-green">{term}</code></dt><dd className="mt-2 text-[12.5px] leading-relaxed text-muted">{definition}</dd></div>)}</dl>
    </StorySection>

    <CTASection title="Put the resources into action." body="Inspect the repository, or bring a safe sample catalog into the workbench." primary={{ href: REPO, label: "Explore GitHub" }} secondary={{ href: "/workbench", label: "Analyze catalog" }} />
  </div>;
}

function Case({ href, name, mpn, outcome, art }: { href: string; name: string; mpn: string; outcome: string; art: string }) { const dimensions = productDimensions(art); return <Rise><Link href={href} className="card-surface group relative block min-h-[280px] overflow-hidden p-6"><p className="relative z-10 text-[10.5px] font-semibold uppercase tracking-[.12em] text-olive">{outcome}</p><h3 className="display-heading relative z-10 mt-3 text-[28px] text-ink">{name}</h3><code className="relative z-10 mt-1 block break-all text-[12px] text-green">{mpn}</code><Image src={art} alt={`${name} ${mpn} product`} width={dimensions.width} height={dimensions.height} sizes="(min-width: 1024px) 240px, 58vw" className="absolute bottom-0 right-3 h-[78%] w-auto max-w-[58%] object-contain object-bottom transition-transform group-hover:-translate-y-1" /><span className="absolute bottom-5 left-6 z-10 text-[12.5px] font-semibold text-green">Open real case →</span></Link></Rise>; }
function productDimensions(art: string) { return art.includes("kichler") ? { width: 286, height: 460 } : art.includes("satco") ? { width: 231, height: 460 } : { width: 460, height: 455 }; }
function CodeBlock({ title, lines }: { title: string; lines: string[] }) { return <div className="dark-card min-w-0 max-w-full overflow-hidden rounded-[16px] p-5"><div className="flex items-center gap-2 text-[13px] font-semibold text-cream"><TerminalSquare className="h-4 w-4 text-amber-soft" />{title}</div><pre className="mt-4 max-w-full overflow-x-auto rounded-[10px] border border-[var(--border-dark-soft)] bg-forest-deep/70 p-4 text-[13px] leading-7 text-[var(--text-on-dark-secondary)]"><code>{lines.join("\n")}</code></pre></div>; }
