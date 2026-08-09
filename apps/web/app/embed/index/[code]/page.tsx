import { notFound } from "next/navigation";
import { IndexChart } from "@/components/IndexChart";
import { changes, getIndex, getSearchIndex } from "@/lib/data";
import { formatPct } from "@/components/Metric";

export const revalidate = 3600;

export async function generateStaticParams() {
  const indexes = await getSearchIndex();
  return indexes.map((index) => ({ code: index.id }));
}

export default async function EmbedPage({ params }: { params: { code: string } }) {
  const index = await getIndex(params.code);
  if (!index) notFound();
  const delta = changes(index);
  return (
    <div className="min-h-screen bg-ink p-3">
      <div className="surface p-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs text-paper/45">{index.code}</div>
            <h1 className="text-base font-semibold">{index.name}</h1>
          </div>
          <span className={delta.d30 >= 0 ? "text-mint" : "text-coral"}>{formatPct(delta.d30)}</span>
        </div>
        <IndexChart history={index.history.slice(-90)} compact />
      </div>
    </div>
  );
}
