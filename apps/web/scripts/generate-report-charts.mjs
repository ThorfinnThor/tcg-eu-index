import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const args = process.argv.slice(2);
const weekPosition = args.indexOf("--week");
const week = weekPosition >= 0 ? args[weekPosition + 1] : null;
if (!week) throw new Error("usage: node scripts/generate-report-charts.mjs --week YYYY-Www");

const reports = JSON.parse(await readFile(path.join(root, "source-data", "reports", "index.json"), "utf8"));
const report = reports.reports.find((item) => item.week === week);
if (!report) throw new Error(`missing report ${week}`);

const outputRoot = path.join(root, "source-data", "report-assets", week);
await mkdir(outputRoot, { recursive: true });
for (const highlight of report.indexHighlights) {
  if (!highlight.chartPath) continue;
  const historyPath = path.join(root, "source-data", "indexes", highlight.code, "history.json");
  const outputPath = path.join(outputRoot, `${highlight.code}.png`);
  const result = spawnSync(
    "uv",
    [
      "run",
      "python",
      "scripts/render_report_chart.py",
      "--history",
      historyPath,
      "--week",
      week,
      "--code",
      highlight.code,
      "--output",
      outputPath
    ],
    { cwd: path.resolve(root, "..", ".."), stdio: "inherit" }
  );
  if (result.status !== 0) throw new Error(`chart generation failed for ${highlight.code}`);
}
