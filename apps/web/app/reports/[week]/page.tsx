import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { formatPct } from "@/components/Metric";
import { getReport, getReports } from "@/lib/data";
import { reportPageMetadata } from "@/lib/seo";

export const revalidate = 3600;
export const dynamicParams = false;

export async function generateStaticParams() {
  const reports = await getReports();
  return reports.reports.map((report) => ({ week: report.week }));
}

export async function generateMetadata({ params }: { params: { week: string } }): Promise<Metadata> {
  const report = await getReport(params.week);
  if (!report) return { title: "Report not found" };
  return reportPageMetadata(`reports/${report.week}`, report.title, report.summary);
}

export default async function ReportPage({ params }: { params: { week: string } }) {
  const report = await getReport(params.week);
  if (!report) notFound();

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Breadcrumbs items={[
        { label: "Overview", href: "/" },
        { label: "Weekly reports", href: "/reports" },
        { label: report.week }
      ]} />
      <div className="border-b border-line pb-6">
        <Link href="/reports" className="text-sm text-paper/50 hover:text-paper">Weekly reports</Link>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="chip">{report.week}</span>
          <span className={`chip ${report.status === "published" ? "border-teal text-teal" : "border-amber text-amber"}`}>
            {report.status}
          </span>
        </div>
        <h1 className="mt-3 text-3xl font-semibold">{report.title}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">{report.summary}</p>
        {report.status === "draft" ? (
          <p className="mt-3 text-xs leading-5 text-amber">Draft report. Figures are generated, but editorial review has not been completed.</p>
        ) : null}
      </div>

      <div className="mt-6 grid gap-4">
        {report.indexHighlights.map((highlight) => (
          <article key={`${report.id}-${highlight.code}`} className="surface p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <Link href={`/index/${highlight.code}`} className="text-sm font-semibold text-amber hover:text-paper">
                  {highlight.code}
                </Link>
                <h2 className="mt-1 text-xl font-semibold">{highlight.headline}</h2>
              </div>
              <span className={`text-xl font-semibold ${highlight.weeklyReturn >= 0 ? "text-mint" : "text-coral"}`}>
                {formatPct(highlight.weeklyReturn)}
              </span>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-4 border-y border-line py-4 sm:grid-cols-4">
              <div>
                <div className="text-xs text-paper/45">Breadth</div>
                <div className="mt-1 font-semibold">{(highlight.breadth * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div className="text-xs text-paper/45">Start value</div>
                <div className="mt-1 font-semibold">{highlight.startValue?.toFixed(2) ?? "unavailable"}</div>
              </div>
              <div>
                <div className="text-xs text-paper/45">End value</div>
                <div className="mt-1 font-semibold">{highlight.endValue?.toFixed(2) ?? "unavailable"}</div>
              </div>
              <div>
                <div className="text-xs text-paper/45">Observations</div>
                <div className="mt-1 font-semibold">{highlight.observations ?? "unavailable"}</div>
              </div>
            </div>
            {highlight.chartPath ? (
              <Image
                className="mt-5 h-auto w-full border border-line"
                src={highlight.chartPath}
                alt={`${highlight.code} weekly index chart`}
                width={1200}
                height={630}
              />
            ) : null}
            {highlight.notableEvents?.length ? (
              <div className="mt-4">
                <h3 className="text-sm font-semibold">Notable events</h3>
                <ul className="mt-2 space-y-2 text-sm leading-6 text-paper/60">
                  {highlight.notableEvents.map((event) => <li key={event}>{event}</li>)}
                </ul>
              </div>
            ) : null}
          </article>
        ))}
      </div>

      <section className="surface mt-6 p-5">
        <h2 className="text-lg font-semibold">Report notes</h2>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-paper/60">
          {report.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </section>
    </div>
  );
}
