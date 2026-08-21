import type { ReactNode } from "react";

import { Container, SectionHeading } from "@/components/primitives";

export function StorySection({ id, index, title, subtitle, children, tone = "plain", className = "" }: {
  id?: string;
  index?: number;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  tone?: "plain" | "soft" | "dark";
  className?: string;
}) {
  const toneClass = tone === "dark" ? "dark-section" : tone === "soft" ? "border-y border-line-soft bg-cream-soft" : "";
  return (
    <section id={id} className={`scroll-mt-24 py-16 sm:py-22 ${toneClass} ${className}`}>
      <Container>
        <SectionHeading index={index} title={title} subtitle={subtitle} />
        <div className="mt-8">{children}</div>
      </Container>
    </section>
  );
}
