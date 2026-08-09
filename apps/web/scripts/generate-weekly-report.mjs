import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { buildWeeklyReport, reportMarkdown } from "./lib/report-generator.mjs";

const root = process.cwd();
const args = process.argv.slice(2);
const weekPosition = args.indexOf("--week");
const week = weekPosition >= 0 ? args[weekPosition + 1] : null;
if (!week) throw new Error("usage: npm run reports:generate -- --week YYYY-Www");

const sourceRoot = path.join(root, "source-data");
const reportsPath = path.join(sourceRoot, "reports", "index.json");
const indexSource = JSON.parse(await readFile(path.join(sourceRoot, "indexes.json"), "utf8"));
const histories = Object.fromEntries(await Promise.all(indexSource.indexes.map(async (index) => [
  index.code,
  JSON.parse(await readFile(path.join(sourceRoot, "indexes", index.code, "history.json"), "utf8"))
])));
const reportsPayload = JSON.parse(await readFile(reportsPath, "utf8"));
const existing = reportsPayload.reports.find((report) => report.week === week);
if (existing?.status === "published") throw new Error(`${week} is already published and cannot be regenerated`);

const report = buildWeeklyReport(indexSource.indexes, histories, week);
reportsPayload.reports = [report, ...reportsPayload.reports.filter((item) => item.week !== week)]
  .sort((left, right) => right.week.localeCompare(left.week));
await writeFile(reportsPath, `${JSON.stringify(reportsPayload, null, 2)}\n`);

const markdownRoot = path.resolve(root, "..", "..", "docs", "reports");
await mkdir(markdownRoot, { recursive: true });
await writeFile(path.join(markdownRoot, `${week}.md`), reportMarkdown(report));
console.log(`generated draft report ${week}`);
