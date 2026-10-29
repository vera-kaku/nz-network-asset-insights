"""Export a small star schema that Power BI (or Excel) can load directly."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def export(
    out_dir: Path,
    *,
    cond: pd.DataFrame,
    age: pd.DataFrame,
    dlv: pd.DataFrame,
    rel: pd.DataFrame,
    cov: pd.DataFrame,
    flags: pd.DataFrame,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = (
        pd.concat(
            [
                cond[["asset_category", "asset_class", "asset_group"]],
                age[["asset_category", "asset_class", "asset_group"]],
            ]
        )
        .drop_duplicates()
        .sort_values(["asset_group", "asset_category", "asset_class"])
        .reset_index(drop=True)
    )
    assets.insert(0, "asset_key", range(1, len(assets) + 1))
    edbs = pd.DataFrame({"edb": sorted(set(cond["edb"]) | set(dlv["edb"]) | set(rel["edb"]))})
    edbs.insert(0, "edb_key", range(1, len(edbs) + 1))

    def keyed(df: pd.DataFrame, with_asset: bool = True) -> pd.DataFrame:
        d = df.merge(edbs, on="edb", how="left")
        if with_asset:
            d = d.merge(
                assets[["asset_key", "asset_category", "asset_class"]],
                on=["asset_category", "asset_class"],
                how="left",
            )
        return d

    tables = {
        "dim_network": edbs,
        "dim_asset": assets,
        "fact_condition": keyed(cond)[
            [
                "edb_key",
                "asset_key",
                "disc_yr",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "grade_unknown",
                "poor_pct",
                "replace_5yr_pct",
                "data_accuracy",
                "quantity",
            ]
        ],
        "fact_age": keyed(age)[
            ["edb_key", "asset_key", "disc_yr", "quantity", "age_unknown", "avg_age", "over_40_pct"]
        ],
        "fact_delivery": keyed(dlv, with_asset=False)[
            [
                "edb_key",
                "disc_yr",
                "reg_period",
                "spend_type",
                "category",
                "forecast",
                "actual",
                "variance_pct",
                "is_total",
            ]
        ],
        "fact_reliability": keyed(rel, with_asset=False)[
            ["edb_key", "disc_yr", "measure", "interruption", "value"]
        ],
        "priority_latest": keyed(cov)[
            [
                "edb_key",
                "asset_key",
                "disc_yr",
                "poor_pct",
                "replace_5yr_pct",
                "coverage_gap_pp",
                "poor_change_pp",
                "weight",
                "priority_score",
                "priority_rank",
                "unweighted_rank",
            ]
        ],
        "early_warnings": flags,
    }
    paths = []
    for name, df in tables.items():
        p = out_dir / f"{name}.csv"
        df.to_csv(p, index=False)
        paths.append(p)
    return paths
