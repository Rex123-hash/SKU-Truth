import type { Metadata } from "next";

import { WorkbenchShell } from "@/components/workbench/WorkbenchShell";

export const metadata: Metadata = {
  title: "Analyze Catalog",
  description: "Upload, validate, analyze, review, and export your catalog with SKUTruth.",
};

export default function WorkbenchPage() {
  return <WorkbenchShell />;
}
