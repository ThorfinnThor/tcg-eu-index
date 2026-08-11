import type { Metadata } from "next";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { RelatedPages } from "@/components/RelatedPages";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 3600;
export const metadata: Metadata = pageMetadata(
  "methodology",
  "Index methodology",
  "Read the versioned calculation, eligibility, weighting, and data-quality methodology for the European TCG Index."
);

export default async function MethodologyPage() {
  const markdown = await readFile(path.join(process.cwd(), "../../docs/methodology/v1.1.0.md"), "utf8").catch(
    () => "# Methodology\n\nMethodology document will be available after build packaging."
  );
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Breadcrumbs items={[{ label: "Overview", href: "/" }, { label: "Methodology" }]} />
      <h1 className="text-3xl font-semibold">Methodology</h1>
      <article className="surface prose prose-invert mt-6 max-w-none p-5">
        <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-paper/75">{markdown}</pre>
      </article>
      <RelatedPages definitionId="methodology" />
    </div>
  );
}
