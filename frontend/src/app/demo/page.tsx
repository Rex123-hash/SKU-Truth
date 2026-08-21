import type { Metadata } from "next";

import { DemoLanding } from "@/components/demo/DemoLanding";

export const metadata: Metadata = {
  title: "Demo",
  description: "Three truthful SKUTruth demo cases: one complete, one rate limited, and one representation gap.",
};

export default function DemoPage() {
  return <DemoLanding />;
}
