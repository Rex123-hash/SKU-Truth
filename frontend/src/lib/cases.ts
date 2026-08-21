/**
 * Frontend route identity for the three demo cases.
 *
 * Routes are keyed by a short slug, never by MPN. One of the three real organizer MPNs
 * is `SHOP/4X2/840/V1`: putting that in a URL segment would either break the route or
 * force a catch-all for no benefit. The slug maps to the server's `case_id`, which the
 * API accepts on the same path as an MPN.
 */

export type CaseSlug = "kichler" | "satco" | "feit";

export interface CaseMeta {
  slug: CaseSlug;
  /** The server's own case id. What actually gets requested. */
  caseId: string;
  manufacturer: string;
  mpn: string;
  /** Short outcome word for the card badge. */
  badge: string;
  /** What a judge should take away from this case in one line. */
  takeaway: string;
  art: string;
  artAlt: string;
}

export const CASES: Record<CaseSlug, CaseMeta> = {
  kichler: {
    slug: "kichler",
    caseId: "kichler-45297bk",
    manufacturer: "Kichler",
    mpn: "45297BK",
    badge: "Complete",
    takeaway: "The whole path runs: exact SKU, ten proposals, seven verified, three refused.",
    art: "/art/product-kichler.png",
    artAlt: "The Kichler outdoor wall lantern this case verifies",
  },
  satco: {
    slug: "satco",
    caseId: "satco-62-1875",
    manufacturer: "SATCO",
    mpn: "62-1875",
    badge: "Rate limited",
    takeaway: "A trusted source was found and the fetch was refused. Nothing was invented.",
    art: "/art/product-satco.png",
    artAlt: "The SATCO LED bulb this case could not acquire",
  },
  feit: {
    slug: "feit",
    caseId: "feit-shop-4x2-840-v1",
    manufacturer: "Feit",
    mpn: "SHOP/4X2/840/V1",
    badge: "Representation gap",
    takeaway: "Official pages exist, but none spelled the reference exactly. Slash is not hyphen.",
    art: "/art/product-feit.png",
    artAlt: "The Feit Electric shop light tube this case could not match exactly",
  },
};

export const CASE_ORDER: CaseSlug[] = ["kichler", "satco", "feit"];

export const isCaseSlug = (value: string): value is CaseSlug => value in CASES;

/** Resolve a slug to the key the API is asked for, or `null` for anything unknown. */
export const caseIdForSlug = (value: string): string | null =>
  isCaseSlug(value) ? CASES[value].caseId : null;

/** The reverse direction, for linking out of an API payload back into a route. */
export const slugForCaseId = (caseId: string): CaseSlug | null =>
  CASE_ORDER.find((slug) => CASES[slug].caseId === caseId) ?? null;
