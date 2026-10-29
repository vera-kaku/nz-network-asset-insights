"""Portfolio views built on the tidy tables: asset health, renewal coverage, delivery and early warnings."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


def _weighted(df: pd.DataFrame, value: str, weight: str) -> float:
    d = df.dropna(subset=[value])
    w = d[weight].fillna(0)
    if w.sum() > 0:
        return float(np.average(d[value], weights=w))
    return float(d[value].mean()) if len(d) else float("nan")


def attach_quantity(cond: pd.DataFrame, age: pd.DataFrame) -> pd.DataFrame:
    """Add the asset class quantity from the age profile (same year, else the latest earlier year)."""
    if age.empty:
        return cond.assign(quantity=np.nan)
    q = age[["edb", "asset_category", "asset_class", "disc_yr", "quantity"]].dropna(subset=["quantity"])
    q = q.rename(columns={"disc_yr": "qty_yr"}).sort_values("qty_yr")
    left = cond.sort_values("disc_yr")
    merged = pd.merge_asof(
        left,
        q,
        left_on="disc_yr",
        right_on="qty_yr",
        by=["edb", "asset_category", "asset_class"],
        direction="backward",
    )
    return merged.drop(columns=["qty_yr"])


def health_trend(cond: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Quantity-weighted share of assets in H1 or H2 for each year and grouping."""
    rows = []
    for key, g in cond.groupby(["disc_yr"] + by):
        key = key if isinstance(key, tuple) else (key,)
        rows.append(
            dict(
                zip(["disc_yr"] + by, key, strict=True),
                poor_pct=_weighted(g, "poor_pct", "quantity"),
                replace_5yr_pct=_weighted(g, "replace_5yr_pct", "quantity"),
                unknown_pct=_weighted(g, "grade_unknown", "quantity"),
                edbs=g["edb"].nunique(),
                asset_classes=len(g),
            )
        )
    return pd.DataFrame(rows)


def consequence_weight(category: str, cfg: dict) -> float:
    w = cfg["consequence_weights"]
    for pattern, value in w["patterns"].items():
        if re.search(pattern, category or "", flags=re.IGNORECASE):
            return float(value)
    return float(w["default"])


def coverage(cond: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Latest disclosure per network and asset class: poor share against planned 5-year replacement.

    coverage_gap_pp > 0 means more of the class is already in H1/H2 than the network plans to
    replace in the next five years.
    """
    look = cfg["flags"]["lookback_years"]
    latest = cond.loc[cond.groupby("edb")["disc_yr"].transform("max") == cond["disc_yr"]].copy()
    prior = cond[["edb", "asset_category", "asset_class", "disc_yr", "poor_pct"]].rename(
        columns={"poor_pct": "poor_pct_prior", "disc_yr": "prior_yr"}
    )
    latest["prior_yr"] = latest["disc_yr"] - look
    latest = latest.merge(prior, on=["edb", "asset_category", "asset_class", "prior_yr"], how="left")
    latest["poor_change_pp"] = latest["poor_pct"] - latest["poor_pct_prior"]
    latest["coverage_gap_pp"] = latest["poor_pct"] - latest["replace_5yr_pct"]
    latest["weight"] = latest["asset_category"].map(lambda c: consequence_weight(c, cfg))
    # Very small holdings (a handful of units) swing between 0% and 100% and are not ranked.
    small = latest["quantity"].lt(cfg["flags"].get("min_quantity", 0))
    gap = latest["coverage_gap_pp"].clip(lower=0).mask(small, 0)
    latest["priority_score"] = gap * latest["weight"]
    latest["priority_rank"] = latest["priority_score"].rank(ascending=False, method="min")
    latest["unweighted_rank"] = gap.rank(ascending=False, method="min")
    return latest.sort_values("priority_score", ascending=False).reset_index(drop=True)


def delivery_by_period(dlv: pd.DataFrame, category_pattern: str) -> pd.DataFrame:
    """Actual over forecast spend, summed over each regulatory period, for one expenditure category."""
    sub = dlv[dlv["category"].str.contains(category_pattern, case=False, regex=True, na=False)]
    sub = sub[sub["spend_type"] == "capex"]
    g = sub.groupby(["edb", "reg_period"]).agg(
        forecast=("forecast", "sum"), actual=("actual", "sum"), years=("disc_yr", "nunique")
    )
    g["delivery_pct"] = 100 * g["actual"] / g["forecast"]
    return g.reset_index()


def step_changes(cond: pd.DataFrame, threshold_pp: float, min_quantity: float = 0) -> pd.DataFrame:
    """Year-on-year jumps in a network's H1/H2 share for one asset class.

    A move of 20 points or more in a single year is more often a change in how assets were assessed
    than real deterioration, so it is reported for checking rather than read as a trend.
    """
    d = cond.sort_values("disc_yr")[
        ["edb", "asset_category", "asset_class", "disc_yr", "poor_pct", "quantity"]
    ]
    d = d.assign(
        prev_yr=d.groupby(["edb", "asset_class"])["disc_yr"].shift(),
        prev_pct=d.groupby(["edb", "asset_class"])["poor_pct"].shift(),
    )
    total_q = cond.groupby(["asset_class", "disc_yr"])["quantity"].sum().rename("class_quantity")
    d = d.join(total_q, on=["asset_class", "disc_yr"])
    d = d[d["prev_yr"] == d["disc_yr"] - 1]
    d["change_pp"] = d["poor_pct"] - d["prev_pct"]
    # how far this one network moved the all-network figure for the class
    d["national_effect_pp"] = d["change_pp"] * d["quantity"] / d["class_quantity"]
    out = d[(d["change_pp"].abs() >= threshold_pp) & ~d["quantity"].lt(min_quantity)].copy()
    out["prev_yr"] = out["prev_yr"].astype(int)
    return out.sort_values("national_effect_pp", key=abs, ascending=False).reset_index(drop=True)


def early_warnings(
    cov: pd.DataFrame, dlv: pd.DataFrame, cfg: dict, steps: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Rule-based flags. Each row says what was seen, the threshold, and where."""
    f = cfg["flags"]
    flags = []
    min_q = f.get("min_quantity", 0)
    for r in cov.itertuples():
        asset = f"{r.asset_category} / {r.asset_class}"
        if pd.notna(r.quantity) and r.quantity < min_q:
            continue
        if pd.notna(r.coverage_gap_pp) and r.coverage_gap_pp >= f["coverage_gap_pp"]:
            flags.append(
                dict(
                    edb=r.edb,
                    disc_yr=r.disc_yr,
                    flag="Renewal coverage gap",
                    subject=asset,
                    value=round(r.coverage_gap_pp, 1),
                    detail=f"{r.poor_pct:.1f}% in H1/H2 vs {r.replace_5yr_pct:.1f}% planned "
                    "for replacement in 5 years",
                )
            )
        if pd.notna(r.poor_change_pp) and r.poor_change_pp >= f["rising_poor_share_pp"]:
            flags.append(
                dict(
                    edb=r.edb,
                    disc_yr=r.disc_yr,
                    flag="Condition deteriorating",
                    subject=asset,
                    value=round(r.poor_change_pp, 1),
                    detail=f"H1/H2 share up {r.poor_change_pp:.1f} points over {f['lookback_years']} years",
                )
            )
    if not dlv.empty:
        latest_yr = dlv.groupby("edb")["disc_yr"].transform("max")
        recent = dlv[
            (dlv["disc_yr"] == latest_yr)
            & (~dlv["is_total"])
            & (dlv["spend_type"] == "capex")
            & (dlv["forecast"].abs() >= f.get("delivery_min_forecast_k", 0))
        ]
        band = f["delivery_variance_pct"]
        for r in recent[recent["variance_pct"].abs() >= band].itertuples():
            direction = "under" if r.variance_pct < 0 else "over"
            flags.append(
                dict(
                    edb=r.edb,
                    disc_yr=r.disc_yr,
                    flag=f"Capex {direction}-delivery",
                    subject=r.category,
                    value=round(r.variance_pct, 1),
                    detail=f"actual ${r.actual:,.0f}k vs forecast ${r.forecast:,.0f}k",
                )
            )
    if steps is not None and not steps.empty:
        latest_cond = cov.groupby("edb")["disc_yr"].max()
        for r in steps.itertuples():
            if r.disc_yr != latest_cond.get(r.edb):
                continue
            flags.append(
                dict(
                    edb=r.edb,
                    disc_yr=r.disc_yr,
                    flag="Step change in grading",
                    subject=f"{r.asset_category} / {r.asset_class}",
                    value=round(r.change_pp, 1),
                    detail=f"H1/H2 share {r.prev_pct:.1f}% to {r.poor_pct:.1f}% in one year, "
                    "check assessment method",
                )
            )
    cols = ["edb", "disc_yr", "flag", "subject", "value", "detail"]
    out = pd.DataFrame(flags, columns=cols)
    order = {"Renewal coverage gap": 0, "Condition deteriorating": 1, "Step change in grading": 2}
    out["order"] = out["flag"].map(order).fillna(3)
    out["abs"] = out["value"].abs()
    out = out.sort_values(["order", "abs"], ascending=[True, False]).drop(columns=["order", "abs"])
    return out.reset_index(drop=True)
