# NZ Network Asset Insights

**Live dashboard:** https://vera-kaku.github.io/nz-network-asset-insights/

Portfolio performance analysis of New Zealand electricity distribution assets, built from the information disclosures that every regulated electricity distribution business (EDB) files with the Commerce Commission.

The project asks the questions a portfolio performance team asks about its own asset base:

1. **Asset health.** What share of each asset group is in poor condition (grade H1 or H2), and is it getting better or worse?
2. **Renewal coverage.** Is the planned five-year replacement programme large enough to cover the assets already in poor condition?
3. **Prioritisation.** Which network and asset class combinations have the largest gap, once a consequence weight is applied?
4. **Delivery.** How much of the forecast renewal capex was actually spent over each regulatory period?
5. **Outcome.** How has unplanned SAIDI moved over the same years?

Outputs are a static dashboard (`docs/index.html`, published with GitHub Pages), a Power BI ready star schema (`output/*.csv`), a rule-based early-warning list and a data quality report.

## Findings

From the June 2026 release of the data (29 networks; condition data 2019 to 2026, spend and reliability data 2013 to 2025). The same figures are computed by the pipeline and shown at the top of the dashboard.

- **Renewal plans lag condition in a few asset classes.** In the 2026 disclosures, the largest gaps between the share of units already in H1 or H2 and the share forecast to be replaced in the next five years are in centralised load control plant (25.2% vs 13.6%), LV streetlight circuits (10.8% vs 1.2%) and distribution overhead conductor (11.5% vs 3.9%). Wood poles are covered (8.5% vs 9.1%).
- **Renewal spend has met forecast overall.** Actual asset replacement and renewal capex was 106% of forecast across all networks in DPP3 (2021-2025), up from 101% in DPP2 (2016-2020). One network spent less than 80% of its forecast over DPP3.
- **Planned outage minutes have grown.** Median planned SAIDI rose from 43 minutes in 2013 to 138 minutes in 2025, in line with more work on the networks, while unplanned SAIDI from defective equipment stayed between 24 and 39 minutes a year.
- **Big national movements often come from one network re-grading.** 194 one-year moves of 20 points or more in a network's H1/H2 share were found (holdings of 10 units or km and over). Several of the large swings in the all-network figures come from a single network re-assessing an asset class in one year, so the dashboard reports them for checking instead of reading them as deterioration.
- **Data checks.** 13 network asset class records were excluded because their condition grades do not add up to 100% (95% to 105% tolerance). Disclosures before 2019 use a different four-grade scale and are not compared.

## Data

| Source | What is used |
|---|---|
| [Commerce Commission, EDB information disclosure data](https://www.comcom.govt.nz/regulated-industries/electricity-lines/electricity-distributor-performance-and-data/information-disclosed-by-electricity-distributors) (`EDB_ID_Full`, all years, parquet) | Schedule 12a asset condition, 9b asset age profile, 7 forecast against actual expenditure, 10 network reliability |

The data file is not stored in this repository. `assets download` fetches it from the Commerce Commission site.

**Why distribution data?** Transpower's public open data covers asset locations but not asset condition or spend. EDBs disclose condition grades, age profiles, capex forecasts and actuals under the same Commerce Commission regime, which makes them the most complete public data set for this kind of analysis.

## Method

- **Condition.** Schedule 12a gives, for each asset class, the share of units in grades H1 (the poorest) to H5 (as new), plus the share forecast to be replaced in the next five years. Poor share = H1 + H2.
- **Weighting.** Networks are combined within each asset class using unit quantities from the Schedule 9b age profile of the same year (or the latest earlier year), so a network with 50,000 poles counts more than one with 2,000. Classes are not added together, because their units differ (number of poles, km of line).
- **Coverage gap** = poor share minus planned five-year replacement, in percentage points. A positive gap means some poor-condition assets are not yet in the renewal plan.
- **Priority score** = positive coverage gap × consequence weight. Criticality is not disclosed, so the weights in `config.yaml` are an explicit assumption (zone substation and subtransmission 3; distribution, poles, protection and SCADA 2; others 1). The unweighted rank is reported next to the weighted one.
- **Delivery** = actual ÷ forecast asset replacement and renewal capex from Schedule 7, summed over each default price-quality path period (DPP2 2016-2020, DPP3 2021-2025).
- **Early warnings** flag coverage gaps of 5 points or more, a rise of 3 points or more in poor share over three years, a one-year step change of 20 points or more, and capex lines over $1m more than 20% away from forecast in the latest year. All thresholds are in `config.yaml`.
- **Data quality.** Grades that do not add up to 100% are excluded and listed; one-year step changes are reported with their effect on the all-network figure, since they usually reflect a change in how a network assessed its assets.

### Limits

- Condition grades are assessed by each network against the Commerce Commission's grade definitions, and practice varies between networks. Schedule 12a also reports a data accuracy score, which is carried into the outputs.
- Planned replacement is a forecast in an asset management plan, not a commitment.
- Schedule 7 compares actual spend with the forecast made in an earlier plan, so variance reflects both delivery and changes of plan.
- Sub-network rows are excluded to avoid double counting.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

assets download          # about 14 MB, saved to data/raw/
assets profile           # optional: lists every label combination, to check config.yaml
assets build             # writes output/*.csv and docs/index.html
pytest                   # 19 tests on a synthetic data set, no download needed
assets demo              # full pipeline on synthetic data
```

To see the dashboard, open `docs/index.html` (or `output/dashboard_standalone.html`, which works offline). To publish it, enable GitHub Pages on the `docs/` folder of the main branch.

Power BI: see [docs/powerbi.md](docs/powerbi.md) for relationships and DAX measures.

## Project layout

```
src/assetinsights/
  load.py       download, load and profile the disclosure file
  extract.py    long-format rows to tidy tables (condition, age, delivery, reliability)
  metrics.py    weighted health trend, coverage gap, priority ranking, step changes, early warnings
  findings.py   headline findings computed from the tables
  report.py     static Plotly dashboard
  powerbi.py    star schema export
  config.yaml   label patterns, thresholds and consequence weights
tests/          pytest suite on synthetic data
```

## Licence and attribution

Data: Commerce Commission New Zealand, EDB information disclosure data. Code: all rights reserved by the author unless a licence file is added.

Built with the help of AI coding assistants.
