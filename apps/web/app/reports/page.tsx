export const revalidate = 3600;

export default function ReportsPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Weekly reports</h1>
      <div className="mt-6 grid gap-4 md:grid-cols-[1fr_320px]">
        <section className="surface p-5">
          <h2 className="text-lg font-semibold">Archive</h2>
          <p className="mt-3 text-sm leading-6 text-paper/65">
            Reports are generated each Monday with benchmark returns, movers, breadth, flagged events, and an editor notes placeholder for human review before publishing.
          </p>
          <div className="mt-5 divide-y divide-line text-sm">
            <div className="flex justify-between py-3">
              <span>First report</span>
              <span className="text-paper/55">pending production snapshots</span>
            </div>
          </div>
        </section>
        <form className="surface p-5">
          <h2 className="text-lg font-semibold">Email signup</h2>
          <input className="surface mt-4 w-full px-3 py-2 text-sm" type="email" placeholder="you@example.com" />
          <button className="mt-3 w-full rounded bg-amber px-3 py-2 text-sm font-semibold text-ink" type="button">Join</button>
        </form>
      </div>
    </div>
  );
}
