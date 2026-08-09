import { notFound } from "next/navigation";
import { getConstituents, getIndex } from "@/lib/data";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export default async function ConstituentsPage({ params, searchParams }: { params: { code: string }; searchParams: { asOf?: string } }) {
  const index = await getIndex(params.code);
  if (!index) notFound();
  const constituents = await getConstituents(params.code);
  const asOf = searchParams.asOf ?? index.history.at(-1)?.value_date ?? index.base_date;
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 border-b border-line pb-5">
        <div className="text-sm text-paper/50">{index.code}</div>
        <h1 className="mt-1 text-3xl font-semibold">Constituents</h1>
        <form className="mt-4 flex max-w-sm items-center gap-3">
          <label htmlFor="asOf" className="text-sm text-paper/60">As of</label>
          <input id="asOf" name="asOf" type="date" defaultValue={asOf} className="surface px-3 py-2 text-sm" />
          <button className="chip bg-amber text-ink" type="submit">Apply</button>
        </form>
      </div>
      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Set</th>
              <th className="px-4 py-3">Variant</th>
              <th className="px-4 py-3">Member since</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3 text-right">Liquidity</th>
              <th className="px-4 py-3 text-right">Ref price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {constituents.map((item) => (
              <tr key={`${item.cm_product_id}-${item.variant_key}`}>
                <td className="px-4 py-3 text-paper">{item.name}</td>
                <td className="px-4 py-3 text-paper/65">{item.set}</td>
                <td className="px-4 py-3 text-paper/65">{item.variant_key}</td>
                <td className="px-4 py-3 text-paper/65">{item.member_since}</td>
                <td className="px-4 py-3"><span className="chip">{item.action}</span></td>
                <td className="px-4 py-3 text-right text-paper/75">{item.liquidity_score.toFixed(3)}</td>
                <td className="px-4 py-3 text-right text-paper/75">EUR {item.ref_price.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
