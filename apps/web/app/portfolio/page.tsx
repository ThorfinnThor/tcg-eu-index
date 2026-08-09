import { getIndexes } from "@/lib/data";

export default async function PortfolioPage() {
  const indexes = await getIndexes();
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Portfolio benchmark</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
        Upload holdings with `cm_product_id,variant_key,quantity,cost_basis_eur`. Unmatched IDs are reported and never silently dropped.
      </p>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="surface p-5">
          <textarea
            className="surface min-h-72 w-full p-3 font-mono text-sm text-paper"
            defaultValue={"cm_product_id,variant_key,quantity,cost_basis_eur\n750123,nonfoil,3,12.50"}
          />
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="rounded bg-amber px-4 py-2 text-sm font-semibold text-ink" type="button">Preview</button>
            <button className="rounded border border-line px-4 py-2 text-sm text-paper" type="button">Save holdings</button>
          </div>
        </section>
        <aside className="surface p-5">
          <h2 className="text-lg font-semibold">Comparison</h2>
          <select className="surface mt-4 w-full px-3 py-2 text-sm">
            {indexes.map((index) => (
              <option key={index.code}>{index.code}</option>
            ))}
          </select>
          <div className="mt-6 space-y-4 text-sm">
            <div className="flex justify-between"><span>Your collection</span><span className="text-mint">+14.2%</span></div>
            <div className="flex justify-between"><span>Benchmark</span><span className="text-mint">+8.1%</span></div>
            <div className="flex justify-between"><span>Relative</span><span className="text-amber">+6.1 pp</span></div>
          </div>
        </aside>
      </div>
    </div>
  );
}
