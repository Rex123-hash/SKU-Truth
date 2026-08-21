"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";

import { ButtonLink, Container } from "./primitives";
import { Logo } from "./Logo";

interface NavItem {
  label: string;
  href: string;
}

/**
 * There is no Pricing entry and no Log in button. This project has no pricing model and
 * no authentication, and putting either in the navigation of a submission would be a
 * claim the repository cannot support.
 */
const NAV: NavItem[] = [
  { label: "How it works", href: "/#how-it-works" },
  { label: "Demo", href: "/demo" },
  { label: "Proof", href: "/proof" },
];

export function AppNavbar() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");

  return (
    <header
      ref={navRef}
      className={
        "sticky top-0 z-50 transition-colors duration-300 " +
        (scrolled
          ? "border-b border-line bg-cream/85 backdrop-blur-[10px]"
          : "border-b border-transparent bg-cream")
      }
    >
      <Container>
        <div className="flex h-[72px] items-center justify-between gap-6">
          <Link href="/" className="flex items-center gap-2.5" aria-label="SKUTruth home">
            <Logo className="h-7 w-7" />
            <span className="display-heading text-[22px] tracking-tight text-ink">SKUTruth</span>
          </Link>

          <nav aria-label="Primary" className="hidden lg:block">
            <ul className="flex items-center gap-1">
              {NAV.map((item) => (
                <li key={item.label} className="relative">
                  <Link
                    href={item.href}
                    aria-current={isActive(item.href) ? "page" : undefined}
                    className={
                      "inline-block rounded-full px-3.5 py-2 text-[14.5px] transition-colors " +
                      (isActive(item.href) ? "text-forest" : "text-ink/80 hover:text-forest")
                    }
                  >
                    {item.label}
                  </Link>
                  {isActive(item.href) ? (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-3.5 -bottom-0.5 h-[2px] rounded-full bg-olive"
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </nav>

          <div className="hidden items-center gap-2.5 lg:flex">
            <ButtonLink href="/demo">Launch demo</ButtonLink>
          </div>

          <button
            type="button"
            className="lg:hidden"
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </Container>

      {mobileOpen ? (
        <div id="mobile-nav" className="border-t border-line bg-cream lg:hidden">
          <Container className="py-4">
            <ul className="flex flex-col gap-0.5">
              {NAV.map((item) => (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className="block rounded-[10px] px-3 py-3 text-[16px] text-ink hover:bg-cream-soft"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-col gap-2.5">
              <ButtonLink href="/demo" className="w-full" onClick={() => setMobileOpen(false)}>
                Launch demo
              </ButtonLink>
            </div>
          </Container>
        </div>
      ) : null}
    </header>
  );
}
