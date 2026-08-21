import Image from "next/image";
import type { ReactNode } from "react";

import { DottedArrow, Sparkle } from "@/components/Decor";
import { Float, Rise } from "@/components/motion";
import { ButtonLink, Container, Eyebrow } from "@/components/primitives";

export interface HeroArt {
  src: string;
  alt: string;
  width?: number;
  className?: string;
  decorative?: boolean;
}

export function ProductPageHero({ eyebrow, title, body, primary, secondary, art, note }: {
  eyebrow: string;
  title: ReactNode;
  body: string;
  primary: { href: string; label: string };
  secondary: { href: string; label: string };
  art: HeroArt[];
  note: string;
}) {
  return (
    <section className="paper-grain relative overflow-hidden border-b border-line-soft py-12 sm:py-16">
      <Container>
        <div className="grid min-h-[440px] items-center gap-10 lg:grid-cols-[minmax(0,.92fr)_minmax(460px,1.08fr)]">
          <Rise className="relative z-10">
            <Eyebrow>{eyebrow}</Eyebrow>
            <h1 className="display-heading mt-6 text-[clamp(2.8rem,5vw,4.5rem)] text-ink">{title}</h1>
            <p className="mt-6 max-w-[65ch] text-[17px] leading-[1.72] text-muted sm:text-[18px]">{body}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href={primary.href}>{primary.label}</ButtonLink>
              <ButtonLink href={secondary.href} variant="secondary">{secondary.label}</ButtonLink>
            </div>
          </Rise>

          <div className="relative min-h-[330px] sm:min-h-[410px]">
            <div aria-hidden="true" className="absolute inset-x-[4%] bottom-[8%] h-[62%] rounded-[50%] bg-[radial-gradient(ellipse_at_center,#eee5d5_0%,rgba(247,241,231,0)_72%)]" />
            <Sparkle className="absolute left-[8%] top-[12%]" size={22} />
            <Sparkle className="absolute right-[7%] top-[4%]" size={27} delay={1.1} />
            <DottedArrow className="absolute bottom-[15%] left-[2%] hidden sm:block" />
            {art.map((item, index) => (
              <Float key={item.src} distance={index ? 5 : 7} duration={7.5 + index} delay={index * .45} className={item.className ?? "absolute inset-0 flex items-center justify-center"}>
                <Image src={item.src} alt={item.decorative ? "" : item.alt} aria-hidden={item.decorative || undefined} width={item.width ?? 900} height={item.width ?? 900} priority={index === 0} sizes="(max-width: 1024px) 82vw, 600px" className="h-auto w-full object-contain drop-shadow-[0_22px_34px_rgba(23,32,25,.10)]" />
              </Float>
            ))}
            <div className="card-surface absolute right-[1%] top-[5%] z-20 max-w-[195px] px-4 py-3.5">
              <p className="display-heading text-[16px] leading-snug text-forest">{note}</p>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
