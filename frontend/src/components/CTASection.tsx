"use client";

import Image from "next/image";

import { ButtonLink, Container } from "./primitives";
import { Rise } from "./motion";

/** The deep forest-green band that closes every page, with the robot peeking in. */
export function CTASection({
  title = "Messy data in. Verified truth out.",
  body = "Open the demo and follow one organizer row all the way to a verified manufacturer fact — and to the two that stopped.",
  primary = { href: "/demo", label: "Launch demo" },
  secondary = { href: "/demo/kichler", label: "Explore the Kichler journey" },
}: {
  title?: string;
  body?: string;
  primary?: { href: string; label: string };
  secondary?: { href: string; label: string };
}) {
  return (
    <Container className="pb-16 pt-4">
      <Rise>
        <div className="relative overflow-hidden rounded-[20px] bg-forest px-7 py-10 sm:px-12 sm:py-12">
          <div className="relative z-10 flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-[520px]">
              <h2 className="display-heading text-[28px] text-cream sm:text-[34px]">{title}</h2>
              <p className="mt-3.5 text-[15.5px] leading-relaxed text-cream/75">{body}</p>
            </div>

            <div className="flex flex-wrap items-center gap-3 lg:pr-[200px]">
              <ButtonLink href={primary.href} variant="onDark">
                {primary.label}
              </ButtonLink>
              <ButtonLink href={secondary.href} variant="ghostOnDark" withArrow={false}>
                {secondary.label}
              </ButtonLink>
            </div>
          </div>

          <Image
            src="/art/robot-inspector.png"
            alt=""
            aria-hidden="true"
            width={815}
            height={820}
            sizes="240px"
            loading="lazy"
            className="pointer-events-none absolute -bottom-6 right-4 hidden w-[186px] lg:block"
          />
        </div>
      </Rise>
    </Container>
  );
}
