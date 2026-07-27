import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Live coverage checker",
  description:
    "Enter a CPT or ICD-10 code and a clinical note to see a citation-backed Medicare coverage decision, live.",
};

export default function CheckerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
