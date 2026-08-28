from __future__ import annotations

from typing import Any, Literal

import polars as pl

from indexengine.calc import Rebalance


def build_public_membership_contract(
    index_code: str,
    generated_for: str,
    rebalances: list[Rebalance],
    products: pl.DataFrame,
    sets: pl.DataFrame,
    data_state: Literal["validation", "preview", "published"] = "validation",
    cadence: Literal["monthly", "daily_preview"] = "monthly",
) -> dict[str, object]:
    """Build the small public membership contract without writing or publishing it."""
    product_by_id = {
        int(row["cm_product_id"]): row for row in products.iter_rows(named=True)
    }
    set_by_id = {
        int(row["cm_expansion_id"]): str(row["name"])
        for row in sets.iter_rows(named=True)
        if row.get("cm_expansion_id") is not None
    }
    lifecycle: list[dict[str, Any]] = []
    open_interval: dict[tuple[int, str], int] = {}
    public_rebalances: list[dict[str, object]] = []

    for rebalance in sorted(rebalances, key=lambda item: item.effective_date):
        changes: list[dict[str, object]] = []
        for constituent in rebalance.constituents:
            identity = constituent.identity
            if identity not in open_interval:
                product = product_by_id.get(constituent.cm_product_id, {})
                expansion_id = product.get("cm_expansion_id")
                set_name = (
                    set_by_id.get(int(expansion_id), f"Expansion {expansion_id}")
                    if expansion_id is not None
                    else "Unknown set"
                )
                lifecycle.append(
                    {
                        "cm_product_id": constituent.cm_product_id,
                        "variant_key": constituent.variant_key,
                        "name": str(
                            product.get("name", f"Product {constituent.cm_product_id}")
                        ),
                        "set": set_name,
                        "member_since": rebalance.effective_date,
                        "action": constituent.action,
                        "entry_reason": constituent.reason,
                        "liquidity_score": constituent.liquidity_score,
                        "ref_price": constituent.ref_price,
                    }
                )
                open_interval[identity] = len(lifecycle) - 1
                changes.append(
                    {
                        "cm_product_id": constituent.cm_product_id,
                        "variant_key": constituent.variant_key,
                        "action": "added",
                        "reason": constituent.reason,
                    }
                )

        for removed in rebalance.removed:
            identity = removed.cm_product_id, removed.variant_key
            interval_index = open_interval.pop(identity, None)
            if interval_index is not None:
                lifecycle[interval_index].update(
                    {
                        "removed_at": rebalance.effective_date,
                        "removal_reason": removed.reason,
                        "action": "removed",
                    }
                )
            changes.append(
                {
                    "cm_product_id": removed.cm_product_id,
                    "variant_key": removed.variant_key,
                    "action": "removed",
                    "reason": removed.reason,
                }
            )

        public_rebalances.append(
            {
                "effective_date": rebalance.effective_date,
                "methodology_version": rebalance.methodology_version,
                "selection_snapshot_sha256": rebalance.selection_snapshot_sha256,
                "eligible_count": rebalance.eligible_count,
                "active_count": len(rebalance.constituents),
                "retained_count": sum(
                    item.action == "retained" for item in rebalance.constituents
                ),
                "changes": changes,
            }
        )

    lifecycle.sort(
        key=lambda item: (
            str(item["member_since"]),
            int(item["cm_product_id"]),
            str(item["variant_key"]),
        )
    )
    return {
        "constituents": lifecycle,
        "rebalances": {
            "schema_version": 1,
            "index_code": index_code,
            "data_state": data_state,
            "cadence": cadence,
            "generated_for": generated_for,
            "rebalances": public_rebalances,
        },
    }
