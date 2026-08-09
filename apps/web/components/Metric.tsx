import clsx from "clsx";

export function formatPct(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

export function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "up" | "down" | "neutral" }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-normal text-paper/50">{label}</div>
      <div
        className={clsx(
          "mt-1 text-lg font-semibold",
          tone === "up" && "text-mint",
          tone === "down" && "text-coral",
          tone === "neutral" && "text-paper"
        )}
      >
        {value}
      </div>
    </div>
  );
}
