import { CollectorCompositionTable } from "@/components/CollectorCompositionTable";
import { Metric } from "@/components/Metric";
import {
  collectorGameName,
  collectorThreshold,
  latestCollectorRecord,
  latestCollectorRebalance
} from "@/lib/collector-ui";
import type {
  CollectorCompositionIndex,
  CollectorCompositionPage,
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
  composition: CollectorCompositionIndex;
  compositionPage: CollectorCompositionPage;
};

export function CollectorShadowPanel({
  summary,
  history,
  rebalances,
  composition,
  compositionPage
}: Props) {
  const current = latestCollectorRecord(history);
  const currentBasket = latestCollectorRebalance(rebalances);
  const gameName = collectorGameName(summary.game_key);
  const threshold = collectorThreshold(summary);
  const changeSinceStart = current?.index_value == null
    ? null
    : ((current.index_value / summary.base_value) - 1) * 100;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <section className="mb-6 border-l-2 border-amber bg-amber/[0.07] px-5 py-4" role="status">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip border-amber text-amber">Preview</span>
          <span className="chip">Singles only</span>
          <span className="chip">60-day observation phase</span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold text-paper">{summary.name}</h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-paper/70">
          This preview tracks the combined price movement of {gameName} single-card variants priced from €{threshold}. It is provisional until the observation phase is complete.
        </p>
      </section>

      <section className="surface p-5">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label={`Index value · ${current?.value_date ?? "pending"}`}
            value={current?.index_value?.toFixed(2) ?? "pending"}
          />
          <Metric
            label="Change since start"
            value={changeSinceStart == null ? "pending" : `${changeSinceStart >= 0 ? "+" : ""}${changeSinceStart.toFixed(2)}%`}
            tone={changeSinceStart == null || changeSinceStart === 0
              ? "neutral"
              : changeSinceStart > 0 ? "up" : "down"}
          />
          <Metric
            label="Cards tracked"
            value={currentBasket ? currentBasket.active_count.toLocaleString("en-GB") : "pending"}
          />
          <Metric label="Price rule" value={`From €${threshold}`} />
        </div>
        <p className="mt-5 border-t border-line pt-4 text-xs leading-5 text-paper/50">
          The index started at {summary.base_value.toLocaleString("en-GB")}. Card membership is reviewed monthly; the index value is calculated from the latest daily price data. Cardmarket does not provide transaction counts in this feed, so this preview does not label cards as liquid or illiquid.
        </p>
      </section>

      <section className="surface mt-4 p-5">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Cards in this index</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/55">
              Browse every included card, filter by price range, or search the entire index by card name, set, card number, variant, or Cardmarket ID.
            </p>
          </div>
          <span className="text-xs text-paper/40">{gameName} · Cardmarket Europe</span>
        </div>
        <CollectorCompositionTable
          composition={composition}
          compositionPage={compositionPage}
          gameName={gameName}
        />
      </section>
    </div>
  );
}
