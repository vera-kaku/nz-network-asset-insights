"""Headline findings, computed from the tables so the numbers on the page always match the data."""

from __future__ import annotations

import pandas as pd


def _pct(x: float) -> str:
    return f"{x:.0f}%"


def headline(
    *,
    cls_latest: pd.DataFrame,
    period: pd.DataFrame,
    rel: pd.DataFrame,
    steps: pd.DataFrame,
    exceptions: pd.DataFrame,
    common_classes: set[str] | None = None,
) -> list[str]:
    out = []
    if not cls_latest.empty:
        top = cls_latest.sort_values("gap_pp", ascending=False).head(3)
        parts = [
            f"{r.asset_class} ({r.poor_pct:.1f}% in H1/H2, {r.replace_5yr_pct:.1f}% planned)"
            for r in top.itertuples()
        ]
        yr = int(cls_latest["disc_yr"].iloc[0])
        out.append(
            f"<b>Renewal plans lag condition in a few asset classes.</b> In the {yr} disclosures the largest "
            f"gaps between assets already in poor condition and the five-year replacement forecast are in "
            f"{'; '.join(parts)}."
        )
    if not period.empty:
        tot = period.groupby("reg_period")[["actual", "forecast"]].sum()
        tot["pct"] = 100 * tot["actual"] / tot["forecast"]
        full = period.groupby("reg_period")["years"].max()
        done = [p for p in tot.index if full[p] >= 5]
        if len(done) >= 2:
            a, b = done[-2], done[-1]
            below = period[(period["reg_period"] == b) & (period["delivery_pct"] < 80)]["edb"].nunique()
            n = period[period["reg_period"] == b]["edb"].nunique()
            out.append(
                f"<b>Renewal spend has met forecast overall.</b> Across all networks, actual asset replacement and "
                f"renewal capex was {_pct(tot.loc[b, 'pct'])} of forecast in {b}, up from "
                f"{_pct(tot.loc[a, 'pct'])} in {a}; {below} of {n} networks spent less than 80% of forecast."
            )
    if not rel.empty:
        s = rel[rel["measure"] == "SAIDI"].groupby(["interruption", "disc_yr"])["value"].median()
        years = sorted(rel["disc_yr"].unique())
        y0, y1 = years[0], years[-1]
        try:
            p0, p1 = s[("planned", y0)], s[("planned", y1)]
            d = s.xs("unplanned, defective equipment", level="interruption")
            out.append(
                f"<b>Planned outage minutes have grown.</b> Median planned SAIDI rose from {p0:.0f} to "
                f"{p1:.0f} minutes between {y0} and {y1}, in line with more work being done on the networks, "
                f"while unplanned SAIDI from defective equipment stayed between {d.min():.0f} and "
                f"{d.max():.0f} minutes."
            )
        except KeyError:
            pass
    if not steps.empty:
        big = steps if common_classes is None else steps[steps["asset_class"].isin(common_classes)]
        big = big.sort_values("national_effect_pp", key=abs, ascending=False)
        big = big.drop_duplicates("edb").head(3)
        if not big.empty:
            ex = "; ".join(
                f"{r.edb} {r.asset_class} went from {r.prev_pct:.0f}% to {r.poor_pct:.0f}% in "
                f"{r.disc_yr}, moving the all-network figure by {r.national_effect_pp:+.1f} points"
                for r in big.itertuples()
            )
            out.append(
                f"<b>Big national movements often come from one network re-grading.</b> {len(steps)} one-year "
                f"moves of 20 points or more were found. For example, {ex}. These are flagged for checking "
                f"rather than read as real deterioration or improvement."
            )
    out.append(
        f"<b>Data checks.</b> {len(exceptions)} network asset class records were left out because their "
        f"condition grades do not add up to 100%."
    )
    return out
