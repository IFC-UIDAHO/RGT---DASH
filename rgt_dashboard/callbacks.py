# -*- coding: utf-8 -*-
"""
All Dash callbacks, registered on the app via :func:`register`.

Three data panels live in the page (toggled by ``_toggle``); the report
assistant is a floating ForestTask popup. The map tab uses a clientside
callback to poll for pin clicks from the embedded Leaflet iframe.
"""
from __future__ import annotations

import functools
import json
import logging
import math
import time
import uuid
from urllib.parse import urlencode, parse_qs

import pandas as pd
from dash import Input, Output, State, dcc, html, no_update
from dash.dependencies import ALL
from dash.exceptions import PreventUpdate

from . import config, figures as F, report as RPT, stats
from . import components as C
from .assistant import CLIENT, auto_model, build_messages
from .config import Color
from .layout import SUGGESTIONS, ASSISTANT_NAME

logger = logging.getLogger("rgt.callbacks")

GRAPH_CONFIG = {"displaylogo": False, "displayModeBar": "hover",
                "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
                "toImageButtonOptions": {"format": "png", "scale": 2}}
CHAT_GRAPH_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}

_GAIN_CACHE: dict = {}


def _gain_df(store, region, year, metric, inst_type):
    key = (region or "", year, metric, inst_type)
    if key not in _GAIN_CACHE:
        _GAIN_CACHE[key] = stats.gain_by_installation(
            store, region=region, year=year, metric=metric, inst_type=inst_type)
    return _GAIN_CACHE[key]


def _error_card(err_id, where=""):
    """User-facing error card. Shows a short reference id only -- the full
    traceback is logged server-side, never rendered to the browser."""
    where_txt = f" in {where}" if where else ""
    return html.Div([
        html.Div(f"This panel couldn't load{where_txt}.",
                 style={"fontWeight": 700, "color": Color.NEGATIVE, "marginBottom": "6px"}),
        html.Div("Try a different Region, Year, or Metric. If it keeps happening, "
                 "send this reference to the maintainer:",
                 style={"fontSize": "12px", "color": Color.INK, "marginBottom": "8px"}),
        html.Code(f"error {err_id}", style={
            "fontSize": "12px", "background": Color.SURFACE_ALT, "padding": "3px 8px",
            "borderRadius": "6px", "border": f"1px solid {Color.BORDER}", "color": Color.MUTED}),
    ], className="chart-card", style={"padding": "14px"})


def _safe(n_outputs, where=""):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except PreventUpdate:
                raise
            except Exception:
                # Log the full traceback server-side under a short id; show the
                # user only the id -- never the stack trace.
                err_id = uuid.uuid4().hex[:8]
                logger.exception("Panel error [%s]%s", err_id,
                                 f" in {where}" if where else "")
                card = _error_card(err_id, where)
                if n_outputs == 1:
                    return card
                return tuple([card] + [html.Div() for _ in range(n_outputs - 1)])
        return wrapper
    return deco


def _graph(fig, height):
    return dcc.Graph(figure=fig, config=GRAPH_CONFIG, style={"height": f"{height}px"})


def _fmt(x, pct=False, plus=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    s = f"{x:+.1f}" if plus else f"{x:.1f}"
    return s + ("%" if pct else "")


# --------------------------------------------------------------------------- #
# Shareable view state <-> URL query string
# --------------------------------------------------------------------------- #
def _state_to_search(region, installation, year, metric, inst_type, tab, fdr) -> str:
    params = {}
    if region:       params["region"] = region
    if installation: params["inst"] = installation
    if year:         params["year"] = year
    if metric:       params["metric"] = metric
    if inst_type:    params["type"] = inst_type
    if tab:          params["tab"] = tab
    if fdr and "fdr" in fdr:
        params["fdr"] = "1"
    return ("?" + urlencode(params)) if params else ""


def _search_to_state(search):
    q = parse_qs((search or "").lstrip("?"))

    def g(k):
        v = q.get(k)
        return v[0] if v else None

    fdr = ["fdr"] if g("fdr") == "1" else []
    return g("region"), g("inst"), g("year"), g("metric"), g("type"), g("tab"), fdr


# =========================================================================== #
def register(app, store):

    # ---- tab visibility toggle (panels + site-type + map poll) ------------- #
    @app.callback(
        Output("pane-explorer",  "style"),
        Output("pane-summary",   "style"),
        Output("pane-map",       "style"),
        Output("insttype-wrap",  "style"),
        Output("installation-wrap", "style"),
        Output("map-poll",       "disabled"),
        Input("tabs", "value"),
    )
    def _toggle(tab):
        hide = {"display": "none"}
        # Dim (don't remove) controls that don't drive the active tab so their
        # value survives a tab switch. Installation drives only Plot Explorer;
        # Site Type drives only the Summary tab. The map is opened by the globe
        # button in the topbar (tab == "map"), not a visible tab.
        dim = {"opacity": 0.4, "pointerEvents": "none"}
        return (
            {} if tab == "explorer" else hide,
            {} if tab == "summary" else hide,
            {} if tab == "map"     else hide,
            {} if tab == "summary" else hide,   # Site Type
            {} if tab == "explorer" else dim,   # Installation
            tab != "map",   # enable the map poll only while the map is open
        )

    # ---- Shareable links: keep the URL in sync with the view, and restore a
    #      deep-linked view once at load. -----------------------------------=- #
    @app.callback(
        Output("url", "search"),
        Input("dd-region", "value"), Input("dd-installation", "value"),
        Input("dd-year", "value"), Input("dd-metric", "value"),
        Input("dd-insttype", "value"), Input("tabs", "value"),
        Input("fdr-toggle", "value"),
        prevent_initial_call=True,
    )
    def _sync_url(region, installation, year, metric, inst_type, tab, fdr):
        return _state_to_search(region, installation, year, metric, inst_type, tab, fdr)

    @app.callback(
        Output("dd-region", "value", allow_duplicate=True),
        Output("dd-installation", "value", allow_duplicate=True),
        Output("dd-year", "value", allow_duplicate=True),
        Output("dd-metric", "value", allow_duplicate=True),
        Output("dd-insttype", "value", allow_duplicate=True),
        Output("tabs", "value", allow_duplicate=True),
        Output("fdr-toggle", "value", allow_duplicate=True),
        Input("boot", "n_intervals"),
        State("url", "search"),
        prevent_initial_call=True,
    )
    def _apply_url(_boot, search):
        if not search:
            raise PreventUpdate
        region, inst, year, metric, itype, tab, fdr = _search_to_state(search)
        if not any([region, inst, year, metric, itype, tab]):
            raise PreventUpdate
        if tab not in ("explorer", "summary", "map"):   # ignore stale/removed tabs
            tab = None
        # Missing params fall back to whatever the dropdowns already hold.
        return (region or no_update, inst or no_update, year or no_update,
                metric or no_update, itype or no_update, tab or no_update, fdr)

    # ---- clientside: poll window._rgt_selected (set by map iframe) --------- #
    app.clientside_callback(
        """
        function(n) {
            try {
                var sel = window._rgt_selected;
                if (!sel) return window.dash_clientside.no_update;
                var ts = sel._ts || 0;
                if (window._rgt_last_ts && ts <= window._rgt_last_ts)
                    return window.dash_clientside.no_update;
                window._rgt_last_ts = ts;
                return {installation: sel.installation, region: sel.region};
            } catch(e) {
                return window.dash_clientside.no_update;
            }
        }
        """,
        Output("map-click-store", "data"),
        Input("map-poll", "n_intervals"),
    )

    # ---- map pin click -> switch to explorer + sync region ----------------- #
    @app.callback(
        Output("dd-region", "value"),
        Output("tabs", "value"),
        Input("map-click-store", "data"),
        prevent_initial_call=True,
    )
    def _from_map_click(data):
        if not data or not isinstance(data, dict):
            raise PreventUpdate
        region = data.get("region") or config.DEFAULT_REGION
        return region, "explorer"

    # ---- topbar map icon -> TOGGLE the Installations Map ------------------- #
    app.clientside_callback(
        "function(n, cur){ if(!n) return window.dash_clientside.no_update;"
        " return cur === 'map' ? 'explorer' : 'map'; }",
        Output("tabs", "value", allow_duplicate=True),
        Input("topbar-map-btn", "n_clicks"),
        State("tabs", "value"),
        prevent_initial_call=True,
    )

    # ---- ForestTask popup open/close --------------------------------------- #
    @app.callback(
        Output("assistant-popup", "className"),
        Output("assistant-fab", "style"),
        Input("assistant-fab", "n_clicks"),
        Input("assistant-close", "n_clicks"),
        State("assistant-popup", "className"),
        prevent_initial_call=True,
    )
    def _toggle_assistant(_fab, _close, cls):
        from dash import callback_context as ctx
        is_open = "open" in (cls or "")
        open_ = False if ctx.triggered_id == "assistant-close" else (not is_open)
        return ("forestask-popup open" if open_ else "forestask-popup closed",
                {"display": "none"} if open_ else {})

    # ---- Methods & definitions modal open/close ---------------------------- #
    @app.callback(
        Output("methods-modal", "className"),
        Input("methods-btn", "n_clicks"),
        Input("methods-close", "n_clicks"),
        State("methods-modal", "className"),
        prevent_initial_call=True,
    )
    def _toggle_methods(_open, _close, cls):
        from dash import callback_context as ctx
        is_open = "open" in (cls or "")
        open_ = False if ctx.triggered_id == "methods-close" else (not is_open)
        return "methods-modal open" if open_ else "methods-modal closed"

    # ---- dependent installation dropdown ---------------------------------- #
    @app.callback(
        Output("dd-installation", "options"),
        Output("dd-installation", "value"),
        Input("dd-region", "value"),
        State("dd-installation", "value"),
        State("map-click-store", "data"),
    )
    def _installs(region, current, map_click):
        if not region:
            return [], None
        insts = list(store.installations(region))
        opts = [{"label": i, "value": i} for i in insts]
        # Map pin click: pre-select the requested installation
        if map_click and isinstance(map_click, dict):
            desired = map_click.get("installation")
            if desired and desired in insts:
                return opts, desired
        if current in insts:
            value = current
        else:
            value = config.REGION_DEFAULT_INSTALLATION.get(region) or (insts[0] if insts else None)
            if value not in insts and insts:
                value = insts[0]
        return opts, value

    # ====================================================================== #
    # PLOT EXPLORER
    # ====================================================================== #
    @app.callback(
        Output("exp-kpi", "children"),
        Output("exp-plots", "children"),
        Output("exp-tables", "children"),
        Input("boot", "n_intervals"),
        Input("dd-region", "value"),
        Input("dd-installation", "value"),
        Input("dd-year", "value"),
        Input("dd-metric", "value"),
    )
    @_safe(3, "Plot Explorer")
    def _explorer(_boot, region, installation, year, metric):
        if not all([region, installation, year, metric]):
            raise PreventUpdate

        trees = store.trees(region=region, installation=installation, year=year, metric=metric)
        res = stats.compare_sources(store, region=region, installation=installation,
                                    year=year, metric=metric)
        unit = config.METRICS.get(metric, {}).get("unit", "")

        if res is None or trees["Value"].notna().sum() == 0:
            kpis = [C.kpi("Status", "No data", f"{installation} · {year}", Color.NEUTRAL)]
            empty = _graph(F.empty_fig(f"No {metric.title()} measurements at "
                                       f"{installation} in {year}.", 260), 260)
            return kpis, empty, [html.Div()]

        gain_accent = (Color.POSITIVE if (res.gain_pct or 0) >= 0 else Color.NEGATIVE)
        kpis = [
            C.kpi("Woods Run mean", f"{res.woods_mean:.1f} {unit}",
                  f"{res.n_woods_entries} seedlots · {res.n_woods_trees} trees", Color.WOODS),
            C.kpi("Improved mean", f"{res.improved_mean:.1f} {unit}",
                  f"{res.n_improved_entries} seedlots · {res.n_improved_trees} trees", Color.IMPROVED),
            C.kpi("Realized gain", _fmt(res.gain_pct, pct=True, plus=True),
                  f"{_fmt(res.gain_abs, plus=True)} {unit}  ·  Hedges g {_fmt(res.hedges_g)}",
                  gain_accent),
            C.kpi("Significance", res.stars or "ns",
                  f"p = {res.p_value:.3f}" if not math.isnan(res.p_value) else "n/a · small sample",
                  Color.NAVY),
        ]

        zmin = float(trees["Value"].min())
        zmax = float(trees["Value"].max())
        cards = []
        for plot in range(1, 7):
            src = config.PLOT_SOURCE_MAP.get(plot, "")
            sub = trees[trees["PLOT"] == plot]
            fig = F.heatmap(sub, zmin=zmin, zmax=zmax, height=250)
            cards.append(C.chart_card(f"{src} · Plot {plot}", _graph(fig, 250),
                                      info=f"{src} seedlots, replication x seedlot growth"))
        plots = html.Div(cards, className="card-grid grid-3")

        woods_p = store.plots(region=region, installation=installation, year=year,
                              metric=metric, source=config.SOURCE_WOODS)
        imp_p = store.plots(region=region, installation=installation, year=year,
                            metric=metric, source=config.SOURCE_IMPROVED)
        com = store.plots(region=region, installation=installation, year=year, metric=metric)

        tables = [
            C.chart_card("Woods Run -- mean by plot", _mean_table(woods_p), info="Per-seedlot plot means"),
            C.chart_card("Improved -- mean by plot",  _mean_table(imp_p),   info="Per-seedlot plot means"),
            C.chart_card("Avg / Max / Min by seedlot",
                         _graph(F.avg_max_min(com, metric=metric, height=300), 300),
                         info="Marker = seedlot mean; whiskers = plot max/min"),
        ]
        return kpis, plots, tables

    # ---- Deployment decision (per installation, across years & metrics) ---- #
    @app.callback(
        Output("exp-deploy", "children"),
        Input("dd-region", "value"),
        Input("dd-installation", "value"),
    )
    @_safe(1, "Deployment call")
    def _deploy(region, installation):
        if not region or not installation:
            raise PreventUpdate
        dc = stats.deployment_call(store, region=region, installation=installation)
        return _deploy_card(dc)

    # ====================================================================== #
    # SUMMARY & GENETIC GAIN
    # ====================================================================== #
    @app.callback(
        Output("sum-kpi", "children"),
        Output("sum-gain-card", "children"),
        Output("sum-prod-card", "children"),
        Output("sum-table-card", "children"),
        Output("sum-bars", "children"),
        Output("sum-box-card", "children"),
        Output("sum-instcompare-card", "children"),
        Output("sum-mort-card", "children"),
        Output("sum-damage-card", "children"),
        Input("boot", "n_intervals"),
        Input("dd-region", "value"),
        Input("dd-year", "value"),
        Input("dd-metric", "value"),
        Input("dd-insttype", "value"),
        Input("fdr-toggle", "value"),
    )
    @_safe(9, "Genetic Gain & Summary")
    def _summary(_boot, region, year, metric, inst_type, fdr):
        if not all([region, year, metric, inst_type]):
            raise PreventUpdate

        gdf = _gain_df(store, region, year, metric, inst_type)
        fdr_on = bool(fdr and "fdr" in fdr)
        if fdr_on:                       # multiplicity-controlled significance
            gdf = stats.apply_fdr(gdf)
        rel = stats.productivity_relationship(gdf)
        unit = config.METRICS.get(metric, {}).get("unit", "")

        if gdf.empty:
            empty = _graph(F.empty_fig("No installations with data for this filter", 380), 380)
            kpis = [C.kpi("Sites", "0", f"{region} · {year}", Color.NEUTRAL)]
            blank = C.chart_card("--", empty)
            return (kpis, blank, C.chart_card("--", empty), html.Div(),
                    [html.Div(), html.Div()], C.chart_card("--", empty),
                    C.chart_card("--", empty), C.chart_card("--", empty),
                    C.chart_card("--", empty))

        valid = gdf["gain_pct"].dropna()
        mean_gain = valid.mean() if not valid.empty else float("nan")
        n_sig = int(gdf["significant"].sum())
        rtxt = (f"r = {rel['r']:+.2f}, p = {rel['p']:.2f}" if rel.get("n", 0) >= 3
                and not math.isnan(rel.get("r", float("nan"))) else "n/a")
        kpis = [
            C.kpi("Installations", f"{len(gdf)}", f"{region} · {year} · {inst_type}", Color.NAVY),
            C.kpi("Mean realized gain", _fmt(mean_gain, pct=True, plus=True),
                  f"median {_fmt(valid.median() if not valid.empty else None, pct=True, plus=True)}",
                  Color.POSITIVE if (mean_gain or 0) >= 0 else Color.NEGATIVE),
            C.kpi("Significant sites", f"{n_sig} / {len(gdf)}",
                  "q < 0.05 (BH-FDR)" if fdr_on else "p < 0.05 (Welch)", Color.GOLD_INK),
            C.kpi("Gain vs productivity", rtxt,
                  "negative => gain falls on better sites" if rel.get("slope", 0) < 0
                  else "positive => gain rises on better sites", Color.NAVY),
        ]

        gh = min(620, max(420, 22 * len(gdf) + 130))
        gain_card = C.chart_card(
            f"Woods Run → Improved by site -- {config.METRICS.get(metric, {}).get('short','')} ({year})",
            _graph(F.gain_dumbbell(gdf, metric=metric, height=gh), gh),
            info="Each line pairs a site's Woods Run and Improved means. "
                 "Green = positive realized gain, red = negative, gold ring = significant (p<0.05). "
                 "Grey whisker = 95% CI of the gain; if it reaches back across the Woods Run dot, "
                 "the gain isn't significant.")
        prod_card = C.chart_card(
            "Genetic gain vs site productivity",
            _graph(F.gain_vs_productivity(gdf, rel, metric=metric, height=420), 420),
            info="Does realized gain change with site quality? Y-axis is absolute gain "
                 "(Improved − Woods Run), which avoids the denominator bias of regressing "
                 "gain % on the Woods Run mean.")

        disp = gdf[["installation", "inst_type", "woods_mean", "improved_mean",
                    "gain_pct", "stars", "p_value", "woods_mortality", "improved_mortality"]].copy()
        pcol = "q (FDR)" if fdr_on else "p"
        disp.columns = ["Installation", "Type", f"Woods ({unit})", f"Improved ({unit})",
                        "Gain %", "Sig.", pcol, "Woods mort.%", "Imp. mort.%"]
        disp[pcol] = disp[pcol].apply(lambda v: "--" if pd.isna(v) else f"{v:.3f}")
        gain_table = C.chart_card(
            "Site-by-site genetic gain & survival",
            C.data_table(disp, table_id="tbl-summary", height="300px",
                         numeric_cols=[f"Woods ({unit})", f"Improved ({unit})", "Gain %",
                                       "Woods mort.%", "Imp. mort.%"],
                         gain_col="Gain %", filter_=True),
            info="Realized gain plus survival per site. Gain % is coloured by sign. "
                 "Growth means use surviving trees only (dead/replacement excluded); "
                 "mortality counts them.")

        sl = store.seedlots(region=region, year=year, metric=metric, inst_type=inst_type)
        sl = sl[["Installation", "Source", "Seedlot", "Average", "Standard error",
                 "Mortality %"]].copy()
        sl.columns = ["Installation", "Source", "Seedlot", f"Mean ({unit})", "Std error", "Mortality %"]
        sl = sl.sort_values(["Installation", "Source", "Seedlot"]).round(2)
        seedlot_table = C.chart_card(
            "Per-seedlot means & mortality",
            C.data_table(sl, table_id="tbl-seedlot", height="320px", page_size=12,
                         numeric_cols=[f"Mean ({unit})", "Std error", "Mortality %"], filter_=True),
            info="Mean growth, standard error and mortality % for every seedlot in the current view.")

        table_card = html.Div([gain_table, seedlot_table], style={"display": "grid", "gap": "16px"})

        plots_all = store.plots(region=region, year=year, metric=metric, inst_type=inst_type)
        insts = sorted(plots_all["Installation"].unique())
        cmap = C.build_colour_map(insts)
        ymax = plots_all["Overall Avg"].max() if not plots_all.empty else None
        bars = [
            C.chart_card("Woods Run -- seedlot means by site",
                         _graph(F.seedlot_bars(plots_all, source=config.SOURCE_WOODS,
                                inst_order=insts, colour_map=cmap, ymax=ymax,
                                metric=metric, height=360), 360)),
            C.chart_card("Improved -- seedlot means by site",
                         _graph(F.seedlot_bars(plots_all, source=config.SOURCE_IMPROVED,
                                inst_order=insts, colour_map=cmap, ymax=ymax,
                                metric=metric, height=360), 360)),
        ]

        trees_all = store.trees(region=region, year=year, metric=metric,
                                inst_type=inst_type, living_only=True)
        box_card = C.chart_card("Distribution of tree growth by seedlot",
                                _graph(F.seedlot_box(trees_all, metric=metric, height=420), 420),
                                info="Box = IQR, whiskers 1.5xIQR, points = outliers")
        inst_df = store.installations_summary(region=region, year=year, metric=metric,
                                              inst_type=inst_type)
        comp_card = C.chart_card("Installation means -- Woods Run vs Improved (+-SE)",
                                 _graph(F.installation_comparison(inst_df, metric=metric,
                                        height=420), 420))

        # Survival & damage -- ALL trees (incl. dead) so each tree counts once.
        surv = store.trees(region=region, year=year, metric=metric, inst_type=inst_type)
        mort_card = C.chart_card(
            "Mortality by site -- Woods Run vs Improved",
            _graph(F.mortality_by_site(surv, height=440), 440),
            info="Share of trees coded dead / replaced, per installation. Lower is better.")
        damage_card = C.chart_card(
            "Top damage agents by source",
            _graph(F.damage_agents(surv, height=440), 440),
            info="Most common defect codes as a % of each source's trees "
                 "(browse, frost, herbicide, unhealthy, etc.).")
        return (kpis, gain_card, prod_card, table_card, bars, box_card, comp_card,
                mort_card, damage_card)

    # ---- CSV export -------------------------------------------------------- #
    @app.callback(
        Output("dl-gain", "data"),
        Input("dl-gain-btn", "n_clicks"),
        State("dd-region", "value"), State("dd-year", "value"),
        State("dd-metric", "value"), State("dd-insttype", "value"),
        State("fdr-toggle", "value"),
        prevent_initial_call=True,
    )
    def _download(n, region, year, metric, inst_type, fdr):
        if not n:
            raise PreventUpdate
        gdf = _gain_df(store, region, year, metric, inst_type)
        fdr_on = bool(fdr and "fdr" in fdr)
        if fdr_on:                       # export matches the on-screen FDR view (adds p_raw + q)
            gdf = stats.apply_fdr(gdf)
        tag = "_FDR" if fdr_on else ""
        fname = f"rgt_gain_{region}_{year}_{config.METRICS.get(metric,{}).get('short','metric')}_{inst_type}{tag}.csv"
        return dcc.send_data_frame(gdf.to_csv, fname.replace(" ", ""), index=False)

    # ---- per-seedlot table download --------------------------------------- #
    @app.callback(
        Output("dl-seedlot", "data"),
        Input("dl-seedlot-btn", "n_clicks"),
        State("dd-region", "value"), State("dd-year", "value"),
        State("dd-metric", "value"), State("dd-insttype", "value"),
        prevent_initial_call=True,
    )
    def _download_seedlot(n, region, year, metric, inst_type):
        if not n:
            raise PreventUpdate
        sl = store.seedlots(region=region, year=year, metric=metric, inst_type=inst_type)
        cols = ["Installation", "Source", "Seedlot", "Average", "Standard error", "Mortality %"]
        sl = sl[[c for c in cols if c in sl.columns]]
        short = config.METRICS.get(metric, {}).get("short", "metric")
        fname = f"rgt_seedlots_{region}_{year}_{short}_{inst_type}.csv".replace(" ", "")
        return dcc.send_data_frame(sl.to_csv, fname, index=False)

    # ====================================================================== #
    # FORESTTASK  (chat, charts, and full report generation)
    # ====================================================================== #
    # Clear the chat box the instant Send/Enter is pressed: a clientside callback
    # captures the text into a store (with a timestamp so repeats still fire) and
    # blanks the input. The server callback below reads the store, not the input.
    app.clientside_callback(
        "function(n, val){"
        "  if(!n || !val || !val.trim()) return [window.dash_clientside.no_update, window.dash_clientside.no_update];"
        "  return [{t: val, ts: Date.now()}, '']; }",
        Output("chat-outbox", "data"),
        Output("chat-input", "value", allow_duplicate=True),
        Input("chat-send", "n_clicks"),
        State("chat-input", "value"),
        prevent_initial_call=True,
    )

    # Pending area: show the user's bubble + typing dots the instant a message is
    # sent (chat-outbox changes), then clear them when the reply lands (chat-log
    # children change). Two tiny clientside callbacks -- no DOM manipulation.
    app.clientside_callback(
        "function(outbox){"
        "  var no = window.dash_clientside.no_update;"
        "  if(!outbox || !outbox.t || !outbox.t.trim()) return [no, no, no];"
        "  var show = {display: 'flex'};"
        "  return [outbox.t, show, show]; }",
        Output("pending-user-bubble", "children"),
        Output("pending-user", "style"),
        Output("pending-typing", "style"),
        Input("chat-outbox", "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        "function(_children){ var hide = {display: 'none'}; return [hide, hide]; }",
        Output("pending-user", "style", allow_duplicate=True),
        Output("pending-typing", "style", allow_duplicate=True),
        Input("chat-log", "children"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("chat-history", "data"),
        Output("chat-log", "children"),
        Output("chat-input", "value"),
        Output("report-view", "className"),
        Output("pending-report", "data"),
        Output("report-loading", "children", allow_duplicate=True),
        Output("report-html", "data", allow_duplicate=True),
        Output("report-body", "children", allow_duplicate=True),
        Input("chat-outbox", "data"),
        Input({"type": "chip", "index": ALL}, "n_clicks"),
        State("chat-history", "data"),
        State("dd-region", "value"), State("dd-year", "value"),
        State("dd-metric", "value"), State("dd-insttype", "value"),
        prevent_initial_call=True,
    )
    def _chat(outbox, chip_clicks, history, region, year, metric, inst_type):
        from dash import callback_context as ctx
        trig = ctx.triggered_id
        if trig is None:
            raise PreventUpdate
        is_chip = isinstance(trig, dict) and trig.get("type") == "chip"
        if is_chip:
            if not chip_clicks or not any(chip_clicks):
                raise PreventUpdate
            prompt = SUGGESTIONS[trig["index"]]
        else:
            prompt = ((outbox or {}).get("t") if isinstance(outbox, dict)
                      else (outbox or "")).strip()
        if not prompt:
            raise PreventUpdate

        history = list(history or [])
        history.append({"role": "user", "content": prompt})
        # report-view, pending-report, report-loading, report-html, report-body
        NU = (no_update,) * 5

        # ---- REPORT request -> immediately open overlay with animation ------
        # A quick-prompt chip is always a report; otherwise detect report intent.
        if is_chip or _is_report_request(prompt):
            spec = RPT.parse_request(prompt, store)
            note = (f"Generating your **{spec.title}** -- "
                    "this usually takes 20-60 seconds with maximum reasoning. "
                    "The report will appear in the panel to the right when ready.")
            history.append({"role": "assistant", "content": note})
            # cache-bust the src so the film RELOADS (replays from 0) every
            # request instead of freezing on the previous report's end-state
            loading_anim = html.Iframe(
                src=f"/assets/forest_loading.html?t={int(time.time() * 1000)}",
                style={"width": "100%", "height": "100%", "border": "none",
                       "minHeight": "380px"},
            )
            # also clear the previous report (html + body) so no stale
            # "ready"/old report can show through on the new request
            return (history, _render_chat(history), "", "report-overlay open",
                    prompt, loading_anim, None, html.Div())

        # ---- chart request ----
        if _wants_chart(prompt):
            chart, caption = _build_chart(store, prompt, region, year, metric, inst_type)
            if chart is not None:
                history.append({"role": "assistant", "chart": chart, "caption": caption})
            else:
                history.append({"role": "assistant", "content": caption})
            return (history, _render_chat(history), "") + NU

        # ---- text answer grounded in current view + trial overview ----
        summary = stats.summarize_for_llm(store, region=region, year=year,
                                          metric=metric, inst_type=inst_type)
        api_history = []
        for m in history:
            if m.get("error"):
                continue
            if m.get("chart"):
                api_history.append({"role": "assistant", "content": m.get("caption", "[chart shown]")})
            elif m.get("content") is not None:
                api_history.append({"role": m["role"], "content": m["content"]})
        context = {"current_view": summary, "trial_overview": stats.trial_overview(store)}
        result = CLIENT.chat(build_messages(api_history, context), model=auto_model(prompt))
        if result["ok"]:
            history.append({"role": "assistant", "content": result["content"]})
        else:
            history.append({"role": "assistant", "content": result["error"], "error": True})
        return (history, _render_chat(history), "") + NU

    # ---- deferred report build (triggered when pending-report is set) ------
    @app.callback(
        Output("report-body", "children", allow_duplicate=True),
        Output("report-html", "data"),
        Input("pending-report", "data"),
        prevent_initial_call=True,
    )
    @_safe(2, "report builder")
    def _build_report(prompt):
        if not prompt:
            raise PreventUpdate
        spec = RPT.parse_request(prompt, store)
        rep = RPT.build_report(spec, store, CLIENT)
        return RPT.to_components(rep), RPT.to_html(rep)

    # ---- report download + close ----
    @app.callback(
        Output("report-dl", "data"),
        Input("report-dl-btn", "n_clicks"),
        State("report-html", "data"),
        prevent_initial_call=True,
    )
    def _report_dl(n, html_str):
        if not n or not html_str:
            raise PreventUpdate
        return dict(content=html_str, filename="RGT_report.html")

    @app.callback(
        Output("report-view", "className", allow_duplicate=True),
        Input("report-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def _report_close(n):
        return "report-overlay closed"

    # ---- SINGLE reveal path: the instant the report is built (report-html is
    #      set), drop the film overlay and show the report. This one callback is
    #      now the ONLY reveal mechanism -- the old film postMessage handshake,
    #      the Skip button, loadbridge.js and the theme.js listener were
    #      redundant routes to the same outcome and have been removed. --------- #
    @app.callback(
        Output("report-view", "className", allow_duplicate=True),
        Input("report-html", "data"),
        prevent_initial_call=True,
    )
    def _auto_reveal(report_html):
        if not report_html:
            raise PreventUpdate
        return "report-overlay open revealed"


# --------------------------------------------------------------------------- #
# chart-from-chat helpers
# --------------------------------------------------------------------------- #
_CHART_WORDS = ("plot", "chart", "graph", "visualis", "visualiz", "scatter",
                "bar chart", "figure", "draw ", "show me a")


def _wants_chart(prompt: str) -> bool:
    p = (prompt or "").lower()
    return any(w in p for w in _CHART_WORDS)


# A "report" = a full deliverable (charts + tables + written analysis), rendered
# in the panel with the loading film. Anything else short is answered inline.
_REPORT_WORDS = ("report", "deploy", "deployment", "should we", "recommend",
                 "summary", "summarise", "summarize", "assessment", "assess",
                 "evaluate", "evaluation", "safest bet", "stability", "g×e", "gxe",
                 "best and worst", "across all", "full analysis", "write-up", "writeup")


def _is_report_request(prompt: str) -> bool:
    """True when the user wants a full report (opens the report panel), not a quick
    chat answer. Triggers on explicit report words, or a clear comparison."""
    p = (prompt or "").lower()
    if any(w in p for w in _REPORT_WORDS):
        return True
    return ("compare" in p or " vs " in p or " versus " in p)


def _build_chart(store, prompt, region, year, metric, inst_type):
    p = (prompt or "").lower()
    short = config.METRICS.get(metric, {}).get("short", "")
    tag = f"{region}, {year}, {short}, {inst_type}"
    gdf = _gain_df(store, region, year, metric, inst_type)
    if gdf is None or gdf.empty:
        return None, ("There's no data to plot for the current filters -- try a different "
                      "Year or Site type on the Summary tab, then ask again.")
    if "scatter" in p or "productivit" in p or "relationship" in p:
        rel = stats.productivity_relationship(gdf)
        fig = F.gain_vs_productivity(gdf, rel, metric=metric, height=320)
        cap = f"**Gain vs site productivity** -- {tag}."
    elif "box" in p or "distribution" in p or "spread" in p:
        trees = store.trees(region=region, year=year, metric=metric,
                            inst_type=inst_type, living_only=True)
        fig = F.seedlot_box(trees, metric=metric, height=320)
        cap = f"**Tree-growth distribution by seedlot** -- {tag}."
    else:
        fig = F.gain_chart(gdf, metric=metric, height=340)
        v = gdf.dropna(subset=["gain_pct"])
        lead = ""
        if not v.empty:
            top, bot = v.iloc[0], v.iloc[-1]
            lead = (f" {top['installation']} leads at {top['gain_pct']:+.1f}%; "
                    f"{bot['installation']} is lowest at {bot['gain_pct']:+.1f}%.")
        cap = f"**Realized genetic gain by site** -- {tag}.{lead}"
    return json.loads(fig.to_json()), cap


def _mean_table(plot_df_source):
    if plot_df_source is None or plot_df_source.empty:
        return html.Div("No data", style={"padding": "20px", "color": Color.MUTED,
                                          "textAlign": "center"})
    plot_cols = [c for c in plot_df_source.columns
                 if c.startswith("Plot ") and plot_df_source[c].notna().any()]
    cols = ["Seedlot"] + plot_cols + (["Overall Avg"] if "Overall Avg" in plot_df_source else [])
    d = plot_df_source[cols].sort_values("Seedlot")
    return C.data_table(d, height="300px", numeric_cols=plot_cols + ["Overall Avg"])


_DEPLOY_COLORS = {"deploy": Color.POSITIVE, "caution": Color.GOLD_INK,
                  "hold": Color.NEGATIVE, "none": Color.NEUTRAL}


def _deploy_card(dc):
    """Render the deployment verdict + the evidence it rests on."""
    color = _DEPLOY_COLORS.get(dc["level"], Color.NEUTRAL)
    items = []
    for d in dc["per_metric"]:
        sig = d["stars"] if d["stars"] and d["stars"] != "ns" else "n.s."
        gain_col = Color.POSITIVE if d["gain_pct"] >= 0 else Color.NEGATIVE
        parts = [f"{d['short']} ({d['year']}): ",
                 html.B(f"{d['gain_pct']:+.1f}%", style={"color": gain_col}),
                 f"  [{sig}]"]
        if d["improved_mort"] is not None and d["woods_mort"] is not None:
            parts.append(f"  ·  mortality {d['improved_mort']:.0f}% Improved vs "
                         f"{d['woods_mort']:.0f}% Woods")
        items.append(html.Li(parts))
    return html.Div([
        html.Div([
            html.Span(dc["verdict"], className="deploy-badge", style={"background": color}),
            html.Span(dc["headline"], className="deploy-headline"),
        ], className="deploy-head"),
        html.Ul(items, className="deploy-evidence") if items else html.Div(),
        html.Div("Based on the latest measured year of each metric. A screening signal — confirm "
                 "with the full report (trend, G×E, damage) before an operational call.",
                 className="deploy-foot"),
    ], className="deploy-card", style={"borderLeft": f"5px solid {color}"})


def _render_chat(history):
    rows = []
    for m in history:
        role = m["role"]
        err  = m.get("error")
        who  = "You" if role == "user" else ASSISTANT_NAME
        cls  = "msg " + ("user" if role == "user" else "assistant") + (" err" if err else "")
        if m.get("chart"):
            inner = []
            if m.get("caption"):
                inner.append(dcc.Markdown(m["caption"], className="md",
                                          style={"marginBottom": "6px"}))
            inner.append(dcc.Graph(figure=m["chart"], config=CHAT_GRAPH_CONFIG,
                                   style={"height": "320px"}))
            rows.append(html.Div([html.Span(who, className="msg-who"),
                                  html.Div(inner)], className=cls))
        else:
            rows.append(html.Div([html.Span(who, className="msg-who"),
                                  dcc.Markdown(m.get("content") or "", className="md")],
                                 className=cls))
    return rows
