import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { formatPct } from "@/components/Metric";
import { RelatedPages } from "@/components/RelatedPages";
import { NewsletterSignup } from "@/components/NewsletterSignup";
import { getReports } from "@/lib/data";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 3600;
export const metadata: Metadata = pageMetadata(
  "reports",
  "Weekly reports",
  "Browse human-reviewed weekly reports for European trading card listing-price benchmarks."
);

export default async function ReportsPage() {
  const reportsPayload = await getReports();
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Breadcrumbs items={[{ label: "Overview", href: "/" }, { label: "Weekly reports" }]} />
      <div className="border-b border-line pb-6">
        <p className="text-sm text-amber">Human-reviewed weekly archive</p>
        <h1 className="mt-2 text-3xl font-semibold">Weekly reports</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
          Report records are generated from static JSON first, then marked published only after an editor review. Newsletter delivery is enabled only when a provider is configured on Vercel.
        </p>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-[1fr_320px]">
        <section className="surface p-5">
          <h2 className="text-lg font-semibold">Archive</h2>
          <div className="mt-5 divide-y divide-line text-sm">
            {reportsPayload.reports.map((report) => (
              <article key={report.id} className="py-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="text-xs text-paper/45">{report.week}</div>
                    <h3 className="mt-1 font-semibold text-paper">
                      <Link href={`/reports/${report.week}`} className="hover:text-amber">{report.title}</Link>
                    </h3>
                  </div>
                  <span className="chip">{report.status}</span>
                </div>
                <p className="mt-3 leading-6 text-paper/65">{report.summary}</p>
                <div className="mt-4 grid gap-3">
                  {report.indexHighlights.map((highlight) => (
                    <div key={`${report.id}-${highlight.code}`} className="grid gap-2 rounded border border-line px-3 py-2 sm:grid-cols-[90px_1fr_90px_90px]">
                      <span className="font-semibold text-paper">{highlight.code}</span>
                      <span className="text-paper/65">{highlight.headline}</span>
                      <span className={highlight.weeklyReturn >= 0 ? "text-mint" : "text-coral"}>{formatPct(highlight.weeklyReturn)}</span>
                      <span className="text-paper/55">{(highlight.breadth * 100).toFixed(0)}% breadth</span>
                      {highlight.notableEvents?.length ? (
                        <div className="text-xs leading-5 text-paper/45 sm:col-span-4">{highlight.notableEvents.join(" ")}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
                <Link href={`/reports/${report.week}`} className="mt-4 inline-block text-xs font-semibold text-amber hover:text-paper">
                  View report
                </Link>
              </article>
            ))}
            {reportsPayload.reports.length === 0 ? (
              <p className="py-5 leading-6 text-paper/60">
                No market report has been published. Reports will begin after real index data is available and has passed editorial review.
              </p>
            ) : null}
          </div>
        </section>
        <NewsletterSignup enabled={reportsPayload.signupEnabled} provider={reportsPayload.newsletterProvider} />
      </div>
      <RelatedPages definitionId="reports" />
    </div>
  );
}
