"""Download, load and inspect the Commerce Commission EDB information disclosure dataset."""

from __future__ import annotations

import re
import urllib.request
from importlib import resources
from pathlib import Path

import pandas as pd
import yaml

TEXT_COLS = [
    "edb",
    "network",
    "schedule",
    "source",
    "section",
    "category",
    "sub_category",
    "description",
    "units",
]
YEAR_COLS = ["disc_yr", "obs_yr", "fcast_yr"]


def load_config(path: str | Path | None = None) -> dict:
    if path:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return yaml.safe_load(
        resources.files("assetinsights").joinpath("config.yaml").read_text(encoding="utf-8")
    )


def download(url: str, dest: Path) -> Path:
    """Download one file. Files are kept out of git (see .gitignore)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "nz-network-asset-insights/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    return dest


def load_disclosures(path: str | Path) -> pd.DataFrame:
    """Read the long-format disclosure file (parquet or csv/csv.gz) into a clean frame."""
    path = Path(path)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"edb", "disc_yr", "schedule", "description", "value"} - set(df.columns)
    if missing:
        raise ValueError(f"File does not look like EDB ID data, missing columns: {sorted(missing)}")
    for col in TEXT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().fillna("")
        else:
            df[col] = ""
    for col in YEAR_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype("string").str.extract(r"(\d{4})")[0], errors="coerce")
        else:
            df[col] = pd.NA
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # Whole-network rows only; sub-network rows would double count.
    if "network" in df.columns:
        whole = df["network"].str.lower().isin(["", "all"])
        if whole.any():
            df = df[whole]
    return df.reset_index(drop=True)


def match(series: pd.Series, pattern: str) -> pd.Series:
    rx = re.compile(pattern, flags=re.IGNORECASE)
    return series.fillna("").astype(str).map(lambda s: bool(rx.search(s))).astype(bool)


def latest_version(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the most recent version of each disclosure when restated values exist."""
    if "version" not in df.columns or df["version"].isna().all():
        return df
    keys = [
        "edb",
        "disc_yr",
        "schedule",
        "section",
        "category",
        "sub_category",
        "description",
        "obs_yr",
        "fcast_yr",
    ]
    return df.sort_values("version").drop_duplicates(keys, keep="last")


def profile(df: pd.DataFrame, schedule_pattern: str | None = None, limit: int = 400) -> pd.DataFrame:
    """Distinct label combinations, used to check the config patterns against the real file."""
    sub = df if schedule_pattern is None else df[match(df["schedule"], schedule_pattern)]
    cols = ["schedule", "section", "category", "sub_category", "description", "units"]
    out = (
        sub.groupby(cols, dropna=False)
        .agg(
            rows=("value", "size"),
            edbs=("edb", "nunique"),
            first_yr=("disc_yr", "min"),
            last_yr=("disc_yr", "max"),
        )
        .reset_index()
        .sort_values(cols)
    )
    return out.head(limit)
