import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { RelatedPages } from "@/components/RelatedPages";
import { getDataQuality, getManifest, getStatus } from "@/lib/data";
import { assessFreshness, freshnessTextClass } from "@/lib/freshness";
import { pageMetadata } from "@/lib/seo";

function statusClass(status: string) {
  if (status === "pass") return "border-teal text-teal";
  if (status === "fail") return "border-coral text-coral";
  if (status === "warn") return "border-amber text-amber";
  return "border-line text-paper/65";
}

export const revalidate = 3600;
export const metadata: Metadata = pageMetadata(
  "data-quality",
  "Data quality",
  "Review freshness, completeness, known gaps, and limitations of the European TCG Index dataset."
);

export default async function DataQualityPage() {
  const [quality, status, manifest] = await Promise.all([getDataQuality(), getStatus(), getManifest()]);
  const freshness = assessFreshness(status.last_snapshot_date);
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Breadcrumbs items={[{ label: "Overview", href: "/" }, { label: "Data quality" }]} />
      <div className="border-b border-line pb-6">
        <p className="text-sm text-amber">Public data contract</p>
        <h1 className="mt-2 text-3xl font-semibold">Data quality</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
          The MVP publishes derived aggregates only. This page shows what the current static dataset covers, which checks pass, and where human review is still pending.
        </p>
      </div>

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="surface p-5">
          <div className="text-xs uppercase text-paper/45">Last snapshot</div>
          <div className="mt-2 text-2xl font-semibold">{status.last_snapshot_date ?? "pending"}</div>
        </div>
        <div className="surface p-5">
          <div className="text-xs uppercase text-paper/45">Freshness</div>
          <div className={`mt-2 text-2xl font-semibold ${freshnessTextClass(freshness.level)}`}>
            {freshness.level}
          </div>
          <div className="mt-1 text-xs text-paper/45">{freshness.label}</div>
        </div>
        <div className="surface p-5">
          <div className="text-xs uppercase text-paper/45">Dataset version</div>
          <div className="mt-2 text-2xl font-semibold">{manifest?.datasetVersion ?? "unknown"}</div>
        </div>
        <div className="surface p-5">
          <div className="text-xs uppercase text-paper/45">Contract completeness</div>
          <div className="mt-2 text-2xl font-semibold">{(quality.datasetCompleteness * 100).toFixed(0)}%</div>
        </div>
      </section>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {quality.limitations.map((item) => (
          <section key={item.title} className="surface p-5">
            <h2 className="text-lg font-semibold">{item.title}</h2>
            <p className="mt-3 text-sm leading-6 text-paper/65">{item.body}</p>
          </section>
        ))}
      </div>

      <section className="surface mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Check</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {quality.checks.map((check) => (
              <tr key={check.id}>
                <td className="px-4 py-3 text-paper">{check.label}</td>
                <td className="px-4 py-3"><span className={`chip ${statusClass(check.status)}`}>{check.status}</span></td>
                <td className="px-4 py-3 text-paper/65">{check.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="surface mt-6 p-5">
        <h2 className="text-lg font-semibold">Archive gaps</h2>
        {quality.gaps.length === 0 ? (
          <p className="mt-3 text-sm text-paper/65">No source gaps are recorded in the MVP dataset.</p>
        ) : (
          <div className="mt-4 divide-y divide-line text-sm">
            {quality.gaps.map((gap) => (
              <div key={`${gap.date}-${gap.reason}`} className="grid gap-2 py-3 md:grid-cols-[140px_120px_1fr]">
                <span>{gap.date}</span>
                <span className="text-paper/60">{gap.game ?? "all games"}</span>
                <span className="text-paper/70">{gap.reason}</span>
              </div>
            ))}
          </div>
        )}
      </section>
      <RelatedPages definitionId="data-quality" />
    </div>
  );
}
