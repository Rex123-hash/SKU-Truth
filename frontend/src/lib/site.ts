export const SITE_ROUTES = [
  "/",
  "/platform",
  "/solutions",
  "/workbench",
  "/demo",
  "/demo/kichler",
  "/demo/satco",
  "/demo/feit",
  "/proof",
  "/resources",
  "/company",
] as const;

export const PRIMARY_NAV = [
  { label: "Platform", href: "/platform" },
  { label: "Solutions", href: "/solutions" },
  { label: "Analyze Catalog", href: "/workbench" },
  { label: "Demo", href: "/demo" },
  { label: "Proof", href: "/proof" },
  { label: "Resources", href: "/resources" },
  { label: "Company", href: "/company" },
] as const;
