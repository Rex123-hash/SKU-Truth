import type { Metadata, Viewport } from "next";
import { Inter, Playfair_Display } from "next/font/google";

import { AppNavbar } from "@/components/AppNavbar";
import { CursorOrb } from "@/components/CursorOrb";
import { SiteFooter } from "@/components/SiteFooter";
import { MotionProvider } from "@/components/motion";
import "./globals.css";

const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-playfair",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "SKUTruth — from messy data to verified truth",
    template: "%s · SKUTruth",
  },
  description:
    "SKUTruth turns messy industrial catalogue rows into verified product facts. AI proposes, SKUTruth verifies against manufacturer evidence, and refuses what the evidence does not support.",
};

export const viewport: Viewport = {
  themeColor: "#F7F1E7",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${playfair.variable} ${inter.variable}`}
    >
      <body className="min-h-screen bg-cream text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-full focus:bg-forest focus:px-5 focus:py-2.5 focus:text-sm focus:font-medium focus:text-cream"
        >
          Skip to content
        </a>
        <MotionProvider>
          <CursorOrb />
          <AppNavbar />
          <main id="main" className="premium-page">{children}</main>
          <SiteFooter />
        </MotionProvider>
      </body>
    </html>
  );
}
