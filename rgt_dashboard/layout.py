# -*- coding: utf-8 -*-
"""
Page layout -- Modern Theme 2026.

Three main tabs (Plot Explorer, Genetic Gain & Summary, Installations Map)
live in the page; the report assistant is a floating "ForestTask" chat widget
(button bottom-right that opens a popup), available from any tab.
"""
from __future__ import annotations

from dash import dcc, html

from . import config
from .assistant import CLIENT
from .components import dropdown

IFC_LOGO = "https://ifc.nkn.uidaho.edu/static/img/ifc_logo_official.png"
UI_LOGO  = "https://nextsteps.idaho.gov/assets/uploads/2020/05/LOGO-UIdaho-2020.jpg"
ASSISTANT_NAME = "ForestTask"

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
                    ["🗺️", html.Span("Map", className="tb-label")],
                    id="topbar-map-btn", className="topbar-btn", n_clicks=0,
                    title="Open the installations map",
                ),
                html.Button(
                    "🌙", id="theme-toggle", className="topbar-btn theme-toggle",
                    n_clicks=0, title="Toggle light / dark theme",
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
                 label="Region"),
        dropdown("dd-installation", list(store.installations(config.DEFAULT_REGION)),
                 default_inst, label="Installation"),
        dropdown("dd-year",    years,
                 config.DEFAULT_YEAR   if config.DEFAULT_YEAR   in years   else years[0],
                 label="Year"),
        dropdown("dd-metric",  metrics,
                 config.DEFAULT_METRIC if config.DEFAULT_METRIC in metrics else metrics[0],
                 label="Metric"),
        html.Div(
            dropdown("dd-insttype", ["ALL", "CORE", "TRANSFER"], "CORE", label="Site Type"),
            id="insttype-wrap",
        ),
        html.P(
            "Region / Year / Metric / Site Type drive the Summary & Gain tab; "
            "Installation selects the site shown in Plot Explorer.",
            className="controls-note",
        ),
    ], className="controls")


def _explorer_pane():
    return html.Div([
        html.Div(id="exp-kpi", className="kpi-row"),
        html.Div([
            html.Span("Woods Run (plots 1-3)", className="legend-item",
                      style={"fontWeight": 700, "color": config.Color.WOODS}),
            html.Span("Improved (plots 4-6)", className="legend-item",
                      style={"fontWeight": 700, "color": config.Color.IMPROVED}),
        ], className="legend-row"),
        html.Div(id="exp-plots"),
        html.Div(id="exp-tables", className="card-grid grid-3",
                 style={"marginTop": "16px"}),
    ], id="pane-explorer")


def _summary_pane():
    return html.Div([
        html.Div(id="sum-kpi", className="kpi-row"),
        html.Div([
            html.Div(id="sum-gain-card"),
            html.Div(id="sum-prod-card"),
        ], className="card-grid grid-2", style={"marginTop": "8px"}),
        html.Div([
            html.Button("Download gain table (CSV)", id="dl-gain-btn",
                        className="btn btn-ghost"),
            html.Button("Download seedlot table (CSV)", id="dl-seedlot-btn",
                        className="btn btn-ghost"),
            dcc.Download(id="dl-gain"),
            dcc.Download(id="dl-seedlot"),
        ], style={"margin": "16px 0 4px", "display": "flex",
                  "gap": "8px", "justifyContent": "flex-end"}),
        html.Div(id="sum-table-card"),
        html.Div(id="sum-bars", className="card-grid grid-2",
                 style={"marginTop": "16px"}),
        html.Div([
            html.Div(id="sum-box-card"),
            html.Div(id="sum-instcompare-card"),
        ], className="card-grid grid-2", style={"marginTop": "16px"}),
    ], id="pane-summary", style={"display": "none"})


def _map_pane():
    return html.Div([
        html.Div([
            html.Div([
                html.H3("RGT Installation Map", className="map-pane-title"),
                html.P(
                    "18 installations across INW (Idaho/Washington) and K-S (Oregon) regions. "
                    "Click a pin to view realized gain data, then 'View in Dashboard' to explore.",
                    className="map-pane-sub",
                ),
            ], className="map-pane-info"),
        ], className="map-pane-header"),
        html.Iframe(
            src="/assets/installations_map.html",
            id="map-iframe",
            style={
                "width": "100%",
                "height": "calc(100vh - 230px)",
                "border": "none",
                "borderRadius": "12px",
                "boxShadow": "0 2px 24px rgba(0,0,0,.14)",
            },
        ),
        # Store receives {installation, region} when user clicks "View in Dashboard"
        dcc.Store(id="map-click-store", data=None),
        # Interval polls window._rgt_selected (set by iframe) every 400 ms
        dcc.Interval(id="map-poll", interval=400, disabled=True),
    ], id="pane-map", style={"display": "none"})


def _assistant_widget():
    configured = CLIENT.configured
    status = ("Connected -- best model auto-selected" if configured
              else "Offline -- add MINDROUTER_API_KEY to .env and restart")
    welcome = (
        f"Hi, I'm **{ASSISTANT_NAME}** -- IFC's Report Assistant. Two ways to use me:\n\n"
        "**📄 Reports** — start with *report* (or pick a chip below). I open the panel on "
        "the right, play a short build animation, and produce a full document with charts, "
        "tables and written analysis. Takes ~1-2 min. e.g. *report on installation HOODOO*, "
        "*deployment report for CORE sites*, *report comparing INW vs K-S*.\n\n"
        "**💬 Quick questions** — ask anything short for an instant inline answer, or say "
        "*plot the gains* for a quick chart. e.g. *what's the gain at HOODOO in Year 2?*"
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
                        title="Close"),
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
                html.Button("Skip to report →", id="report-skip",
                            className="btn btn-primary", style={"display": "none"}),
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
        dcc.Store(id="film-ready-bridge"),
        dcc.Download(id="report-dl"),
    ], id="report-view", className="report-overlay closed")


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
    ], id="parent")
