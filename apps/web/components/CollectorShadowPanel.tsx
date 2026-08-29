import { CollectorCompositionTable } from "@/components/CollectorCompositionTable";
import { Metric } from "@/components/Metric";
import {
  collectorDiagnosticSummary,
  collectorGameName,
  collectorThreshold,
  collectorUniverseLabel,
  formatCollectorPct,
  latestCollectorRecord,
  latestCollectorRebalance
} from "@/lib/collector-ui";
import type {
  CollectorDiagnostics,
  CollectorHistory,
  CollectorIndexSummary,
  CollectorRebalances
} from "@/lib/types";

type Props = {
  summary: CollectorIndexSummary;
  history: CollectorHistory;
  rebalances: CollectorRebalances;
  diagnostics: CollectorDiagnostics;
};

export function CollectorShadowPanel({ summary, history, rebalances, diagnostics }: Props) {
  const latest = latestCollectorRecord(history);
  const latestRebalance = latestCollectorRebalance(rebalances);
  const diagnosticSummary = collectorDiagnosticSummary(diagnostics);
  const gameName = collectorGameName(summary.game_key);
  const threshold = collectorThreshold(summary);
  const metadataTotal = summary.product_metadata.constituent_count;
  const metadataRate = (count: number) => metadataTotal ? formatCollectorPct(count / metadataTotal) : "—";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <section className="mb-6 border-l-2 border-amber bg-amber/[0.07] px-5 py-4" role="status">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip border-amber text-amber">Private shadow</span>
          <span className="chip">{summary.methodology_version}</span>
          <span className="chip">Not public</span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold text-paper">{summary.name}</h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-paper/70">
          This is a private v1.5 development series. It is not linked from public navigation, has no public alias, and must not be presented as the official index before the 60-day history, calibration, and human cutover review are complete.
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="surface p-5">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Latest shadow value" value={latest?.index_value?.toFixed(2) ?? "pending"} />
            <Metric label="Eligible variants" value={latestRebalance ? String(latestRebalance.active_count) : "pending"} />
            <Metric label="Last effective date" value={latestRebalance?.effective_date ?? "pending"} />
            <Metric label="Cadence" value="Monthly" />
          </div>
          <div className="mt-5 border-t border-line pt-4 text-xs leading-5 text-paper/50">
            {latest?.value_date ? `Latest observation: ${latest.value_date}. ` : "No daily observation yet. "}
            Membership is frozen between monthly rebalances; crossing the price threshold does not change the basket mid-month.
          </div>
        </div>
        <aside className="surface p-5">
          <div className="text-xs uppercase tracking-normal text-paper/50">Series identity</div>
          <div className="mt-2 break-all font-mono text-xs leading-5 text-paper/70">{summary.series_id}</div>
          <div className="mt-4 space-y-2 text-xs text-paper/50">
            <div className="flex justify-between gap-3"><span>Universe</span><span className="text-paper/75">{collectorUniverseLabel(summary.universe)}</span></div>
            <div className="flex justify-between gap-3"><span>Threshold</span><span className="text-paper/75">AVG30 ≥ €{threshold}</span></div>
            <div className="flex justify-between gap-3"><span>Valuation</span><span className="text-paper/75">AVG30 only</span></div>
            <div className="flex justify-between gap-3"><span>Target size</span><span className="text-paper/75">None</span></div>
            <div className="flex justify-between gap-3"><span>Named cards</span><span className="text-paper/75">{metadataRate(summary.product_metadata.named_count)}</span></div>
            <div className="flex justify-between gap-3"><span>Card numbers</span><span className="text-paper/75">{metadataRate(summary.product_metadata.collector_number_count)}</span></div>
            <div className="flex justify-between gap-3"><span>Artwork</span><span className="text-paper/75">{metadataRate(summary.product_metadata.image_count)}</span></div>
          </div>
        </aside>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="surface p-5">
          <h2 className="text-lg font-semibold">Data Quality Score</h2>
          <p className="mt-2 text-sm leading-6 text-paper/55">
            A diagnostic of archived price completeness, update frequency, and inverse dispersion. It describes source quality; it is not a liquidity score and does not reweight the index.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-5">
            <Metric label="Average score" value={formatCollectorPct(diagnosticSummary.averageQuality)} />
            <Metric label="Diagnostic rows" value={String(diagnosticSummary.count)} />
          </div>
        </div>
        <div className="surface p-5">
          <h2 className="text-lg font-semibold">Trading Activity Proxy</h2>
          <p className="mt-2 text-sm leading-6 text-paper/55">
            Positive AVG1 observations over observable source days. This is a diagnostic signal only: Cardmarket does not expose individual orders or transaction counts, and AVG1 is not an eligibility gate in v1.5.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-5">
            <Metric label="Average positive-day ratio" value={formatCollectorPct(diagnosticSummary.averageActivityRatio)} />
            <Metric label="Rows with activity" value={diagnosticSummary.count ? `${diagnosticSummary.positiveActivityRows}/${diagnosticSummary.count}` : "—"} />
          </div>
        </div>
      </section>

      <section className="surface mt-4 p-5">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Monthly composition</h2>
            <p className="mt-2 text-sm leading-6 text-paper/55">
              Every eligible {summary.universe === "sealed" ? "sealed product" : "single-card variant"} above the threshold is included. There is no ranking, quota, cap, or target count.
            </p>
          </div>
          <span className="text-xs text-paper/40">{gameName} · all Cardmarket Europe languages</span>
        </div>
        <CollectorCompositionTable rebalances={rebalances} gameName={gameName} />
      </section>

      <section className="surface mt-4 p-5">
        <h2 className="text-lg font-semibold">Recent calculation state</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead className="text-left text-paper/50">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3 text-right">Index value</th>
                <th className="px-4 py-3 text-right">Daily return</th>
                <th className="px-4 py-3 text-right">Fresh</th>
                <th className="px-4 py-3 text-right">Carried</th>
                <th className="px-4 py-3 text-right">Suspended</th>
                <th className="px-4 py-3">State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {history.records.slice(-7).reverse().map((record) => (
                <tr key={record.value_date}>
                  <td className="px-4 py-3 text-paper/75">{record.value_date}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/75">{record.index_value?.toFixed(2) ?? "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/60">{formatCollectorPct(record.daily_return)}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/60">{record.fresh_count}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/60">{record.carried_count}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/60">{record.suspended_count}</td>
                  <td className="px-4 py-3 text-paper/55">{record.status === "active" ? "active" : "empty eligible universe"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.records.length === 0 ? <p className="py-5 text-sm text-paper/45">No calculation history is available yet.</p> : null}
        </div>
      </section>
    </div>
  );
}
