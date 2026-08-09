import { readFile } from "node:fs/promises";
import path from "node:path";

export const revalidate = 3600;

export default async function MethodologyPage() {
  const markdown = await readFile(path.join(process.cwd(), "../../docs/methodology/v1.0.0.md"), "utf8").catch(
    () => "# Methodology\n\nMethodology document will be available after build packaging."
  );
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Methodology</h1>
      <article className="surface prose prose-invert mt-6 max-w-none p-5">
        <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-paper/75">{markdown}</pre>
      </article>
    </div>
  );
}
