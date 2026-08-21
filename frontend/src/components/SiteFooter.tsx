import Link from "next/link";

import { Container } from "./primitives";
import { Logo } from "./Logo";

/**
 * The approved footer keeps concise link columns and a tagline card. What it does not keep
 * is the concept mockup's distributor logo strip or its SOC 2 badge: neither a customer
 * relationship nor a security certification exists here, and a submission that implies
 * one is making a false claim about a real organisation.
 */
const COLUMNS = [
  {
    heading: "Overview",
    links: [
      { label: "Home", href: "/" },
      { label: "How it works", href: "/#how-it-works" },
      { label: "Featured journey", href: "/#journey" },
      { label: "All demo cases", href: "/demo" },
    ],
  },
  {
    heading: "Cases",
    links: [
      { label: "Kichler 45297BK", href: "/demo/kichler" },
      { label: "SATCO 62-1875", href: "/demo/satco" },
      { label: "Feit shop light", href: "/demo/feit" },
    ],
  },
  {
    heading: "Proof",
    links: [
      { label: "Evidence model", href: "/proof#evidence" },
      { label: "Trust boundaries", href: "/proof#boundaries" },
      { label: "API contract", href: "/proof#api" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-cream-soft">
      <Container className="py-14">
        <div className="grid gap-10 lg:grid-cols-[1.15fr_2.6fr_1.15fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <Logo className="h-6 w-6" />
              <span className="display-heading text-[20px] text-ink">SKUTruth</span>
            </div>
            <p className="mt-3.5 max-w-[240px] text-[14px] leading-relaxed text-muted">
              From messy distributor rows to verified manufacturer facts — and an honest
              refusal wherever the evidence runs out.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {COLUMNS.map((column) => (
              <div key={column.heading}>
                <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-forest">
                  {column.heading}
                </h3>
                <ul className="mt-3.5 space-y-2.5">
                  {column.links.map((link) => (
                    <li key={link.href + link.label}>
                      <Link
                        href={link.href}
                        className="text-[13.5px] text-muted transition-colors hover:text-forest"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="card-surface flex flex-col justify-center p-6">
            <p className="display-heading text-[21px] leading-snug text-ink">
              Clean data.
              <br />
              <span className="text-green">Better decisions.</span>
            </p>
            <p className="mt-2.5 text-[13px] text-muted">Evidence before enrichment.</p>
          </div>
        </div>

        <div className="mt-11 flex flex-col gap-3 border-t border-line pt-6 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>SKUTruth — UniHack 2026 submission.</p>
          <p>
            <a
              href="https://github.com/Rex123-hash/SKU-Truth"
              className="transition-colors hover:text-forest"
              target="_blank"
              rel="noreferrer"
            >
              github.com/Rex123-hash/SKU-Truth
            </a>
          </p>
        </div>
      </Container>
    </footer>
  );
}
