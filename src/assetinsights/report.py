"""Static HTML dashboard (for GitHub Pages) built from the tidy tables."""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import plotly.graph_objects as go

# Validated categorical order (adjacent pairs pass the CVD checks). A hue follows its entity, never its rank.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#121614", "#4d5551", "#7f8783", "#dfe3e0", "#c9cfcb", "#fdfdfc"
CRITICAL = "#d03b3b"

# Asset classes shown in the trend chart: the largest holdings plus the classes with the biggest gaps.
KEY_CLASSES = [
    ("Wood poles", "Wood poles"),
    ("Pole Mounted Transformer", "Pole mounted transformers"),
    ("Ground Mounted Transformer", "Ground mounted transformers"),
    ("Distribution OH Open Wire Conductor", "Distribution overhead conductor"),
    ("Zone Substation Transformers", "Zone substation transformers"),
    ("LV OH/UG Streetlight circuit", "Streetlight circuits"),
]


def _layout(fig: go.Figure, title: str, y_title: str, height: int = 400) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"),
        height=height,
        margin=dict(l=56, r=24, t=56, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="IBM Plex Sans, system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK2
        ),
        legend=dict(orientation="h", y=-0.16, x=0, font=dict(color=INK2)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickcolor=AXIS, tickfont=dict(color=MUTED))
    fig.update_yaxes(
        title=y_title, gridcolor=GRID, zeroline=True, zerolinecolor=AXIS, tickfont=dict(color=MUTED)
    )
    return fig


def _line(fig, x, y, name, color, unit="%"):
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            name=name,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=8, line=dict(color=SURFACE, width=2)),
            hovertemplate="%{y:.1f}" + unit + "<extra>" + name + "</extra>",
        )
    )


def fig_class_trend(trend: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for (cls, label), color in zip(KEY_CLASSES, SERIES, strict=False):
        d = trend[trend["asset_class"] == cls].sort_values("disc_yr")
        if not d.empty:
            _line(fig, d["disc_yr"], d["poor_pct"], label, color)
    fig.update_xaxes(dtick=1)
    fig = _layout(fig, "Share of units in H1 or H2, all networks", "% of units")
    fig.update_yaxes(rangemode="tozero")
    return fig


def fig_coverage(cls_latest: pd.DataFrame) -> go.Figure:
    d = cls_latest.sort_values("gap_pp")
    labels = d["asset_class"].map(lambda x: x if len(x) <= 30 else x[:29].rstrip() + "\u2026")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=d["poor_pct"],
            name="In H1 or H2 now",
            orientation="h",
            marker=dict(color=SERIES[0], cornerradius=4, line=dict(color=SURFACE, width=2)),
            customdata=d[["edbs"]],
            hovertemplate="%{x:.1f}% in H1/H2 (%{customdata[0]} networks)<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=labels,
            x=d["replace_5yr_pct"],
            name="Forecast to be replaced in next 5 years",
            orientation="h",
            marker=dict(color=SERIES[1], cornerradius=4, line=dict(color=SURFACE, width=2)),
            hovertemplate="%{x:.1f}% planned<extra></extra>",
        )
    )
    fig.update_layout(barmode="group", bargap=0.25)
    fig = _layout(fig, "Poor condition vs planned renewal", "", height=110 + 46 * len(d))
    fig.update_layout(hovermode="y unified", margin=dict(l=8))
    fig.update_xaxes(title="% of units", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


def fig_delivery(period: pd.DataFrame, reg_period: str) -> go.Figure:
    d = period[period["reg_period"] == reg_period].sort_values("delivery_pct")
    colors = [CRITICAL if v < 80 else SERIES[0] for v in d["delivery_pct"]]
    fig = go.Figure(
        go.Bar(
            y=d["edb"],
            x=d["delivery_pct"],
            orientation="h",
            marker=dict(color=colors, cornerradius=4, line=dict(color=SURFACE, width=2)),
            customdata=d[["actual", "forecast", "years"]],
            hovertemplate="%{y}<br>%{x:.0f}% of forecast<br>actual $%{customdata[0]:,.0f}k"
            " vs forecast $%{customdata[1]:,.0f}k<br>%{customdata[2]} years<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_vline(x=100, line=dict(color=INK2, width=1, dash="dot"))
    fig = _layout(fig, f"Renewal capex vs forecast, {reg_period}", "", height=24 * len(d) + 120)
    fig.update_layout(hovermode="closest", margin=dict(l=8))
    fig.update_xaxes(title="Actual as % of forecast (red: below 80%)", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


def fig_reliability(rel: pd.DataFrame) -> go.Figure:
    d = rel[rel["measure"] == "SAIDI"].groupby(["interruption", "disc_yr"])["value"].median().reset_index()
    fig = go.Figure()
    names = [
        ("planned", "Planned (class B)"),
        ("unplanned", "Unplanned (class C)"),
        ("unplanned, defective equipment", "Unplanned, defective equipment"),
    ]
    for (key, label), color in zip(names, SERIES, strict=False):
        s = d[d["interruption"] == key]
        _line(fig, s["disc_yr"], s["value"], label, color, unit=" min")
    fig.update_xaxes(dtick=1)
    fig = _layout(fig, "SAIDI, median network", "minutes")
    fig.update_yaxes(rangemode="tozero")
    return fig


FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600'
    '&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;600&display=swap">'
)

# Re-colours the Plotly charts from the page tokens so they follow light and dark themes.
THEME_JS = """
<script>
(function(){
  var DARK={"#2a78d6":"#3987e5","#eb6834":"#d95926","#1baf7a":"#199e70","#eda100":"#c98500",
            "#e87ba4":"#d55181","#008300":"#008300","#6250d6":"#9085e9","#e34948":"#e66767","#d03b3b":"#e66767"};
  function isDark(){
    var t=document.documentElement.getAttribute("data-theme");
    if(t) return t==="dark";
    return window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function tok(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
  function swap(c,dark){
    if(typeof c!=="string") return c;
    var k=c.toLowerCase();
    if(dark) return DARK[k]||c;
    for(var l in DARK){ if(DARK[l]===k) return l; }
    return c;
  }
  function apply(){
    if(!window.Plotly) return;
    var dark=isDark(), ink=tok("--ink"), ink2=tok("--ink2"), muted=tok("--muted"), line=tok("--line");
    document.querySelectorAll(".js-plotly-plot").forEach(function(el){
      (el.data||[]).forEach(function(tr,i){
        var u={};
        if(tr.line&&tr.line.color) u["line.color"]=swap(tr.line.color,dark);
        if(tr.marker&&tr.marker.color) u["marker.color"]=Array.isArray(tr.marker.color)?
          [tr.marker.color.map(function(c){return swap(c,dark);})]:swap(tr.marker.color,dark);
        if(tr.marker&&tr.marker.line) u["marker.line.color"]=tok("--surface");
        if(Object.keys(u).length) Plotly.restyle(el,u,[i]);
      });
      Plotly.relayout(el,{"font.color":ink2,"title.font.color":ink,"legend.font.color":ink2,
        "xaxis.tickfont.color":muted,"yaxis.tickfont.color":muted,"xaxis.gridcolor":line,"yaxis.gridcolor":line,
        "xaxis.linecolor":line,"yaxis.zerolinecolor":line,"hoverlabel.bgcolor":tok("--surface"),
        "hoverlabel.font.color":ink});
    });
  }
  window.addEventListener("load",apply);
  if(window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",apply);
  new MutationObserver(apply).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
})();
</script>
"""


def _table(df: pd.DataFrame, cols: dict[str, str], fmt: dict[str, str] | None = None, limit: int = 20) -> str:
    fmt = fmt or {}
    head = "".join(f"<th>{html.escape(v)}</th>" for v in cols.values())
    body = []
    for _, r in df.head(limit).iterrows():
        cells = []
        for k in cols:
            v = r[k]
            s = "" if pd.isna(v) else (format(v, fmt[k]) if k in fmt else str(v))
            num = k in fmt
            cells.append(f'<td class="{"num" if num else ""}">{html.escape(s)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


CSS = """
/* Layout: a single reading column of evidence, summary first, then one chart or table per question. */
:root{
  --page:#f6f7f5; --surface:#fdfdfc; --ink:#121614; --ink2:#4d5551; --muted:#7f8783; --line:#dfe3e0;
  --thead:#eef1ef; --accent:#1f6fc4; --critical:#c23535;
  --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --display:"IBM Plex Sans Condensed","IBM Plex Sans",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --page:#121513; --surface:#1a1e1c; --ink:#eef1ef; --ink2:#c0c7c3; --muted:#8a928e; --line:#2d3330;
  --thead:#222826; --accent:#5d9fe8; --critical:#e66767; color-scheme:dark}}
:root[data-theme="dark"]{
  --page:#121513; --surface:#1a1e1c; --ink:#eef1ef; --ink2:#c0c7c3; --muted:#8a928e; --line:#2d3330;
  --thead:#222826; --accent:#5d9fe8; --critical:#e66767; color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 var(--body)}
main{max-width:1080px;margin:0 auto;padding-block:32px 64px;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2{font-family:var(--display);text-wrap:balance;letter-spacing:-0.01em}
h1{font-size:30px;font-weight:600;margin:0 0 6px;line-height:1.2}
h2{font-size:20px;font-weight:600;margin:44px 0 8px}
.eyebrow{font:600 12px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
p.lede{color:var(--ink2);margin:0 0 20px;max-width:68ch}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0 8px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;min-width:0}
.tile b{display:block;font:600 26px/1.2 var(--display)}.tile span{color:var(--ink2);font-size:13px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px;margin:12px 0;min-width:0}
.note{color:var(--ink2);font-size:14px;max-width:72ch}
.findings{border-left:3px solid var(--accent);padding:2px 0 2px 18px;margin:20px 0;max-width:80ch}
.findings ul{margin:0;padding-left:18px}.findings li{margin:10px 0}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600;background:var(--thead)}
td.num{text-align:right;font:13px var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
footer{margin-top:48px;color:var(--muted);font-size:13px}a{color:var(--accent)}
code{font:12.5px var(--mono)}
"""


def build_html(
    *,
    cond: pd.DataFrame,
    class_trend: pd.DataFrame,
    cls_latest: pd.DataFrame,
    cov: pd.DataFrame,
    period: pd.DataFrame,
    rel: pd.DataFrame,
    flags: pd.DataFrame,
    steps: pd.DataFrame,
    exceptions: pd.DataFrame,
    findings: list[str],
    source_note: str,
    synthetic: bool = False,
    plotlyjs: str | bool = "cdn",
    common_classes: set[str] | None = None,
    fragment: bool = False,
) -> str:
    first_yr, latest_yr = int(cond["disc_yr"].min()), int(cond["disc_yr"].max())
    gaps = int((flags["flag"] == "Renewal coverage gap").sum())
    tiles = [
        (f"{cond['edb'].nunique()}", "distribution networks"),
        (f"{first_yr}-{latest_yr}", "condition disclosures (H1-H5 scale)"),
        (f"{gaps}", "renewal coverage gaps of 5+ points"),
        (f"{len(steps)}", "one-year grading step changes"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>' for v, k in tiles
    )

    periods = sorted(period["reg_period"].unique()) if not period.empty else []
    complete = [p for p in periods if period[period["reg_period"] == p]["years"].max() >= 5]
    show_period = complete[-1] if complete else (periods[-1] if periods else None)

    figs = {"trend": fig_class_trend(class_trend), "coverage": fig_coverage(cls_latest)}
    if show_period:
        figs["delivery"] = fig_delivery(period, show_period)
    if not rel.empty:
        figs["reliability"] = fig_reliability(rel)
    divs = {}
    # The bundled Plotly source contains a literal U+FFFD inside one regex; write it as an escape.
    for i, (k, f) in enumerate(figs.items()):
        divs[k] = f.to_html(
            full_html=False,
            include_plotlyjs=plotlyjs if i == 0 else False,
            config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["toImage"]},
        ).replace("\ufffd", "\\ufffd")

    counts = flags["flag"].value_counts()
    flag_counts = " · ".join(f"{html.escape(k)}: {v}" for k, v in counts.items())
    flags_top = flags.groupby("flag", sort=False).head(8)
    priority = cov[(cov["priority_score"] > 0)].copy()
    if "check" not in priority.columns:
        priority["check"] = ""
    priority["asset"] = priority["asset_category"] + " / " + priority["asset_class"]
    steps_t = steps if common_classes is None else steps[steps["asset_class"].isin(common_classes)]
    steps_t = steps_t.copy()
    steps_t["years"] = steps_t["prev_yr"].astype(str) + " to " + steps_t["disc_yr"].astype(str)
    banner = (
        '<p class="note"><b>Synthetic demo data.</b> The networks and numbers on this page are made up, '
        "to show the pipeline. Run <code>assets build</code> on the real file for actual results.</p>"
        if synthetic
        else ""
    )
    findings_html = (
        '<div class="findings"><ul>' + "".join(f"<li>{f}</li>" for f in findings) + "</ul></div>"
        if findings
        else ""
    )
    delivery_html = (
        f"""<h2>4. Delivery against forecast</h2>
<p class="note">Asset replacement and renewal capex from Schedule 7: actual spend against the forecast in each
network's earlier asset management plan, summed over the regulatory period.</p>
<div class="card">{divs["delivery"]}</div>"""
        if show_period
        else ""
    )
    rel_html = (
        f"""<h2>5. Service outcome</h2>
<p class="note">SAIDI (minutes without supply per customer per year) from Schedule 10 for the median network. Planned minutes come mostly from outages taken to
do work on the network; the defective equipment line is the part of unplanned SAIDI most tied to asset condition.
The 2023 disclosure year (April 2022 to March 2023) includes the Auckland Anniversary floods and Cyclone Gabrielle.</p>
<div class="card">{divs["reliability"]}</div>"""
        if not rel.empty
        else ""
    )
    head = (
        f'<title>NZ Network Asset Insights</title><meta name="claude:viewport-fit-sides" content="cover">'
        f"{FONTS}<style>{CSS}</style>"
    )
    opening = (
        head
        if fragment
        else '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        + head
        + "</head><body>"
    )
    closing = "" if fragment else "</body></html>"
    return f"""{opening}<main>
<p class="eyebrow">Commerce Commission information disclosures · Schedules 7, 9b, 10, 12a</p>
<h1>NZ electricity distribution asset portfolio</h1>
<p class="lede">Asset health, renewal coverage and delivery against forecast for New Zealand's electricity
distribution businesses, from their information disclosures to the Commerce Commission.</p>
{banner}
<div class="tiles">{tiles_html}</div>
{findings_html}

<h2>1. Asset health over time</h2>
<p class="note">Share of units graded H1 or H2 (the two poorest of five grades) in Schedule 12a, combined across
networks by unit quantity from the Schedule 9b age profile. Large single-year moves usually trace back to one
network re-grading its assets (see section 6).</p>
<div class="card">{divs["trend"]}</div>

<h2>2. Is planned renewal keeping up?</h2>
<p class="note">Asset classes held by at least 15 networks, latest disclosure, sorted by the gap between the share
already in H1 or H2 and the share forecast to be replaced in the next five years.</p>
<div class="card">{divs["coverage"]}</div>

<h2>3. Priority list</h2>
<p class="note">Network asset classes ranked by coverage gap times a consequence weight. Criticality is not
disclosed, so the weights in <code>config.yaml</code> are an assumption (zone substation and subtransmission 3,
distribution, poles, protection and SCADA 2, others 1); the unweighted rank shows their effect. Holdings under
10 units or km are not ranked.</p>
{
        _table(
            priority,
            {
                "priority_rank": "Rank",
                "unweighted_rank": "Unweighted",
                "edb": "Network",
                "asset": "Asset",
                "quantity": "Quantity",
                "poor_pct": "% H1/H2",
                "replace_5yr_pct": "% planned 5 yrs",
                "coverage_gap_pp": "Gap (pts)",
                "weight": "Weight",
                "check": "Check",
            },
            {
                "priority_rank": ".0f",
                "unweighted_rank": ".0f",
                "quantity": ",.0f",
                "poor_pct": ".1f",
                "replace_5yr_pct": ".1f",
                "coverage_gap_pp": ".1f",
                "weight": ".0f",
            },
        )
    }

{delivery_html}

{rel_html}

<h2>6. Data quality checks</h2>
<p class="note">One-year moves of 20 points or more in a network's H1/H2 share for an asset class (classes held
by at least 15 networks, holdings of 10 units or km and over), sorted by how far each one moved the all-network
figure for that class. Moves this
large are more likely changes in assessment method than real deterioration, so they should be confirmed with the
network before being read as a trend. Full list in <code>output/grading_step_changes.csv</code>.</p>
{
        _table(
            steps_t,
            {
                "edb": "Network",
                "asset_class": "Asset class",
                "years": "Years",
                "quantity": "Quantity",
                "prev_pct": "From %",
                "poor_pct": "To %",
                "national_effect_pp": "Effect on all networks (pts)",
            },
            {"quantity": ",.0f", "prev_pct": ".1f", "poor_pct": ".1f", "national_effect_pp": "+.1f"},
            limit=20,
        )
    }
<p class="note">Records left out of the analysis because their grades do not add up to 100%
(within 95% to 105%): {
        len(exceptions)
    }. They are listed in <code>output/data_quality_exceptions.csv</code>.</p>

<h2>Early warnings, latest disclosure</h2>
<p class="note">Rule-based flags: coverage gaps of 5 points or more, H1/H2 share up 3 points or more over three
years, grading step changes, and capex lines over $1m that were more than 20% away from forecast. Thresholds are
in <code>config.yaml</code>. Full list in <code>output/early_warnings.csv</code>.</p>
<p class="note">{flag_counts}</p>
{
        _table(
            flags_top,
            {"flag": "Flag", "edb": "Network", "subject": "Subject", "value": "Value", "detail": "Detail"},
            {"value": "+.1f"},
            limit=40,
        )
    }

<h2>Method and limits</h2>
<p class="note">Condition grades are assessed by each network and practice differs between networks; Schedule 12a
also carries a data accuracy score from 1 to 4, which is kept in the outputs. Disclosures before 2019 used a
different four-grade scale and are not included. Planned replacement is a forecast, not a commitment, and assets
in H2 may reasonably be scheduled beyond five years. Schedule 7 compares actual spend with the forecast made in
an earlier plan, so a variance reflects both delivery and changes of plan. Distribution networks are not
Transpower's grid, but they report under the same Commerce Commission regime, which makes them the most
complete public data set for this kind of portfolio analysis.</p>
<footer>{html.escape(source_note)}. Code and method:
<a href="https://github.com/vera-kaku/nz-network-asset-insights">github.com/vera-kaku/nz-network-asset-insights</a>.
Generated {date.today().isoformat()}.</footer>
</main>{THEME_JS}{closing}"""
