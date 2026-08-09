export default function DataQualityPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Data quality</h1>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {[
          ["Listing-price basis", "Benchmarks use Cardmarket daily price guides, not executed transaction prices."],
          ["Carried forward", "Missing constituent observations are carried for up to five days, then suspended until fresh data returns."],
          ["Spike capped", "Daily constituent returns are winsorized at +/-25% and flagged in aggregate counts."],
          ["Archive gaps", "Documented missing source days are never fabricated. The public series discloses gap counts."]
        ].map(([title, body]) => (
          <section key={title} className="surface p-5">
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="mt-3 text-sm leading-6 text-paper/65">{body}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
