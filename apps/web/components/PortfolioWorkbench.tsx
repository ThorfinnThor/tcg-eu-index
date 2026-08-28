"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { formatPct } from "@/components/Metric";
import { buildPortfolioComparison, summarizePortfolio, validatePortfolioCsv } from "@/lib/portfolio";
import type { Constituent, IndexCode, IndexSummary } from "@/lib/types";

type Props = {
  indexes: IndexSummary[];
  constituentsByCode: Record<IndexCode, Constituent[]>;
};

const sampleCsv = "cm_product_id,variant_key,quantity,cost_basis_eur\n750001,nonfoil,3,9.50\n750007,foil,1,10.00\n999999,nonfoil,2,5.00";
const storageKey = "tcg-eu-index:portfolio-preview:v1";

type StoredPortfolio = {
  selectedCode?: string;
  csv?: string;
  basisDate?: string;
};

function subscribeToStorage(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}

function subscribeToHydration() {
  return () => undefined;
}

function getStoredPortfolio() {
  try {
    return window.localStorage.getItem(storageKey);
  } catch {
    return null;
  }
}

function parseStoredPortfolio(value: string | null): StoredPortfolio | null {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object") return null;
    const stored: StoredPortfolio = {};
    if ("selectedCode" in parsed && typeof parsed.selectedCode === "string") stored.selectedCode = parsed.selectedCode;
    if ("csv" in parsed && typeof parsed.csv === "string") stored.csv = parsed.csv;
    if ("basisDate" in parsed && typeof parsed.basisDate === "string") stored.basisDate = parsed.basisDate;
    return stored;
  } catch {
    return null;
  }
}

export function PortfolioWorkbench({ indexes, constituentsByCode }: Props) {
  const storedPayload = useSyncExternalStore(subscribeToStorage, getStoredPortfolio, () => null);
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false);
  const stored = useMemo(() => parseStoredPortfolio(storedPayload), [storedPayload]);
  const defaultCode = indexes[0]?.code ?? "OPEU500";
  const storedCode = stored?.selectedCode && indexes.some((index) => index.code === stored.selectedCode)
    ? stored.selectedCode as IndexCode
    : null;
  const [selectedCodeOverride, setSelectedCode] = useState<IndexCode | null>(null);
  const [csvOverride, setCsv] = useState<string | null>(null);
  const [basisDateOverride, setBasisDate] = useState<string | null>(null);
  const selectedCode = selectedCodeOverride ?? storedCode ?? defaultCode;
  const csv = csvOverride ?? stored?.csv ?? sampleCsv;
  const basisDate = basisDateOverride ?? stored?.basisDate ?? indexes[0]?.history.at(0)?.value_date ?? "";
  const fileInput = useRef<HTMLInputElement>(null);
  const selectedIndex = indexes.find((index) => index.code === selectedCode) ?? indexes[0];
  const constituents = useMemo(() => constituentsByCode[selectedCode] ?? [], [constituentsByCode, selectedCode]);

  const validation = useMemo(() => validatePortfolioCsv(csv, constituents), [csv, constituents]);
  const summary = useMemo(
    () => summarizePortfolio(validation, selectedIndex?.history ?? [], basisDate),
    [validation, selectedIndex, basisDate]
  );
  const series = useMemo(
    () => buildPortfolioComparison(selectedIndex?.history ?? [], validation, basisDate),
    [selectedIndex, validation, basisDate]
  );
  const latest = series.at(-1);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ selectedCode, csv, basisDate }));
    } catch {
      // The preview remains usable when private browsing blocks local storage.
    }
  }, [hydrated, selectedCode, csv, basisDate]);

  function selectBenchmark(code: IndexCode) {
    setSelectedCode(code);
    const index = indexes.find((item) => item.code === code);
    setBasisDate(index?.history.at(0)?.value_date ?? "");
  }

  async function uploadCsv(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
  }

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_360px]">
      <section className="surface min-w-0 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold">CSV holdings</h2>
          <select
            className="surface max-w-full px-3 py-2 text-sm"
            value={selectedCode}
            onChange={(event) => selectBenchmark(event.target.value as IndexCode)}
            aria-label="Benchmark index"
          >
            {indexes.map((index) => (
              <option key={index.code} value={index.code}>{index.code} - {index.name}</option>
            ))}
          </select>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4">
          <div>
            <label className="block text-xs uppercase text-paper/45" htmlFor="portfolio-basis-date">Comparison basis</label>
            <input
              id="portfolio-basis-date"
              className="surface mt-1 px-3 py-2 text-sm"
              type="date"
              min={selectedIndex?.history.at(0)?.value_date}
              max={selectedIndex?.history.at(-1)?.value_date}
              value={basisDate}
              onChange={(event) => setBasisDate(event.target.value)}
            />
          </div>
          <input
            ref={fileInput}
            className="sr-only"
            type="file"
            accept=".csv,text/csv"
            aria-label="Upload portfolio CSV"
            onChange={(event) => void uploadCsv(event.target.files?.[0])}
          />
          <button className="chip hover:border-amber" type="button" onClick={() => fileInput.current?.click()}>
            Upload CSV
          </button>
          <button className="chip hover:border-amber" type="button" onClick={() => setCsv(sampleCsv)}>
            Load example
          </button>
          <span className="text-xs text-paper/45">Saved only in this browser</span>
        </div>
        <textarea
          className="surface mt-4 min-h-72 w-full p-3 font-mono text-sm text-paper"
          value={csv}
          onChange={(event) => setCsv(event.target.value)}
          spellCheck={false}
        />
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="surface p-3">
            <div className="text-xs uppercase text-paper/45">Accepted rows</div>
            <div className="mt-1 text-xl font-semibold">{validation.accepted.length}</div>
          </div>
          <div className="surface p-3">
            <div className="text-xs uppercase text-paper/45">Errors</div>
            <div className="mt-1 text-xl font-semibold">{validation.errors.length}</div>
          </div>
          <div className="surface p-3">
            <div className="text-xs uppercase text-paper/45">Market value</div>
            <div className="mt-1 text-xl font-semibold">EUR {summary.latestMarketValue.toFixed(2)}</div>
          </div>
        </div>

        {validation.errors.length > 0 && (
          <div className="mt-4 rounded border border-coral/60 p-3 text-sm text-coral">
            {validation.errors.map((error) => (
              <div key={`${error.line}-${error.error}`}>Line {error.line}: {error.error}</div>
            ))}
          </div>
        )}

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-sm">
            <thead className="text-left text-paper/50">
              <tr>
                <th className="py-2 pr-3">Product</th>
                <th className="py-2 pr-3">Variant</th>
                <th className="py-2 pr-3 text-right">Qty</th>
                <th className="py-2 pr-3 text-right">Ref price</th>
                <th className="py-2 text-right">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {validation.accepted.map((item) => (
                <tr key={`${item.line}-${item.holding.cm_product_id}-${item.holding.variant_key}`}>
                  <td className="py-2 pr-3 text-paper">{item.constituent.name}</td>
                  <td className="py-2 pr-3 text-paper/65">{item.holding.variant_key}</td>
                  <td className="py-2 pr-3 text-right text-paper/65">{item.holding.quantity}</td>
                  <td className="py-2 pr-3 text-right text-paper/65">EUR {item.constituent.ref_price.toFixed(2)}</td>
                  <td className="py-2 text-right text-paper">EUR {item.market_value_eur.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="surface min-w-0 p-5">
        <h2 className="text-lg font-semibold">Comparison</h2>
        <div className="mt-5 space-y-4 text-sm">
          <div className="flex justify-between gap-3">
            <span>Your collection</span>
            <span className={summary.portfolioReturn === null || summary.portfolioReturn >= 0 ? "text-mint" : "text-coral"}>
              {summary.portfolioReturn === null ? "cost basis needed" : formatPct(summary.portfolioReturn)}
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span>Benchmark</span>
            <span className={summary.benchmarkReturn >= 0 ? "text-mint" : "text-coral"}>{formatPct(summary.benchmarkReturn)}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span>Relative</span>
            <span className="text-amber">{summary.relativePp === null ? "pending" : `${summary.relativePp.toFixed(2)} pp`}</span>
          </div>
        </div>

        <div className="mt-6 h-64">
          {series.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#34342e" vertical={false} />
                <XAxis dataKey="value_date" tickFormatter={(value) => String(value).slice(5)} tick={{ fill: "#a7a195", fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: "#a7a195", fontSize: 12 }} tickLine={false} axisLine={false} width={48} />
                <Tooltip contentStyle={{ background: "#191916", border: "1px solid #34342e", borderRadius: 8 }} labelStyle={{ color: "#f4efe4" }} />
                <Line type="linear" dataKey="benchmark" stroke="#e7b75f" strokeWidth={2} />
                <Line type="linear" dataKey="portfolio" stroke="#4db7ad" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center border-y border-line text-center text-sm leading-6 text-paper/50">
              Valid holdings and cost basis are required for the two-point comparison.
            </div>
          )}
        </div>

        <p className="mt-4 text-xs leading-5 text-paper/50">
          Holdings are validated locally. The chart compares only the selected basis date with the latest value; no daily collection path is invented without daily card-level prices.
        </p>
        {latest && <p className="mt-3 text-xs text-paper/45">Latest relative point: {latest.relative_pp.toFixed(2)} pp</p>}
      </aside>
    </div>
  );
}
