import type { JsonLdValue } from "@/lib/structured-data";

export function StructuredData({ value }: { value: JsonLdValue }) {
  const json = JSON.stringify(value).replace(/</g, "\\u003c");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
