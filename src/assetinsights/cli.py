"""Command line: assets download | profile | build | demo."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import extract, findings, metrics, powerbi, report, synthetic
from .load import download, load_config, load_disclosures, profile

RAW = Path("data/raw/EDB_ID_Full.parquet")


def run_pipeline(
    df: pd.DataFrame, cfg: dict, out: Path, docs: Path, source_note: str, synthetic_data: bool
) -> dict:
    cond_all = extract.condition(df, cfg)
    age = extract.age(df, cfg)
    dlv = extract.delivery(df, cfg)
    rel = extract.reliability(df, cfg)
    cond = cond_all[cond_all["valid"]].copy()
    if cond.empty:
        raise SystemExit(
            "No valid Schedule 12a condition rows. Run `assets profile --schedule 12a` and check config.yaml."
        )
    exceptions = cond_all[cond_all["issue"] == "grades do not add up to 100%"]
    cond = metrics.attach_quantity(cond, age)
    latest_yr = int(cond["disc_yr"].max())

    class_trend = metrics.health_trend(cond, ["asset_class"])
    n_edb = cond["edb"].nunique()
    min_networks = min(15, -(-n_edb // 2))
    cls_latest = class_trend[
        (class_trend["disc_yr"] == latest_yr) & (class_trend["edbs"] >= min_networks)
    ].copy()
    common = set(cls_latest["asset_class"])
    cls_latest["gap_pp"] = cls_latest["poor_pct"] - cls_latest["replace_5yr_pct"]
    cls_latest = cls_latest.sort_values("gap_pp", ascending=False).head(12)

    cov = metrics.coverage(cond, cfg)
    steps = metrics.step_changes(cond, cfg["flags"]["step_change_pp"], cfg["flags"].get("min_quantity", 0))
    latest_steps = steps.merge(cov[["edb", "disc_yr"]].drop_duplicates(), on=["edb", "disc_yr"])
    cov["check"] = cov.set_index(["edb", "asset_class"]).index.isin(
        latest_steps.set_index(["edb", "asset_class"]).index
    )
    cov["check"] = cov["check"].map({True: "step change this year", False: ""})
    period = (
        metrics.delivery_by_period(dlv, "^asset replacement and renewal$")
        if not dlv.empty
        else pd.DataFrame()
    )
    flags = metrics.early_warnings(cov, dlv, cfg, steps)
    notes = findings.headline(
        cls_latest=cls_latest,
        period=period,
        rel=rel,
        steps=steps,
        exceptions=exceptions,
        common_classes=common,
    )

    powerbi.export(out, cond=cond, age=age, dlv=dlv, rel=rel, cov=cov, flags=flags)
    class_trend.to_csv(out / "health_trend_by_class.csv", index=False)
    steps.to_csv(out / "grading_step_changes.csv", index=False)
    exceptions.to_csv(out / "data_quality_exceptions.csv", index=False)
    if not period.empty:
        period.to_csv(out / "renewal_delivery_by_period.csv", index=False)

    docs.mkdir(parents=True, exist_ok=True)
    page_args = dict(
        cond=cond,
        class_trend=class_trend,
        cls_latest=cls_latest,
        cov=cov,
        period=period,
        rel=rel,
        flags=flags,
        steps=steps,
        exceptions=exceptions,
        findings=notes,
        source_note=source_note,
        synthetic=synthetic_data,
        common_classes=common,
    )
    # docs/index.html loads Plotly from its CDN (for GitHub Pages); the standalone copy works offline.
    (docs / "index.html").write_text(report.build_html(**page_args), encoding="utf-8")
    (out / "dashboard_standalone.html").write_text(
        report.build_html(**page_args, plotlyjs=True), encoding="utf-8"
    )
    # page body only, for hosts that supply their own document skeleton
    (out / "artifact").mkdir(exist_ok=True)
    (out / "artifact" / "nz-network-asset-insights.html").write_text(
        report.build_html(**page_args, plotlyjs=True, fragment=True), encoding="utf-8"
    )
    summary = dict(
        conditions=len(cond),
        exceptions=len(exceptions),
        age_rows=len(age),
        delivery_rows=len(dlv),
        reliability_rows=len(rel),
        scored=len(cov),
        step_changes=len(steps),
        flags=len(flags),
        latest_year=latest_yr,
    )
    for k, v in summary.items():
        print(f"{k:>16}: {v}")
    for n in notes:
        print("-", n.replace("<b>", "").replace("</b>", ""))
    print(f"tables -> {out}/, dashboard -> {docs / 'index.html'}")
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="assets", description=__doc__)
    ap.add_argument("--config", help="path to a config.yaml (defaults to the packaged one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download", help="download the ComCom EDB information disclosure parquet file")
    p = sub.add_parser("profile", help="list the label combinations in the file, to check config patterns")
    p.add_argument("--file", default=str(RAW))
    p.add_argument("--schedule", help="regex on the schedule column, e.g. 12a")
    p.add_argument("--out", default="docs/schema_profile.csv")
    b = sub.add_parser("build", help="build tidy tables, Power BI CSVs and the dashboard")
    b.add_argument("--file", default=str(RAW))
    b.add_argument("--out", default="output")
    b.add_argument("--docs", default="docs")
    d = sub.add_parser("demo", help="run the pipeline on synthetic data (no download)")
    d.add_argument("--out", default="output/demo")
    d.add_argument("--docs", default="output/demo")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "download":
        print("downloading", cfg["sources"]["parquet_url"])
        download(cfg["sources"]["parquet_url"], RAW)
        print("saved", RAW, f"({RAW.stat().st_size / 1e6:.1f} MB)")
    elif args.cmd == "profile":
        df = load_disclosures(args.file)
        prof = profile(df, args.schedule, limit=100000)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        prof.to_csv(args.out, index=False)
        print(prof.groupby("schedule").size().to_string())
        print(f"{len(prof)} label combinations -> {args.out}")
    elif args.cmd == "build":
        df = load_disclosures(args.file)
        note = f"Source: Commerce Commission, EDB information disclosure data ({Path(args.file).name})"
        run_pipeline(df, cfg, Path(args.out), Path(args.docs), note, synthetic_data=False)
    elif args.cmd == "demo":
        df = synthetic.make()
        tmp = Path(args.out) / "synthetic.parquet"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp)
        run_pipeline(
            load_disclosures(tmp),
            cfg,
            Path(args.out),
            Path(args.docs),
            "Synthetic demo data",
            synthetic_data=True,
        )


if __name__ == "__main__":
    main()
