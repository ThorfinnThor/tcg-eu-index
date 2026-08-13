import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { RelatedPages } from "@/components/RelatedPages";
import { getArchiveHealth, getDataQuality, getManifest, getReadiness, getStatus } from "@/lib/data";
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
  const [quality, status, manifest, readiness, archiveHealth] = await Promise.all([
    getDataQuality(),
    getStatus(),
    getManifest(),
    getReadiness(),
    getArchiveHealth()
  ]);
  const freshness = assessFreshness(status.last_snapshot_date);
  const archiveGaps = archiveHealth.generatedFor ? archiveHealth.gaps : quality.gaps;
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
          <div className="text-xs uppercase text-paper/45">Public index data</div>
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

      <section className="mt-6 border-y border-line py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Archive health</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/60">
              Weekly integrity checks publish aggregate coverage and free-tier projections. Private object names and source payloads remain in R2.
            </p>
          </div>
          <span className={`chip ${archiveHealth.status === "healthy" ? "border-teal text-teal" : archiveHealth.status === "attention_required" ? "border-coral text-coral" : "border-amber text-amber"}`}>
            {archiveHealth.status.replaceAll("_", " ")}
          </span>
        </div>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase text-paper/45">Calendar coverage</dt>
            <dd className="mt-1 text-xl font-semibold">
              {archiveHealth.coverageRatio == null ? "pending" : `${(archiveHealth.coverageRatio * 100).toFixed(1)}%`}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-paper/45">Verified files</dt>
            <dd className="mt-1 text-xl font-semibold">{archiveHealth.verifiedFileCount ?? "pending"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-paper/45">R2 storage</dt>
            <dd className="mt-1 text-xl font-semibold">
              {archiveHealth.storage.usageRatio == null ? "pending" : `${(archiveHealth.storage.usageRatio * 100).toFixed(2)}%`}
            </dd>
            <div className="mt-1 text-xs text-paper/45">of free allocation</div>
          </div>
          <div>
            <dt className="text-xs uppercase text-paper/45">Projected monthly rebalance</dt>
            <dd className="mt-1 text-xl font-semibold">{archiveHealth.cutoverProjection.firstMonthlyRebalanceDate ?? "pending"}</dd>
            <div className="mt-1 text-xs text-paper/45">assumes no archive gaps</div>
          </div>
        </dl>
        <div className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
          {([archiveHealth.operations.classA, archiveHealth.operations.classB] as const).map((budget, position) => (
            <div key={position} className="flex items-center justify-between gap-3 border-t border-line pt-3">
              <span className="text-paper/60">Class {position === 0 ? "A" : "B"} operations</span>
              <span>{budget.usageRatio == null ? "pending" : `${(budget.usageRatio * 100).toFixed(2)}% projected`}</span>
            </div>
          ))}
        </div>
      </section>

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

      <section className="surface mt-6 overflow-x-auto">
        <div className="border-b border-line px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Index readiness</h2>
            <span className="text-xs text-paper/45">
              Receipt {readiness.generatedFor ?? "pending"} · Methodology {readiness.methodologyVersion}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/60">
            This surface contains aggregate gate results only. Even a fully eligible index still requires human review before publication.
          </p>
        </div>
        <table className="w-full min-w-[840px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Index</th>
              <th className="px-4 py-3">State</th>
              <th className="px-4 py-3 text-right">Archive</th>
              <th className="px-4 py-3 text-right">Remaining</th>
              <th className="px-4 py-3 text-right">Selection</th>
              <th className="px-4 py-3">Open gates</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {readiness.indexes.map((item) => (
              <tr key={item.code}>
                <td className="px-4 py-3 text-paper">{item.code}</td>
                <td className="px-4 py-3">
                  <span className={`chip ${item.state === "eligible_for_human_review" ? "border-teal text-teal" : "border-amber text-amber"}`}>
                    {item.state.replaceAll("_", " ")}
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {item.availableArchiveDays ?? "pending"} / {item.requiredLookbackDays}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{item.daysRemaining ?? "pending"}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {item.selectedConstituents ?? "pending"} / {item.targetSize}
                </td>
                <td className="px-4 py-3 text-paper/55">
                  {item.blockers.length ? item.blockers.join(", ").replaceAll("_", " ") : "Human review"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="surface mt-6 p-5">
        <h2 className="text-lg font-semibold">Archive gaps</h2>
        {archiveGaps.length === 0 ? (
          <p className="mt-3 text-sm text-paper/65">No source gaps are recorded in the MVP dataset.</p>
        ) : (
          <div className="mt-4 divide-y divide-line text-sm">
            {archiveGaps.map((gap) => (
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
