# -*- coding: utf-8 -*-
"""
Reusable Dash UI components -- Modern Theme 2026.
"""
from __future__ import annotations

import uuid

import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from . import config
from .config import Color
from .figures import lighten


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def data_table(df, *, columns=None, table_id=None, height="300px", page_size=None,
               numeric_cols=(), filter_=False, gain_col=None):
    """Brand-styled DataTable."""
    cols = columns or list(df.columns)
    column_defs = []
    for c in cols:
        d = {"id": c, "name": c}
        if c in numeric_cols:
            d["type"] = "numeric"
        column_defs.append(d)

    style_data_conditional = [
        {"if": {"row_index": "odd"}, "backgroundColor": Color.SURFACE_ALT},
    ]
    if gain_col and gain_col in cols:
        style_data_conditional += [
            {"if": {"filter_query": f"{{{gain_col}}} >= 0", "column_id": gain_col},
             "color": Color.POSITIVE, "fontWeight": "600"},
            {"if": {"filter_query": f"{{{gain_col}}} < 0", "column_id": gain_col},
             "color": Color.NEGATIVE, "fontWeight": "600"},
        ]

    return dash_table.DataTable(
        id=table_id or f"tbl-{uuid.uuid4().hex[:8]}",
        data=df.to_dict("records"),
        columns=column_defs,
        fixed_rows={"headers": True},
        sort_action="native",
        filter_action="native" if filter_ else "none",
        page_action="native" if page_size else "none",
        page_size=page_size or 10,
        style_as_list_view=True,
        style_table={"height": height, "overflowY": "auto", "overflowX": "auto"},
        style_header={
            "backgroundColor": Color.NAVY, "color": "white", "fontWeight": "600",
            "border": "none", "fontSize": "12px", "textAlign": "center",
            "fontFamily": config.FONT_FAMILY, "position": "sticky", "top": 0,
        },
        style_data={"border": "none", "borderBottom": f"1px solid {Color.BORDER}"},
        style_data_conditional=style_data_conditional,
        style_cell={
            "textAlign": "center", "fontFamily": config.FONT_FAMILY, "fontSize": "12px",
            "color": Color.INK, "padding": "6px 8px", "whiteSpace": "normal",
            "minWidth": "70px", "maxWidth": "240px",
        },
    )


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------
def section_title(text, subtitle=None):
    children = [html.H4(text, className="section-title")]
    if subtitle:
        children.append(html.P(subtitle, className="section-subtitle"))
    return html.Div(children, className="section-head")


def chart_card(title, graph, *, info=None, tools=None, body_class="", icon=None):
    """Card wrapper for a chart with optional emoji icon, info tooltip, and tools."""
    head = []
    if icon:
        head.append(html.Span(icon, className="card-icon", **{"aria-hidden": "true"}))
    head.append(html.Span(title, className="card-title"))
    if info:
        # Focusable + labelled so the tip is reachable by keyboard and announced
        # by screen readers (a bare title= attribute is neither).
        head.append(html.Span("i", className="card-info", title=info, tabIndex=0,
                              role="note", **{"aria-label": "Info: " + info}))
    if tools:
        head.append(html.Div(tools, className="card-tools"))
    return html.Div([
        html.Div(head, className="card-head"),
        html.Div(graph, className=("card-body " + body_class).strip()),
    ], className="chart-card")


def kpi(label, value, sub=None, accent=Color.NAVY, icon=None,
        trend=None, trend_dir="neutral"):
    """KPI metric card.

    Parameters
    ----------
    label:     Short uppercase label.
    value:     Primary displayed value (string or Dash component).
    sub:       Optional sub-label text.
    accent:    Accent colour for the value and top border.
    icon:      Optional emoji shown top-right.
    trend:     Optional trend string like "+3.2%".
    trend_dir: "up", "down", or "neutral" -- controls badge colour.
    """
    top = [html.Div(label, className="kpi-label")]
    if icon:
        top.append(html.Div(icon, className="kpi-icon", **{"aria-hidden": "true"}))

    sub_children = []
    if sub:
        sub_children.append(html.Span(sub))
    if trend:
        arrows = {"up": "(+) ", "down": "(-) ", "neutral": ""}
        arrow = arrows.get(trend_dir, "")
        sub_children.append(
            html.Span(arrow + trend, className="kpi-trend " + trend_dir)
        )

    children = [
        html.Div(top, className="kpi-card-top"),
        html.Div(value, className="kpi-value", style={"color": accent}),
    ]
    if sub_children:
        children.append(html.Div(sub_children, className="kpi-sub"))

    return html.Div(children, className="kpi-card",
                    style={"borderTop": "3px solid " + accent})


def dropdown(dd_id, options, value, label=None, clearable=False, persistence=False):
    opts = [{"label": o, "value": o} if not isinstance(o, dict) else o
            for o in options]
    inner = dcc.Dropdown(id=dd_id, options=opts, value=value,
                         clearable=clearable, className="rgt-dd",
                         persistence=persistence, persistence_type="local")
    if label:
        return html.Div(
            [html.Label(label, className="dd-label"), inner],
            className="dd-wrap",
        )
    return inner


def legend_dot(color, text):
    return html.Span(
        [html.Span(className="legend-dot", style={"backgroundColor": color}), text],
        className="legend-item",
    )


# ---------------------------------------------------------------------------
# Colour map for installation series
# ---------------------------------------------------------------------------
def build_colour_map(installations):
    import plotly.express as px
    base = px.colors.qualitative.Dark24
    palette = [lighten(c, 0.35) for c in base]
    return {inst: palette[i % len(palette)] for i, inst in enumerate(sorted(installations))}
