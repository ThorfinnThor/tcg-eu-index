import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { IndexChartExplorer } from "@/components/IndexChart";
import { Metric, formatPct } from "@/components/Metric";
import { RelatedPages } from "@/components/RelatedPages";
import { StructuredData } from "@/components/StructuredData";
import { changes, getIndex, getReadiness, postInceptionHistory } from "@/lib/data";
import { calculateIndexAnalytics } from "@/lib/index-analytics";
import { pageMetadata } from "@/lib/seo";
import { getSiteUrl } from "@/lib/site";
import { breadcrumbStructuredData, indexDatasetStructuredData } from "@/lib/structured-data";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export async function generateMetadata(props: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const params = await props.params;
  const index = await getIndex(params.code);
  if (!index) return { title: "Index not found" };
  return pageMetadata(
    `${index.code.toLowerCase()}-index`,
    index.name,
    ["preview", "published"].includes(index.status)
      ? `${index.name} tracks ${index.game} ${index.universe} listing prices in Europe with transparent methodology and daily history.`
      : `${index.name} is collecting Cardmarket history before its first public index composition and value are released.`
  );
}

export default async function IndexPage(props: { params: Promise<{ code: string }> }) {
  const params = await props.params;
  const [index, readiness] = await Promise.all([getIndex(params.code), getReadiness()]);
  if (!index) notFound();
  const indexReadiness = readiness.indexes.find((item) => item.code === index.code);
  const siteUrl = getSiteUrl();
  const breadcrumbs = [{ label: "Overview", href: "/" }, { label: index.name }];
  const visible = ["preview", "published"].includes(index.status) && index.history.length > 0;
  const preview = index.status === "preview";
  const memberLabel = index.universe === "sealed" ? "products" : "cards";

  if (!visible) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <StructuredData value={breadcrumbStructuredData(siteUrl, breadcrumbs)} />
        <Breadcrumbs items={breadcrumbs} />
        <div className="border-b border-line pb-5">
          <div className="text-sm text-paper/50">{index.code}</div>
          <h1 className="mt-1 text-3xl font-semibold text-paper">{index.name}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
            Cardmarket history is being collected. No public index level, return, constituent list, breadth, or volatility figure has been published yet.
          </p>
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-paper/55">
            <span className="chip border-amber text-amber">collecting data</span>
            <span className="chip">target {index.target_size} {memberLabel}</span>
            <span className="chip">all Cardmarket Europe languages</span>
          </div>
        </div>
        <section className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="surface p-5 md:col-span-2">
            <h2 className="text-lg font-semibold">Publication pending</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-paper/60">
              The first real composition is calculated only after the 60-day observation window and quality gates are complete. A human review is required before those results replace this pending state.
            </p>
          </div>
          <div className="surface p-5">
            <div className="text-xs uppercase text-paper/45">Archive readiness</div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">
              {indexReadiness?.availableArchiveDays ?? "Pending"}
              {indexReadiness ? ` / ${indexReadiness.requiredLookbackDays} days` : ""}
            </div>
            <div className="mt-2 text-xs text-paper/45">
              {indexReadiness?.daysRemaining == null
                ? "Waiting for the next daily readiness receipt."
                : `${indexReadiness.daysRemaining} archive days still required.`}
            </div>
            <Link className="mt-5 inline-block text-sm font-semibold text-amber hover:text-paper" href={`/index/${index.code}/constituents`}>
              Constituent status
            </Link>
          </div>
        </section>
        <RelatedPages definitionId={`${index.code.toLowerCase()}-index`} />
      </div>
    );
  }

  const delta = changes(index);
  const latest = index.history.at(-1);
  const formalHistory = postInceptionHistory(index);
  const analytics = calculateIndexAnalytics(formalHistory);
  const validationObservations = index.history.length - formalHistory.length;
  const description = preview
    ? `${index.name} is a provisional Cardmarket-derived preview index during its 60-day observation phase.`
    : `${index.name} tracks ${index.game} ${index.universe} listing prices in Europe with transparent methodology and daily history.`;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <StructuredData value={[
        breadcrumbStructuredData(siteUrl, breadcrumbs),
        indexDatasetStructuredData({
          siteUrl,
          code: index.code,
          name: index.name,
          description,
          startDate: index.base_date,
          endDate: latest?.value_date ?? null
        })
      ]} />
      <Breadcrumbs items={breadcrumbs} />
      {preview ? (
        <section className="mb-6 border-l-2 border-amber bg-amber/[0.07] px-5 py-4" role="status">
          <div className="text-sm font-semibold text-amber">Preview index · not official</div>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-paper/70">
            Provisional index based on the Cardmarket history available so far. Composition and index values may change materially during the 60-day observation period. This is not the official index and is not investment advice.
          </p>
          <p className="mt-2 text-xs leading-5 text-paper/50">
            Preview observations remain labelled as a preparation phase and will not be silently merged into the official history after cutover.
          </p>
        </section>
      ) : null}
      <div className="mb-6 flex flex-col gap-4 border-b border-line pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-sm text-paper/50">{index.code}</div>
          <h1 className="mt-1 text-3xl font-semibold text-paper">{index.name}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-paper/60">
            Chain-linked equal-weight index on a listing-price basis, currently {index.status}. {preview
              ? `Preview history begins ${index.history_start_date}; the official base date and history remain separate.`
              : `Official history begins ${index.history_start_date}.`}
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-paper/50">
            <span className="chip">Repo-managed MVP data</span>
            <span className="chip">Latest calculation {latest?.value_date ?? "pending"}</span>
            <span className="chip">All Cardmarket Europe languages</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="chip hover:border-amber" href={`/index/${index.code}/constituents`}>Constituents</Link>
          <Link className="chip hover:border-amber" href="/methodology">Methodology</Link>
          <a className="chip hover:border-amber" href={`/api/public/${index.code}/history.csv`} download>CSV</a>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="surface p-4">
          <IndexChartExplorer history={index.history} baseDate={index.base_date} />
        </div>
        <aside className="surface p-4">
          <div className="grid grid-cols-2 gap-5">
            <Metric label="Latest" value={latest?.index_value.toFixed(2) ?? "pending"} />
            <Metric label="1d" value={formatPct(delta.d1)} tone={delta.d1 >= 0 ? "up" : "down"} />
            <Metric label="7d" value={formatPct(delta.d7)} tone={delta.d7 >= 0 ? "up" : "down"} />
            <Metric label="30d" value={formatPct(delta.d30)} tone={delta.d30 >= 0 ? "up" : "down"} />
            <Metric label="Breadth" value={`${(index.breadth * 100).toFixed(0)}%`} />
            <Metric label="Vol 30d" value={`${(index.volatility_30d * 100).toFixed(0)}%`} />
          </div>
        </aside>
      </section>
      {index.status === "published" && index.preview_history?.length ? (
        <section className="surface mt-4 p-4">
          <h2 className="text-lg font-semibold">Preview preparation phase</h2>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-paper/50">
            This separately stored series shows the provisional observation phase before official cutover. It is labelled preview data and is not part of the official performance history above.
          </p>
          <div className="mt-4">
            <IndexChartExplorer history={index.preview_history} baseDate={index.preview_history[0].value_date} />
          </div>
        </section>
      ) : null}

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="surface p-4">
          <h2 className="text-lg font-semibold">{preview ? "Preview analytics" : "Post-inception analytics"}</h2>
          <p className="mt-2 text-xs leading-5 text-paper/45">
            Calculated from {analytics.startDate} through {analytics.endDate}. {preview
              ? "These figures use only the labelled preview phase and remain provisional."
              : "Pre-inception validation values and executed transactions are excluded."}
          </p>
          <div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3">
            <Metric label="Period return" value={formatPct(analytics.periodReturn)} tone={analytics.periodReturn >= 0 ? "up" : "down"} />
            <Metric label="Max drawdown" value={formatPct(analytics.maxDrawdown)} tone="down" />
            <Metric label="Positive days" value={`${(analytics.positiveDayRatio * 100).toFixed(0)}%`} />
            <Metric label="Best day" value={formatPct(analytics.bestDay?.daily_return ?? 0)} tone="up" />
            <Metric label="Worst day" value={formatPct(analytics.worstDay?.daily_return ?? 0)} tone="down" />
            <Metric label="Volatility 30d" value={`${(analytics.annualizedVolatility30d * 100).toFixed(1)}%`} />
          </div>
        </div>
        <div className="surface p-4">
          <h2 className="text-lg font-semibold">Calculation coverage</h2>
          <div className="mt-4 divide-y divide-line text-sm">
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">{preview ? "Preview observations" : "Post-inception observations"}</span>
              <span>{analytics.observationCount}</span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">{preview ? "Days until official review" : "Validation observations"}</span>
              <span>{preview ? indexReadiness?.daysRemaining ?? "pending" : validationObservations}</span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">Days with caps</span>
              <span>{analytics.cappedDays}</span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">Days with carried values</span>
              <span>{analytics.carriedForwardDays}</span>
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <h3 className="text-sm font-semibold text-paper">Per-card movers and contributions</h3>
            <p className="mt-2 text-xs leading-5 text-paper/50">
              Unavailable in the JSON-only MVP because the repository does not yet contain per-constituent daily return series. No synthetic rankings are displayed.
            </p>
          </div>
        </div>
      </section>
      <RelatedPages definitionId={`${index.code.toLowerCase()}-index`} />
    </div>
  );
}
