import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CaseDetail } from "@/components/demo/CaseDetail";
import { CASE_ORDER, CASES, isCaseSlug } from "@/lib/cases";

export const dynamicParams = false;

export function generateStaticParams() {
  return CASE_ORDER.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  if (!isCaseSlug(slug)) return {};
  const meta = CASES[slug];
  return {
    title: `${meta.manufacturer} ${meta.mpn}`,
    description: meta.takeaway,
  };
}

export default async function DemoCasePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  if (!isCaseSlug(slug)) notFound();
  return <CaseDetail key={slug} slug={slug} />;
}
