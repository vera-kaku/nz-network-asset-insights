from pathlib import Path

import pandas as pd
import pytest

from assetinsights import extract, metrics, synthetic
from assetinsights.cli import run_pipeline
from assetinsights.load import load_config, load_disclosures


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def df(tmp_path_factory):
    p = tmp_path_factory.mktemp("data") / "synthetic.parquet"
    synthetic.make().to_parquet(p)
    return load_disclosures(p)


@pytest.fixture(scope="module")
def cond(df, cfg):
    c = extract.condition(df, cfg)
    return metrics.attach_quantity(c[c["valid"]].copy(), extract.age(df, cfg))


def test_load_rejects_unrelated_file(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"a": [1]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        load_disclosures(p)


def test_load_keeps_whole_network_rows(tmp_path):
    raw = synthetic.make()
    sub = raw.head(10).assign(network="Sub-network A")
    p = tmp_path / "mixed.parquet"
    pd.concat([raw, sub]).to_parquet(p)
    assert len(load_disclosures(p)) == len(raw)


def test_condition_grades_are_percentages_that_sum_to_100(df, cfg):
    c = extract.condition(df, cfg)
    valid = c[c["valid"]]
    assert valid["edb"].nunique() == 4
    assert valid[extract.GRADES].sum(axis=1).between(99.99, 100.01).all()
    assert (valid["poor_pct"] == valid["h1"] + valid["h2"]).all()
    assert valid["replace_5yr_pct"].max() > 1  # fractions were scaled to percentages


def test_condition_percentage_input_gives_same_result(df, cfg):
    pct = df.copy()
    is_cond = pct["schedule"].str.contains("12a") & ~pct["description"].str.startswith("Data accuracy")
    pct.loc[is_cond, "value"] = pct.loc[is_cond, "value"] * 100
    a = extract.condition(df, cfg)
    b = extract.condition(pct, cfg)
    assert b["poor_pct"].round(6).tolist() == a["poor_pct"].round(6).tolist()


def test_records_that_do_not_add_up_are_excluded(df, cfg):
    c = extract.condition(df, cfg)
    bad = c[~c["valid"]]
    assert len(bad) == 1
    r = bad.iloc[0]
    assert (r["edb"], r["asset_class"], r["disc_yr"]) == ("Network South", "Pole Mounted Transformer", 2022)
    assert r["issue"] == "grades do not add up to 100%"


def test_asset_group_mapping():
    assert extract.asset_group("HV - Zone substation switchgear") == "Zone substation"
    assert extract.asset_group("LV - LV Streetlighting") == "Low voltage"
    assert extract.asset_group("All - SCADA and communications") == "Secondary systems"
    assert extract.asset_group("All - Overhead Line") == "Poles"
    assert extract.asset_group("All - Civils") == "Other"


def test_age_buckets_parse_real_labels():
    assert (
        extract._bucket_mid_year("Number of assets at disclosure year end by installation date - 1990-1999")
        == 1994.5
    )
    assert (
        extract._bucket_mid_year("Number of assets at disclosure year end by installation date - pre-1940")
        == 1935
    )
    assert (
        extract._bucket_mid_year("Number of assets at disclosure year end by installation date - 2013")
        == 2013
    )
    assert extract._bucket_mid_year("Items at end of year (quantity)") is None


def test_age_profile(df, cfg):
    age = extract.age(df, cfg)
    assert (age["quantity"] > 0).all()
    row = age[age["disc_yr"] == 2026].iloc[0]
    assert 25 < row["avg_age"] < 50
    assert 0 < row["over_40_pct"] < 100


def test_regulatory_period():
    assert extract.regulatory_period(2020) == "DPP2 (2016-2020)"
    assert extract.regulatory_period(2021) == "DPP3 (2021-2025)"
    assert extract.regulatory_period(2026) == "DPP4 (2026-2030)"


def test_delivery_splits_capex_and_opex(df, cfg):
    dlv = extract.delivery(df, cfg)
    assert set(dlv["spend_type"]) == {"capex", "opex"}
    renewal = dlv[(dlv["category"] == "Asset replacement and renewal") & (dlv["spend_type"] == "opex")]
    assert (renewal["forecast"] == 3000).all()
    r = dlv.iloc[0]
    assert r["variance_pct"] == pytest.approx(100 * (r["actual"] - r["forecast"]) / r["forecast"])


def test_delivery_by_period_uses_capex_only(df, cfg):
    period = metrics.delivery_by_period(extract.delivery(df, cfg), "^asset replacement and renewal$")
    assert (period["forecast"] % 30000 == 0).all()
    assert period["delivery_pct"].between(60, 110).all()


def test_reliability_split(df, cfg):
    rel = extract.reliability(df, cfg)
    assert set(rel["interruption"]) == {"planned", "unplanned", "unplanned, defective equipment"}
    assert set(rel["measure"]) == {"SAIDI", "SAIFI"}
    assert len(rel) == 4 * 8 * 3 * 2  # networks x years x series x measures


def test_quantity_attached_from_earlier_year(df, cfg):
    c = extract.condition(df, cfg)
    age = extract.age(df, cfg)
    merged = metrics.attach_quantity(c[c["valid"]], age[age["disc_yr"] < 2026])
    assert merged[merged["disc_yr"] == 2026]["quantity"].notna().all()


def test_weighted_trend_uses_quantity():
    d = pd.DataFrame(
        {
            "disc_yr": [2025, 2025],
            "asset_class": ["Wood poles"] * 2,
            "poor_pct": [10.0, 30.0],
            "replace_5yr_pct": [5.0, 5.0],
            "grade_unknown": [0.0, 0.0],
            "quantity": [300, 100],
            "edb": ["A", "B"],
        }
    )
    t = metrics.health_trend(d, ["asset_class"])
    assert t.loc[0, "poor_pct"] == pytest.approx(15.0)


def test_coverage_gap_and_ranking(cond, cfg):
    cov = metrics.coverage(cond, cfg)
    assert (cov["disc_yr"] == 2026).all()
    assert cov["coverage_gap_pp"].round(6).equals((cov["poor_pct"] - cov["replace_5yr_pct"]).round(6))
    top = cov.iloc[0]
    assert top["priority_score"] == pytest.approx(max(top["coverage_gap_pp"], 0) * top["weight"])


def test_step_change_is_found(cond):
    steps = metrics.step_changes(cond, 20)
    hit = steps[(steps["edb"] == "Network East") & (steps["asset_class"] == "Wood poles")]
    assert len(hit) == 1 and hit.iloc[0]["disc_yr"] == 2025
    assert hit.iloc[0]["national_effect_pp"] > 0


def test_early_warning_rules(cond, df, cfg):
    cov = metrics.coverage(cond, cfg)
    steps = metrics.step_changes(cond, 20)
    flags = metrics.early_warnings(cov, extract.delivery(df, cfg), cfg, steps)
    gaps = flags[flags["flag"] == "Renewal coverage gap"]
    assert (gaps["value"] >= cfg["flags"]["coverage_gap_pp"]).all()
    assert "Capex under-delivery" in set(flags["flag"])
    assert flags.iloc[0]["flag"] == "Renewal coverage gap"


def test_full_pipeline_writes_outputs(df, cfg, tmp_path):
    out, docs = tmp_path / "out", tmp_path / "docs"
    summary = run_pipeline(df, cfg, out, docs, "test", synthetic_data=True)
    assert summary["scored"] == 24
    assert summary["exceptions"] == 1
    for name in (
        "dim_network",
        "dim_asset",
        "fact_condition",
        "fact_delivery",
        "priority_latest",
        "grading_step_changes",
        "data_quality_exceptions",
        "dashboard_standalone",
    ):
        assert any(p.stem == name for p in out.iterdir()), name
    page = (docs / "index.html").read_text(encoding="utf-8")
    assert "Synthetic demo data" in page and "cdn.plot.ly" in page
    assert chr(0x2014) not in page  # no long dashes
    fact = pd.read_csv(out / "fact_condition.csv")
    assert fact["asset_key"].notna().all() and fact["edb_key"].notna().all()


def test_packaged_config_has_sources(cfg):
    assert cfg["sources"]["parquet_url"].startswith("https://www.comcom.govt.nz/")
    assert Path(__file__).exists()
