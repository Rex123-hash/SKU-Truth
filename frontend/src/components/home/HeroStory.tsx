"use client";

import Image from "next/image";

import { ButtonLink, Container, Eyebrow } from "@/components/primitives";
import { DottedArrow, Sparkle } from "@/components/Decor";
import { Float, Rise } from "@/components/motion";

/**
 * The hero, built to the approved lockup: editorial serif headline on the left with the
 * amber swash under the emphasised phrase, and the illustration cluster floating free on
 * the right rather than boxed inside a dashboard screenshot.
 */
export function HeroStory() {
  return (
    <section className="paper-grain relative overflow-hidden pb-6 pt-10 sm:pt-14">
      <Container>
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.18fr)] lg:gap-8">
          <div className="relative z-10">
            <Rise>
              <Eyebrow>Industrial product intelligence</Eyebrow>
            </Rise>

            <Rise delay={0.06}>
              <h1
                aria-label="From messy data to verified truth."
                className="display-heading mt-6 text-[42px] text-ink sm:text-[54px] lg:text-[60px]"
              >
                From messy data
                <br />
                to <span className="underline-swash text-green">verified truth.</span>
              </h1>
            </Rise>

            <Rise delay={0.12}>
              <p className="mt-6 max-w-[430px] text-[17px] leading-relaxed text-muted">
                AI proposes. SKUTruth verifies against the manufacturer&rsquo;s own document —
                and refuses anything the evidence does not support.
              </p>
            </Rise>

            <Rise delay={0.18}>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <ButtonLink href="/workbench">Analyze catalog</ButtonLink>
                <ButtonLink href="/demo" variant="secondary" withArrow={false}>
                  See real demo
                </ButtonLink>
              </div>
            </Rise>

            <Rise delay={0.24}>
              <dl className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-4 text-[13.5px]">
                {[
                  ["1,000", "organizer rows"],
                  ["252", "delivery fields"],
                  ["3", "manufacturer cases"],
                ].map(([value, label]) => (
                  <div key={label} className="flex flex-row-reverse items-baseline justify-end gap-2">
                    <dt className="text-muted">{label}</dt>
                    <dd className="display-heading text-[22px] text-forest">{value}</dd>
                  </div>
                ))}
              </dl>
            </Rise>
          </div>

          <div className="relative min-h-[320px] sm:min-h-[430px] lg:min-h-[500px]">
            {/* A soft warm pool so the cutouts sit on the page instead of hovering over it. */}
            <div
              aria-hidden="true"
              className="absolute left-1/2 top-1/2 h-[78%] w-[92%] -translate-x-1/2 -translate-y-1/2 rounded-[50%] bg-[radial-gradient(ellipse_at_center,#F1E9DA_0%,rgba(247,241,231,0)_68%)]"
            />

            <Sparkle className="absolute left-[6%] top-[8%] z-10" size={20} />
            <Sparkle className="absolute right-[16%] top-[2%] z-10" size={26} delay={1.2} />
            <DottedArrow
              className="absolute -left-2 bottom-[22%] z-10 hidden sm:block"
              d="M4 6C22 30 54 38 92 28"
              width={100}
              height={44}
            />

            <div className="absolute inset-0 flex items-center justify-center pr-0 sm:pr-[82px] lg:pr-[104px]">
              <Float distance={6} duration={7.5}>
                <Image
                  src="/art/hero-cluster.png"
                  alt="A barcode character handing a SKU tag to a crate of bearings"
                  width={1100}
                  height={815}
                  priority
                  sizes="(max-width: 1024px) 90vw, 620px"
                  className="w-[min(100%,600px)] drop-shadow-[0_24px_36px_rgba(23,32,25,0.10)]"
                />
              </Float>
            </div>

            <Float
              distance={7}
              duration={8.5}
              delay={0.7}
              rotate={1.5}
              className="absolute bottom-[2%] right-[1%] hidden sm:block lg:right-0"
            >
              <Image
                src="/art/robot-inspector.png"
                alt=""
                aria-hidden="true"
                width={815}
                height={820}
                sizes="180px"
                className="w-[128px] drop-shadow-[0_18px_28px_rgba(23,32,25,0.10)] lg:w-[154px]"
              />
            </Float>

            {/* The tagline card that sits above the cluster in every approved layout. */}
            <div className="card-surface absolute right-[2%] top-[3%] hidden max-w-[190px] px-4 py-3.5 lg:block">
              <p className="display-heading text-[16px] leading-snug text-ink">
                Clean data.
                <br />
                <span className="text-green">Better decisions.</span>
              </p>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
