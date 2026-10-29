"""Small synthetic dataset with the same layout and labels as the Commerce Commission file.

Used by the tests and the `assets demo` command so the pipeline can run without downloading
anything. The networks are fictional and none of the numbers are real.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ASSETS = [
    ("HV - Subtransmission Line", "Subtransmission OH up to 66kV conductor"),
    ("HV - Zone Substation Transformer", "Zone Substation Transformers"),
    ("All - Overhead Line", "Wood poles"),
    ("HV - Distribution Transformer", "Pole Mounted Transformer"),
    ("LV - LV Streetlighting", "LV OH/UG Streetlight circuit"),
    ("All - Protection", "Protection relays (electromechanical, solid state and numeric)"),
]
EDBS = ["Network North", "Network East", "Network South", "Network West"]
YEARS = range(2019, 2027)
S12A = "SCHEDULE 12a: REPORT ON ASSET CONDITION"
S9B = "SCHEDULE 9b: ASSET AGE PROFILE"
S7 = "SCHEDULE 7: COMPARISON OF FORECASTS TO ACTUAL EXPENDITURE"
S10 = "SCHEDULE 10: REPORT ON NETWORK RELIABILITY"
AGE_PREFIX = "Number of assets at disclosure year end by installation date - "


def _row(edb, yr, schedule, section, category, sub_category, description, value, units="", source=""):
    return dict(
        edb=edb,
        network="All",
        disc_yr=float(yr),
        schedule=schedule,
        source=source,
        section=section,
        category=category,
        sub_category=sub_category,
        description=description,
        value=value,
        units=units,
        obs_yr=float(yr),
        fcast_yr=np.nan,
        version=f"{yr}.05.1",
    )


def make(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for e_i, edb in enumerate(EDBS):
        for a_i, (cat, cls) in enumerate(ASSETS):
            base_poor = 4 + 3 * e_i + 2 * a_i
            qty = int(rng.integers(200, 20000))
            for t, yr in enumerate(YEARS):
                poor = base_poor + t * (0.4 + 0.3 * e_i)
                # one network re-grades its wood poles in a single year (a step change)
                if edb == "Network East" and cls == "Wood poles" and yr >= 2025:
                    poor = 45.0
                h1, h2 = poor * 0.35, poor * 0.65
                unknown = max(0.0, 6 - t)
                h3, h5 = 25.0, 15.0
                h4 = 100 - h1 - h2 - h3 - h5 - unknown
                grades = dict(
                    zip(
                        ["H1", "H2", "H3", "H4", "H5", "Grade unknown"],
                        [h1, h2, h3, h4, h5, unknown],
                        strict=True,
                    )
                )
                # one record whose grades do not add up, to exercise the data quality check
                if edb == "Network South" and cls == "Pole Mounted Transformer" and yr == 2022:
                    grades = {k: v * 1.4 for k, v in grades.items()}
                sec = "12a: Asset Condition"
                for g, v in grades.items():
                    rows.append(
                        _row(edb, yr, S12A, sec, cat, cls, g, round(v / 100, 6), "No.", "Year beginning")
                    )
                replace = poor * (1.1 - 0.25 * e_i)
                rows.append(
                    _row(
                        edb,
                        yr,
                        S12A,
                        sec,
                        cat,
                        cls,
                        "% of asset forecast to be replaced in next five years",
                        round(replace / 100, 6),
                        "No.",
                        "Year beginning",
                    )
                )
                rows.append(
                    _row(edb, yr, S12A, sec, cat, cls, "Data accuracy (1-4)", 3, "No.", "Year beginning")
                )

                age_sec = "9b: Asset Age Profile"
                rows.append(
                    _row(edb, yr, S9B, age_sec, cat, cls, "Items at end of year (quantity)", qty, "No.")
                )
                rows.append(
                    _row(edb, yr, S9B, age_sec, cat, cls, "Number with age unknown", int(qty * unknown / 100))
                )
                for bucket, share in (
                    ("pre-1940", 0.02),
                    ("1960-1969", 0.18),
                    ("1980-1989", 0.3),
                    ("2000-2009", 0.3),
                    ("2015", 0.2),
                ):
                    rows.append(
                        _row(edb, yr, S9B, age_sec, cat, cls, AGE_PREFIX + bucket, int(qty * share), "No.")
                    )

        for t, yr in enumerate(YEARS):
            for item, fc in (
                ("Asset replacement and renewal", 30000),
                ("System growth", 12000),
                ("Consumer connection", 15000),
            ):
                factor = 0.75 + 0.1 * e_i if item == "Asset replacement and renewal" else 1.05
                act = fc * factor * (1 + rng.normal(0, 0.05))
                for measure, v in (("Forecast", fc), ("Actual", round(act, 1)), ("Variance", act / fc - 1)):
                    rows.append(
                        _row(
                            edb,
                            yr,
                            S7,
                            "7(ii): Expenditure on Assets",
                            "Network assets",
                            measure,
                            item,
                            v,
                            "$000",
                        )
                    )
            rows.append(
                _row(
                    edb,
                    yr,
                    S7,
                    "7(iii): Operational Expenditure",
                    "Network opex",
                    "Forecast",
                    "Asset replacement and renewal",
                    3000,
                    "$000",
                )
            )
            rows.append(
                _row(
                    edb,
                    yr,
                    S7,
                    "7(iii): Operational Expenditure",
                    "Network opex",
                    "Actual",
                    "Asset replacement and renewal",
                    2500,
                    "$000",
                )
            )

            bump = 1 + 0.03 * t * (e_i - 1)
            for desc, saidi, saifi in (
                ("Class B (planned interruptions on the network)", 40, 0.2),
                ("Class C (unplanned interruptions on the network)", 110, 1.4),
                ("Total", 150, 1.6),
            ):
                for measure, v in (("SAIDI", saidi * bump), ("SAIFI", saifi * bump)):
                    rows.append(
                        _row(
                            edb,
                            yr,
                            S10,
                            "10(i): Interruptions",
                            "SAIFI and SAIDI by class",
                            measure,
                            desc,
                            round(v, 3),
                            "value",
                        )
                    )
            for measure, v in (("SAIDI", 30 * bump), ("SAIFI", 0.4 * bump)):
                rows.append(
                    _row(
                        edb,
                        yr,
                        S10,
                        "10(ii): Class C Interruptions and Duration by Cause",
                        "Cause",
                        measure,
                        "Defective equipment",
                        round(v, 3),
                        "value",
                    )
                )
    return pd.DataFrame(rows)
