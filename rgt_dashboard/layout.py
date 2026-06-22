# -*- coding: utf-8 -*-
"""
Page layout -- Modern Theme 2026.

Three main tabs (Plot Explorer, Genetic Gain & Summary, Installations Map)
live in the page; the report assistant is a floating "ForestAsk" chat widget
(button bottom-right that opens a popup), available from any tab.
"""
from __future__ import annotations

from dash import dcc, html

from . import config
from .assistant import CLIENT
from .components import dropdown

IFC_LOGO = "https://ifc.nkn.uidaho.edu/static/img/ifc_logo_official.png"
UI_LOGO  = "https://nextsteps.idaho.gov/assets/uploads/2020/05/LOGO-UIdaho-2020.jpg"
ASSISTANT_NAME = "ForestAsk"

SUGGESTIONS = [
    "Report on installation HOODOO",
    "Deployment report: Improved vs Woods Run across CORE sites",
    "Report comparing INW vs K-S",
    "Report on seedlot 97-72 across INW sites",
]


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------

def _hs_item(icon: str, color: str, val: str, label: str):
    return html.Div([
        html.Div(icon, className=f"hs-icon hs-{color}"),
        html.Div([
            html.Div(val,   className="hs-val"),
            html.Div(label, className="hs-label"),
        ]),
    ], className="hs-item")


def _compute_hero(store) -> list:
    try:
        n_insts   = len(store.installations_all())
        n_years   = len(list(store.years()))
        n_regions = len(list(store.regions()))
        try:
            from . import stats as _stats
            ov = _stats.trial_overview(store)
            gdata = ov.get("gain_by_year_and_metric_CORE_percent", {})
            best = max(
                (gdata[yr]["Volume"]["mean_gain_pct"]
                 for yr in gdata if "Volume" in gdata[yr]),
                default=0.0,
            )
            gain_str = f"+{best:.0f}%"
        except Exception:
            gain_str = "+32%"
        return [
            ("🌲", "gold",  str(n_insts),  "Installations"),
            ("📅", "sky",   str(n_years),  "Measurement Years"),
            ("📈", "green", gain_str,       "Peak Vol. Gain"),
            ("🗺️", "amber", str(n_regions), "Trial Regions"),
        ]
    except Exception:
        return [
            ("🌲", "gold",  "--",   "Installations"),
            ("📅", "sky",   "3",    "Measurement Years"),
            ("📈", "green", "+32%", "Peak Vol. Gain"),
            ("🗺️", "amber", "2",    "Trial Regions"),
        ]


# -----------------------------------------------------------------------
# Page sections
# -----------------------------------------------------------------------

def _topbar(hero_items=None):
    stats_row = html.Div(
        [_hs_item(*item) for item in (hero_items or [])],
        className="topbar-stats",
    )
    return html.Div([
        html.Div([
            html.A(
                html.Div([
                    html.Img(src=IFC_LOGO, alt="IFC", className="brand-logo"),
                    html.Div([
                        html.H1("Realized Genetic Gain Trials"),
                        html.P("Woods Run vs Improved Douglas-fir · INW & K-S Regions",
                               className="sub"),
                    ], className="titles"),
                ], className="brand"),
                href="https://ifc.nkn.uidaho.edu/",
                target="_blank",
                style={"textDecoration": "none"},
            ),
            html.Div([
                html.Button(
                    "🌐", id="topbar-map-btn", className="topbar-btn", n_clicks=0,
                    title="Installations map",
                    **{"aria-label": "Open the installations map"},
                ),
                html.Button(
                    "ⓘ", id="methods-btn", className="topbar-btn", n_clicks=0,
                    title="Methods & definitions",
                    **{"aria-label": "Open methods and definitions"},
                ),
                html.Button(
                    "🌙", id="theme-toggle", className="topbar-btn theme-toggle",
                    n_clicks=0, title="Toggle light / dark theme",
                    **{"aria-label": "Toggle light or dark theme"},
                ),
                html.A(
                    html.Span("Intermountain Forestry Cooperative", className="badge badge-link"),
                    href="https://www.intermtnforestcoop.com/",
                    target="_blank",
                    style={"textDecoration": "none"},
                ),
                html.Span("v2.0", className="badge gold"),
            ], className="topbar-right"),
        ], className="topbar-main"),
        # hero stats row removed per design — single clean header bar
    ], className="topbar")


def _controls(store):
    regions = list(store.regions())
    years   = list(store.years())
    metrics = list(store.metrics())
    default_inst = config.REGION_DEFAULT_INSTALLATION.get(config.DEFAULT_REGION)
    return html.Div([
        dropdown("dd-region",   regions,
                 config.DEFAULT_REGION if config.DEFAULT_REGION in regions else regions[0],
                 label="Region", persistence=True),
        html.Div(
            dropdown("dd-installation", list(store.installations(config.DEFAULT_REGION)),
                     default_inst, label="Installation"),
            id="installation-wrap",
        ),
        dropdown("dd-year",    years,
                 config.DEFAULT_YEAR   if config.DEFAULT_YEAR   in years   else years[0],
                 label="Year", persistence=True),
        dropdown("dd-metric",
                 [{"label": config.METRICS.get(m, {}).get("label", m), "value": m} for m in metrics],
                 config.DEFAULT_METRIC if config.DEFAULT_METRIC in metrics else metrics[0],
                 label="Metric", persistence=True),
        html.Div(
            dropdown("dd-insttype", ["ALL", "CORE", "TRANSFER"], "CORE", label="Site Type",
                     persistence=True),
            id="insttype-wrap",
        ),
        html.P(
            "Region, Year and Metric apply everywhere. Installation drives Plot Explorer; "
            "Site Type drives Genetic Gain & Summary — a dimmed control doesn't affect the "
            "current tab.",
            className="controls-note",
        ),
    ], className="controls", id="controls-bar")


def _explorer_pane():
    return html.Div([
        html.Div(id="exp-kpi", className="kpi-row"),
        html.Div(id="exp-deploy"),
        html.Div(id="exp-plots"),
        html.Div(id="exp-tables", className="card-grid grid-3",
                 style={"marginTop": "16px"}),
    ], id="pane-explorer")


def _section(title, subtitle=None):
    """A labelled section divider used to break a long tab into clear groups."""
    children = [html.H4(title, className="section-title")]
    if subtitle:
        children.append(html.P(subtitle, className="section-subtitle"))
    return html.Div(children, className="section-head sum-section")


def _summary_pane():
    return html.Div([
        html.Div(id="sum-kpi", className="kpi-row"),

        # ---- Section 1 · Realized genetic gain ----
        _section("Realized genetic gain",
                 "Improved vs Woods Run by site, and whether gain tracks site productivity."),
        html.Div([
            html.Div([
                html.Span("Stars:  ", style={"fontWeight": 600}),
                html.Span("* p<0.05   ** p<0.01   *** p<0.001   ·   ns = not significant."),
                html.Br(),
                html.Span(
                    "Per-site Welch t-tests, uncorrected for multiplicity. Enable FDR "
                    "(Benjamini–Hochberg) to control the false-discovery rate across the sites "
                    "shown; the p column then reports q-values.",
                    style={"fontSize": "11px"}),
            ], className="sig-key", style={"color": config.Color.MUTED}),
            dcc.Checklist(
                id="fdr-toggle",
                options=[{"label": " FDR-adjust", "value": "fdr"}],
                value=[], className="fdr-toggle", inputStyle={"marginRight": "6px"},
            ),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "gap": "16px", "margin": "4px 2px 0"}),
        html.Div([
            html.Div(id="sum-gain-card"),
            html.Div(id="sum-prod-card"),
        ], className="card-grid grid-2", style={"marginTop": "10px"}),

        # ---- Section 2 · Site-by-site detail ----
        _section("Site-by-site detail",
                 "Per-site gain & survival and per-seedlot means — export either as CSV."),
        html.Div([
            html.Button("Download gain table (CSV)", id="dl-gain-btn",
                        className="btn btn-ghost"),
            html.Button("Download seedlot table (CSV)", id="dl-seedlot-btn",
                        className="btn btn-ghost"),
            dcc.Download(id="dl-gain"),
            dcc.Download(id="dl-seedlot"),
        ], style={"margin": "0 0 10px", "display": "flex",
                  "gap": "8px", "justifyContent": "flex-end"}),
        html.Div(id="sum-table-card"),

        # ---- Section 3 · Distributions ----
        _section("Distributions across seedlots & sites",
                 "Seedlot means by site, the spread of individual trees, and installation means."),
        html.Div(id="sum-bars", className="card-grid grid-2", style={"marginTop": "10px"}),
        html.Div([
            html.Div(id="sum-box-card"),
            html.Div(id="sum-instcompare-card"),
        ], className="card-grid grid-2", style={"marginTop": "16px"}),

        # ---- Section 4 · Survival & damage ----
        _section("Survival & damage",
                 "Mortality (dead / replaced trees) by site and the most common damage agents."),
        html.Div([
            html.Div(id="sum-mort-card"),
            html.Div(id="sum-damage-card"),
        ], className="card-grid grid-2", style={"marginTop": "10px"}),
    ], id="pane-summary", style={"display": "none"})


def _map_pane():
    return html.Div([
        html.Div([
            html.Div([
                html.H3("RGT Installation Map", className="map-pane-title"),
                html.Span(
                    "Click a pin to fly in and see its plots · the globe button in the header closes the map",
                    className="map-pane-hint",
                ),
            ], className="map-pane-info"),
            html.Button(
                "⛶ Fullscreen", id="map-fs-btn", className="map-fs-btn", n_clicks=0,
                title="Expand the map to fill the whole screen (press Esc to exit)",
            ),
        ], className="map-pane-header"),
        html.Iframe(
            src="/assets/installations_map.html",
            id="map-iframe",
            style={
                "width": "100%",
                "height": "calc(100vh - 150px)",
                "border": "none",
                "borderRadius": "12px",
                "boxShadow": "0 2px 24px rgba(0,0,0,.14)",
            },
            **{"allow": "fullscreen"},
        ),
        # Store receives {installation, region} when user clicks "View in Dashboard"
        dcc.Store(id="map-click-store", data=None),
        dcc.Store(id="map-fs-store", data=None),
        # Interval polls window._rgt_selected (set by iframe) every 400 ms
        dcc.Interval(id="map-poll", interval=400, disabled=True),
    ], id="pane-map", style={"display": "none"})


def _assistant_widget():
    configured = CLIENT.configured
    status = ("Connected -- best model auto-selected" if configured
              else "Offline -- add MINDROUTER_API_KEY to .env and restart")
    welcome = (
        f"Hi, I'm **{ASSISTANT_NAME}**, IFC's report assistant.\n\n"
        "Start with **report** for a full write-up, or just ask a quick question.\n\n"
        "e.g. *report on installation HOODOO* · *what's the gain at HOODOO in Year 2?*"
    )
    fab = html.Button(
        [html.Span(className="fab-dot"), f" {ASSISTANT_NAME}"],
        id="assistant-fab", className="fab", title="Open the report assistant",
    )
    popup = html.Div([
        html.Div([
            html.Div([
                html.H5(ASSISTANT_NAME),
                html.P("IFC's Report Assistant", className="sub"),
            ]),
            html.Button("x", id="assistant-close", className="forestask-close",
                        title="Close", **{"aria-label": "Close assistant"}),
        ], className="forestask-head"),
        html.Div(
            [html.Button(s, id={"type": "chip", "index": i}, className="chip")
             for i, s in enumerate(SUGGESTIONS)],
            className="forestask-chips",
        ),
        html.Div(id="chat-log", className="chat-log", children=[
            html.Div([
                html.Div(ASSISTANT_NAME, className="who"),
                dcc.Markdown(welcome, className="bubble md"),
            ], className="msg assistant"),
        ]),
        # Pending area: optimistic user bubble + typing dots. Shown the instant a
        # message is sent and cleared when the server's reply lands -- managed by
        # two small clientside callbacks, no DOM hacking.
        html.Div([
            html.Div([
                html.Div("You", className="who"),
                html.Div(id="pending-user-bubble", className="bubble"),
            ], id="pending-user", className="msg user", style={"display": "none"}),
            html.Div([
                html.Div(ASSISTANT_NAME, className="who"),
                html.Div([html.Span(className="td"), html.Span(className="td"),
                          html.Span(className="td")], className="bubble typing",
                         **{"aria-label": ASSISTANT_NAME + " is typing"}),
            ], id="pending-typing", className="msg assistant typing-row",
               style={"display": "none"}),
        ], id="chat-pending"),
        html.Div(
            status, className="forestask-status",
            style={"color": (config.Color.POSITIVE if configured else config.Color.NEGATIVE)},
        ),
        html.Div([
            dcc.Textarea(id="chat-input",
                         placeholder="Ask for a report, e.g. 'report on HOODOO'...  (Enter to send)"),
            html.Button("Send", id="chat-send", className="btn btn-primary"),
        ], className="chat-input"),
        dcc.Store(id="chat-history", data=[]),
        dcc.Store(id="chat-outbox"),
    ], id="assistant-popup", className="forestask-popup closed")

    return html.Div([fab, popup], id="assistant-widget")


def _report_overlay():
    return html.Div([
        html.Div([
            html.Span("Generated report", className="report-bar-title"),
            html.Div([
                html.Button("Download (HTML)", id="report-dl-btn",
                            className="btn btn-ghost"),
                html.Button("✕ Close", id="report-close",
                            className="btn btn-ghost"),
            ], style={"display": "flex", "gap": "8px"}),
        ], className="report-bar"),
        # report-body holds the finished report; report-loading is the animation
        # overlay that stays mounted (so the film isn't cut off) until reveal.
        html.Div([
            html.Div(id="report-body", className="report-scroll"),
            html.Div(id="report-loading", className="report-loading"),
        ], className="report-stage"),
        dcc.Store(id="report-html"),
        dcc.Store(id="pending-report"),
        dcc.Download(id="report-dl"),
    ], id="report-view", className="report-overlay closed")


METHODS_MD = """
### What this dashboard shows
Realized genetic gain of **Improved** vs local **Woods Run** (unimproved) Douglas-fir across
two regions — **INW** (Inland Northwest) and **K-S** (Klamath–Siskiyou) — over three
measurement years and three growth metrics (caliper mm, height cm, volume cm³).

### Realized genetic gain
**Gain % = 100 × (Improved mean − Woods Run mean) / Woods Run mean**, per installation × year ×
metric. Positive means genetically improved stock grew faster (White, Adams & Neale 2007).

### Growth cohort
Growth means (and therefore gain) use **surviving original trees only** — trees coded *dead* or
*replacement* are excluded, so gain isn't confounded with the younger age of interplanted
replacements. **Mortality** is analysed separately and *does* count them.

### Significance
The unit of replication is the **seedlot (genetic-entry) mean**, not the individual tree (plots
are pseudo-replicates of source). A **Welch t-test** on seedlot means gives the p-value and a
95% CI on the difference; **Hedges g** is the effect size. Stars: `*` p<0.05, `**` p<0.01,
`***` p<0.001; `ns` = not significant.

### Multiple comparisons
The gain table runs one test per site, so the stars are a family of tests. Use the
**FDR-adjust (Benjamini–Hochberg)** toggle on the Summary tab to control the false-discovery
rate; the p column then shows the adjusted q-value.

### Gain vs site productivity
Regression of **absolute** gain (Improved − Woods, in metric units) on the Woods Run site mean (a
productivity proxy). Absolute — not % — because gain % carries the Woods Run mean in its
denominator and would bias the slope.

### Mortality & site type
Mortality = share of records coded `DEAD` / `DEAD (REPLACEMENT)`. **CORE** = main trial sites;
**TRANSFER** = off-site climate-transfer tests.

*A screening tool — for inference-grade conclusions, follow up with a mixed-effects model.*
"""


def _methods_modal():
    return html.Div(
        html.Div([
            html.Div([
                html.H5("Methods & definitions"),
                html.Button("✕", id="methods-close", className="modal-close",
                            title="Close", **{"aria-label": "Close methods"}),
            ], className="methods-head"),
            html.A("📖  Open the full User Manual  ↗",
                   href="/assets/RGT_User_Manual.html", target="_blank",
                   className="manual-link",
                   **{"aria-label": "Open the full user manual in a new tab"}),
            dcc.Markdown(METHODS_MD, className="methods-body md"),
        ], className="methods-card"),
        id="methods-modal", className="methods-modal closed",
    )


def _footer():
    return html.Div([
        html.Div([
            html.Img(src=UI_LOGO, alt="University of Idaho"),
            html.Span("Intermountain Forestry Cooperative, University of Idaho"),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px"}),
        html.Span("Realized Genetic Gain Trials dashboard - 2026"),
    ], className="footer")


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

def build_layout(store):
    hero = _compute_hero(store)
    return html.Div([
        dcc.Interval(id="boot", interval=250, n_intervals=0, max_intervals=1),
        dcc.Location(id="url", refresh=False),
        _topbar(hero),
        html.Div([
            _controls(store),
            dcc.Tabs(id="tabs", value="explorer", className="rgt-tabs", children=[
                dcc.Tab(label="Plot Explorer",          value="explorer",
                        className="tab", selected_className="tab--selected"),
                dcc.Tab(label="Genetic Gain & Summary", value="summary",
                        className="tab", selected_className="tab--selected"),
            ]),
            _explorer_pane(),
            _summary_pane(),
            _map_pane(),
        ], className="page"),
        _footer(),
        _assistant_widget(),
        _report_overlay(),
        _methods_modal(),
    ], id="parent")
