// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import CompanyPage from "@/app/company/page";
import PlatformPage from "@/app/platform/page";
import ResourcesPage from "@/app/resources/page";
import SolutionsPage from "@/app/solutions/page";
import { AppNavbar } from "@/components/AppNavbar";
import { PRIMARY_NAV, SITE_ROUTES } from "./site";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

afterEach(cleanup);

const pages = [
  ["/platform", PlatformPage, "One platform for"],
  ["/solutions", SolutionsPage, "Product data breaks differently"],
  ["/resources", ResourcesPage, "Resources for"],
  ["/company", CompanyPage, "Trust should survive"],
] as const;

describe("product website routes", () => {
  for (const [route, Page, heading] of pages) {
    it(`renders ${route}`, () => {
      const markup = renderToStaticMarkup(<Page />);
      expect(markup).toContain(heading);
      expect(markup).toContain('href="/workbench"');
      expect(markup).not.toContain('href="/pricing"');
      expect(markup.toLowerCase()).not.toContain("trusted by leading");
    });
  }

  it("keeps every primary navigation destination on a real route", () => {
    for (const item of PRIMARY_NAV) expect(SITE_ROUTES).toContain(item.href);
  });

  it("uses only known local destinations across the four pages", () => {
    const known = new Set<string>(SITE_ROUTES);
    const markup = pages.map(([, Page]) => renderToStaticMarkup(<Page />)).join("");
    const hrefs = Array.from(markup.matchAll(/href="(\/[^"#?]*)(?:#[^"]*)?"/g), (match) => match[1] || "/");
    for (const href of hrefs) expect(known.has(href || "/"), `unknown local destination ${href}`).toBe(true);
  });

  it("keeps all three real case links in the website", () => {
    const markup = renderToStaticMarkup(<ResourcesPage />);
    expect(markup).toContain('href="/demo/kichler"');
    expect(markup).toContain('href="/demo/satco"');
    expect(markup).toContain('href="/demo/feit"');
  });
});

describe("responsive navigation", () => {
  it("exposes every product route from the mobile menu", () => {
    render(<AppNavbar />);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = screen.getByRole("button", { name: "Close menu" }).closest("header");
    expect(mobile).toBeTruthy();
    for (const item of PRIMARY_NAV) {
      const matches = screen.getAllByRole("link", { name: item.label });
      expect(matches.some((link) => link.getAttribute("href") === item.href)).toBe(true);
    }
  });
});
