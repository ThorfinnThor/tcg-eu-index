export function isoWeekBounds(week) {
  const match = /^(\d{4})-W(\d{2})$/.exec(week);
  if (!match) throw new Error("week must use YYYY-Www format");
  const year = Number(match[1]);
  const weekNumber = Number(match[2]);
  if (weekNumber < 1 || weekNumber > 53) throw new Error("ISO week must be between 01 and 53");

  const januaryFourth = new Date(Date.UTC(year, 0, 4));
  const januaryFourthDay = januaryFourth.getUTCDay() || 7;
  const monday = new Date(januaryFourth);
  monday.setUTCDate(januaryFourth.getUTCDate() - januaryFourthDay + 1 + (weekNumber - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return { start: monday.toISOString().slice(0, 10), end: sunday.toISOString().slice(0, 10) };
}

export function weeklyIndexHighlight(index, history, week) {
  const { start, end } = isoWeekBounds(week);
  const eligible = history.filter((row) => row.value_date <= end);
  const inWeek = eligible.filter((row) => row.value_date >= start);
  if (inWeek.length === 0) throw new Error(`${index.code} has no observations in ${week}`);

  const baseline = eligible.filter((row) => row.value_date < start).at(-1) ?? inWeek[0];
  const latest = inWeek.at(-1);
  const weeklyReturn = latest.index_value / baseline.index_value - 1;
  const notableEvents = [];
  const cappedDays = inWeek.filter((row) => (row.n_capped ?? 0) > 0).length;
  const carriedDays = inWeek.filter((row) => (row.n_carried_forward ?? 0) > 0).length;
  if (cappedDays > 0) notableEvents.push(`${cappedDays} day(s) included capped constituents.`);
  if (carriedDays > 0) notableEvents.push(`${carriedDays} day(s) used at least one carried-forward value.`);
  if (notableEvents.length === 0) notableEvents.push("No calculation flags were recorded during the week.");

  const direction = weeklyReturn >= 0 ? "rose" : "fell";
  return {
    code: index.code,
    headline: `${index.name} ${direction} ${Math.abs(weeklyReturn * 100).toFixed(2)}%`,
    weeklyReturn: Number(weeklyReturn.toFixed(8)),
    breadth: index.breadth,
    startValue: baseline.index_value,
    endValue: latest.index_value,
    observations: inWeek.length,
    notableEvents
  };
}

export function buildWeeklyReport(indexes, histories, week) {
  const highlights = indexes.map((index) => weeklyIndexHighlight(index, histories[index.code] ?? [], week));
  return {
    id: `${week}-generated`,
    week,
    title: `European TCG market report - ${week}`,
    status: "draft",
    publishedAt: null,
    summary: `${highlights.length} European TCG benchmarks were calculated from the repository-managed MVP dataset for ${week}.`,
    notes: [
      "Generated figures use repo-managed MVP JSON and are not transaction prices.",
      "Per-product movers remain unavailable until the production Cardmarket-derived data flow is connected.",
      "Editor review is required before this draft can be marked published."
    ],
    indexHighlights: highlights
  };
}

export function reportMarkdown(report) {
  const sections = report.indexHighlights.map((highlight) => [
    `## ${highlight.code}`,
    "",
    highlight.headline,
    "",
    `- Weekly return: ${(highlight.weeklyReturn * 100).toFixed(2)}%`,
    `- Index value: ${highlight.startValue.toFixed(2)} to ${highlight.endValue.toFixed(2)}`,
    `- Breadth: ${(highlight.breadth * 100).toFixed(0)}%`,
    `- Daily observations: ${highlight.observations}`,
    "",
    "Notable events:",
    "",
    ...highlight.notableEvents.map((event) => `- ${event}`),
    "",
    "Top and bottom movers: unavailable in the JSON-only MVP dataset."
  ].join("\n"));

  return [
    `# ${report.title}`,
    "",
    `Status: ${report.status}`,
    "",
    report.summary,
    "",
    ...sections,
    "",
    "## Editor's notes",
    "",
    "<!-- Add reviewed commentary here before publishing. -->",
    ""
  ].join("\n");
}
