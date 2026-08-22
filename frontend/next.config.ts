import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Keep local judge captures focused on the product rather than the framework's
  // floating development badge. Runtime errors still surface in the browser console.
  devIndicators: false,

  // The submission is served as plain files from Firebase Hosting. Nothing in this app
  // needs a server: there is no middleware, no route handler, no server action, and the
  // only dynamic route (`/demo/[slug]`) sets `dynamicParams = false` and enumerates its
  // three real cases through `generateStaticParams`.
  output: "export",

  // Emit `/platform/index.html` rather than `/platform.html`, so a judge pasting a deep
  // link straight into a fresh tab is served real generated HTML by Firebase without
  // needing a rewrite rule or `cleanUrls` to guess at the mapping.
  trailingSlash: true,

  images: {
    // Static export ships no image optimizer, so the originals are served as authored.
    // That happens to be the safest outcome for this illustration set: every source is a
    // local transparent PNG, and the previous `formats` list existed only to stop the
    // optimizer converting a cutout to a format without an alpha channel and putting a
    // cream rectangle behind every mascot. Serving the original PNG cannot do that.
    unoptimized: true,
  },
};

export default config;
