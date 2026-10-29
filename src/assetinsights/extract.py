"""Turn the long-format disclosure rows into tidy tables, one per question."""

from __future__ import annotations

import re

import pandas as pd

from .load import latest_version, match

GRADES = ["h1", "h2", "h3", "h4", "h5", "grade_unknown"]

# Asset categories in the file carry a voltage prefix, e.g. "HV - Zone substation switchgear".
ASSET_GROUPS = [
    ("Subtransmission", r"subtransmission"),
    ("Zone substation", r"zone sub"),
    ("Distribution", r"distribution"),
    ("Low voltage", r"^\s*lv\b|low voltage|street ?light"),
    ("Poles", r"overhead line"),
    ("Secondary systems", r"protection|scada|communication|load control|capacitor"),
]


def asset_group(category: str) -> str:
    for name, pattern in ASSET_GROUPS:
        if re.search(pattern, category or "", flags=re.IGNORECASE):
            return name
    return "Other"


def _schedule_rows(df: pd.DataFrame, pattern: str) -> pd.DataFrame:
    return latest_version(df[match(df["schedule"], pattern)])


def _grade_key(desc: str) -> str:
    d = desc.strip().lower()
    return "grade_unknown" if "unknown" in d else d


def condition(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Schedule 12a: share of each asset class in condition grades H1 (worst) to H5 (as new)."""
    c = cfg["condition"]
    rows = _schedule_rows(df, c["schedule"]).rename(
        columns={c["asset_category_col"]: "asset_category", c["asset_class_col"]: "asset_class"}
    )
    keys = ["edb", "disc_yr", "asset_category", "asset_class"]
    rows = rows[rows["asset_category"] != ""]

    grades = rows[match(rows["description"], c["grade"])].copy()
    grades["grade"] = grades["description"].map(_grade_key)
    wide = grades.pivot_table(index=keys, columns="grade", values="value", aggfunc="first").reset_index()
    for g in GRADES:
        if g not in wide.columns:
            wide[g] = pd.NA
    wide = wide[keys + GRADES]

    extras = {}
    for name, pattern in (("replace_5yr_pct", c["replace_5yr"]), ("data_accuracy", c["data_accuracy"])):
        part = rows[match(rows["description"], pattern)]
        extras[name] = part.groupby(keys)["value"].first().rename(name)
    out = wide.set_index(keys).join(pd.DataFrame(extras)).reset_index()

    # Most disclosures give fractions (0.12), a few give percentages (12). Normalise to percentages.
    num = GRADES + ["replace_5yr_pct", "data_accuracy"]
    out[num] = out[num].astype(float)
    grade_sum = out[GRADES].sum(axis=1, min_count=1)
    frac = grade_sum.le(1.5)
    out.loc[frac, GRADES] = out.loc[frac, GRADES] * 100
    rep_frac = frac & out["replace_5yr_pct"].le(1.0)
    out.loc[rep_frac, "replace_5yr_pct"] = out.loc[rep_frac, "replace_5yr_pct"] * 100

    # Data quality: the grades of a class should add up to 100%. Rows outside the tolerance are kept
    # for the exceptions report but excluded from the analysis; rows inside it are rescaled to 100.
    out["grade_total"] = out[GRADES].sum(axis=1, min_count=1)
    has_h = out[["h1", "h2", "h3", "h4", "h5"]].notna().any(axis=1)
    lo, hi = c.get("total_tolerance", [95, 105])
    all_unknown = out["grade_unknown"].fillna(0).ge(lo) & ~has_h  # every unit reported as grade unknown
    on_h_scale = out["disc_yr"].ge(c.get("h_scale_from", 2019))
    out["valid"] = on_h_scale & (has_h | all_unknown) & out["grade_total"].between(lo, hi)
    out["issue"] = ""
    out.loc[~has_h & ~all_unknown, "issue"] = "no H1-H5 grades (older Grade 1-4 scale or blank)"
    out.loc[has_h & ~out["valid"], "issue"] = "grades do not add up to 100%"
    out.loc[out["grade_total"].fillna(0).eq(0), "issue"] = "no units graded (class not held)"
    ok = out["valid"]
    out.loc[ok, GRADES] = out.loc[ok, GRADES].div(out.loc[ok, "grade_total"], axis=0) * 100
    out["poor_pct"] = out["h1"].fillna(0) + out["h2"].fillna(0)
    out["asset_group"] = out["asset_category"].map(asset_group)
    out["disc_yr"] = out["disc_yr"].astype(int)
    return out.sort_values(keys).reset_index(drop=True)


_YEAR_BUCKET = re.compile(r"(?:^|-\s)\s*(pre[-\s]?)?(\d{4})(?:\s*[-\u2013]\s*(\d{4}))?\s*$", re.IGNORECASE)


def _bucket_mid_year(desc: str) -> float | None:
    m = _YEAR_BUCKET.search(desc or "")
    if not m:
        return None
    start = int(m.group(2))
    if m.group(1):  # "pre-1940"
        return start - 5
    end = int(m.group(3)) if m.group(3) else start
    return (start + end) / 2


def age(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Schedule 9b: quantity and quantity-weighted average age of each asset class."""
    c = cfg["age"]
    rows = _schedule_rows(df, c["schedule"]).rename(
        columns={c["asset_category_col"]: "asset_category", c["asset_class_col"]: "asset_class"}
    )
    keys = ["edb", "disc_yr", "asset_category", "asset_class"]
    rows = rows[rows["asset_category"] != ""]

    qty = rows[match(rows["description"], c["quantity"])].groupby(keys)["value"].first().rename("quantity")
    unknown = (
        rows[match(rows["description"], c["age_unknown"])]
        .groupby(keys)["value"]
        .first()
        .rename("age_unknown")
    )

    buckets = rows.assign(mid=rows["description"].map(_bucket_mid_year)).dropna(subset=["mid", "value"])
    buckets = buckets[buckets["value"] > 0]
    buckets["age"] = buckets["disc_yr"] - buckets["mid"]
    buckets["w_age"] = buckets["age"] * buckets["value"]
    buckets["over_40"] = buckets["value"].where(buckets["age"] >= 40, 0)
    agg = buckets.groupby(keys).agg(
        dated=("value", "sum"), w_age=("w_age", "sum"), over_40=("over_40", "sum")
    )
    agg["avg_age"] = agg["w_age"] / agg["dated"]
    agg["over_40_pct"] = 100 * agg["over_40"] / agg["dated"]

    out = pd.concat([qty, unknown, agg[["dated", "avg_age", "over_40_pct"]]], axis=1).reset_index()
    out["asset_group"] = out["asset_category"].map(asset_group)
    out["disc_yr"] = out["disc_yr"].astype(int)
    return out.sort_values(keys).reset_index(drop=True)


def delivery(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Schedule 7: forecast (from the earlier asset management plan) against actual spend.

    In the file, `sub_category` holds Forecast / Actual / Variance and `description` holds the
    expenditure line, e.g. "Asset replacement and renewal".
    """
    c = cfg["delivery"]
    rows = _schedule_rows(df, c["schedule"])
    rows = rows.assign(measure=rows[c["measure_col"]].str.strip().str.lower())
    rows = rows[rows["measure"].isin(["forecast", "actual"])]
    rows["spend_type"] = (
        pd.Series("other", index=rows.index)
        .mask(match(rows["section"], c["opex_section"]), "opex")
        .mask(match(rows["section"], c["capex_section"]), "capex")
    )
    rows = rows[rows["spend_type"] != "other"].rename(columns={c["item_col"]: "item"})
    keys = ["edb", "disc_yr", "spend_type", "item"]
    out = rows.pivot_table(index=keys, columns="measure", values="value", aggfunc="first").reset_index()
    for col in ("forecast", "actual"):
        if col not in out.columns:
            out[col] = pd.NA
    out = out.dropna(subset=["forecast", "actual"]).rename(columns={"item": "category"})
    out = out[out["forecast"] != 0].copy()
    out["variance_pct"] = 100 * (out["actual"] - out["forecast"]) / out["forecast"].abs()
    out["is_total"] = match(out["category"], c["total_items"])
    out["disc_yr"] = out["disc_yr"].astype(int)
    out["reg_period"] = out["disc_yr"].map(regulatory_period)
    return out.sort_values(["edb", "disc_yr", "spend_type", "category"]).reset_index(drop=True)


def regulatory_period(disc_yr: int) -> str:
    """Default price-quality path periods. Disclosure years end on 31 March."""
    if disc_yr <= 2015:
        return "DPP1 (2011-2015)"
    if disc_yr <= 2020:
        return "DPP2 (2016-2020)"
    if disc_yr <= 2025:
        return "DPP3 (2021-2025)"
    return "DPP4 (2026-2030)"


def reliability(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Schedule 10: SAIDI (minutes) and SAIFI (interruptions per customer) by class, plus the
    unplanned SAIDI caused by defective equipment, which is the part most tied to asset condition.
    """
    c = cfg["reliability"]
    rows = _schedule_rows(df, c["schedule"])
    measure = rows["sub_category"].str.strip().str.upper()
    rows = rows[measure.isin(["SAIDI", "SAIFI"])].assign(measure=measure)

    by_class = rows[match(rows["category"], c["by_class"])]
    planned = match(by_class["description"], c["planned"])
    unplanned = match(by_class["description"], c["unplanned"])
    by_class = pd.concat(
        [
            by_class[planned].assign(interruption="planned"),
            by_class[unplanned].assign(interruption="unplanned"),
        ]
    )
    cause = rows[match(rows["category"], c["cause_category"]) & match(rows["description"], c["asset_cause"])]
    cause = cause.assign(interruption="unplanned, defective equipment")

    keys = ["edb", "disc_yr", "measure", "interruption"]
    out = pd.concat([by_class, cause]).dropna(subset=["value"]).groupby(keys)["value"].first().reset_index()
    out["disc_yr"] = out["disc_yr"].astype(int)
    return out.sort_values(keys).reset_index(drop=True)
