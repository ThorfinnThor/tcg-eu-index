import { z } from "zod";

export const holdingSchema = z.object({
  cm_product_id: z.coerce.number().int().positive(),
  variant_key: z.string().trim().default("nonfoil"),
  quantity: z.coerce.number().positive(),
  cost_basis_eur: z.coerce.number().optional()
});

export type Holding = z.infer<typeof holdingSchema>;

export function parsePortfolioCsv(csv: string) {
  const lines = csv.trim().split(/\r?\n/).filter(Boolean);
  const [header, ...rows] = lines;
  const columns = header.split(",").map((item) => item.trim());
  return rows.map((line, index) => {
    const values = line.split(",").map((item) => item.trim());
    const record = Object.fromEntries(columns.map((column, columnIndex) => [column, values[columnIndex]]));
    const parsed = holdingSchema.safeParse({
      ...record,
      variant_key: record.variant_key || "nonfoil",
      cost_basis_eur: record.cost_basis_eur || undefined
    });
    if (!parsed.success) {
      return { line: index + 2, ok: false as const, error: parsed.error.issues[0]?.message ?? "Invalid row" };
    }
    return { line: index + 2, ok: true as const, holding: parsed.data };
  });
}
