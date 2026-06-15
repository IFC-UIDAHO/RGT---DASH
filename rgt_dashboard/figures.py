# -*- coding: utf-8 -*-
"""
Plotly figure factories.

The old app hand-built six near-identical heatmaps and several charts inline in
the callbacks (~400 lines of copy-paste).  Here each chart type is a single,
themed, defensive function.  Every figure runs through :func:`_theme` so the
whole dashboard shares one visual language.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import config
from . import transfer_layout
from .config import Color


# --------------------------------------------------------------------------- #
# Theming helpers
# --------------------------------------------------------------------------- #
def _theme(fig: go.Figure, *, height=None, legend=True, margin=None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        font=dict(family=config.FONT_FAMILY, size=12, color=Color.INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=margin or dict(l=48, r=18, t=30, b=40),
        hoverlabel=dict(font_family=config.FONT_FAMILY, font_size=12),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(255,255,255,0.6)", font=dict(size=11)),
        colorway=[Color.WOODS, Color.IMPROVED, Color.GOLD, Color.NAVY],
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(gridcolor=Color.GRID, zeroline=False)
    fig.update_yaxes(gridcolor=Color.GRID, zeroline=False)
    return fig


def empty_fig(message: str = "No data for this selection", height=None) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=14, color=Color.MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _theme(fig, height=height, legend=False)


def lighten(hex_color: str, amount: float = 0.5) -> str:
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02X}{g:02X}{b:02X}"


def _rep_sort_key(rep: str):
    m = re.search(r"(\d+)", str(rep))
    return (int(m.group(1)) if m else 0, str(rep))


def source_color(source: str) -> str:
    return Color.IMPROVED if source == config.SOURCE_IMPROVED else Color.WOODS


# --------------------------------------------------------------------------- #
# 1. Per-plot growth heatmap  (replaces 6 copy-pasted blocks)
# --------------------------------------------------------------------------- #
def heatmap(trees_one_plot: pd.DataFrame, *, zmin=None, zmax=None, height=300) -> go.Figure:
    """Per-plot growth grid.

    CORE plots are a true field map: the TREE index runs as a serpentine
    (row-major boustrophedon) walk across the 10-wide monitored grid -- rep 1 of
    each of the 10 seedlots along row 0, rep 2 reversed along row 1, and so on,
    which matches the trial's TREE numbering -- so cells sit in their real
    planting positions. Cells are coloured by growth and labelled with the
    seedlot; replication / defect / management are in the hover.

    TRANSFER plots store trees grouped by seedlot with no field-position column in
    the dataset, so each tree is placed at its real (row, col) from the IFC Plot
    Design workbook (``transfer_layout.POSITIONS``) -- making the transfer field
    map match the PLOT1-6 design diagrams exactly."""
    d = trees_one_plot
    if d is None or d.empty or d["Value"].notna().sum() == 0:
        return empty_fig("No measurements in this plot", height=height)
    if "InstallationType" in d.columns and str(d["InstallationType"].iloc[0]) == "TRANSFER":
        return _transfer_field_map(d, zmin=zmin, zmax=zmax, height=height)
    d = d.dropna(subset=["TREE"]).sort_values("TREE")
    n = len(d)
    # The monitored grid is config.PLOT_GRID_WIDTH wide (10×10 = 100 by design).
    # Snap to it when the count is consistent with that layout; fall back to a
    # square-ish reconstruction only for off-nominal / irregular plots.
    gw = getattr(config, "PLOT_GRID_WIDTH", 10)
    W = gw if abs(n - gw * gw) <= 25 else max(1, int(round(np.sqrt(n))))
    rows = int(np.ceil(n / W))
    vals = pd.to_numeric(d["Value"], errors="coerce").to_numpy(dtype=float)
    seeds = d["Seedlot"].astype(str).to_numpy()
    reps = d["Replication"].astype(str).to_numpy()
    defect = d["Defect"].fillna("").astype(str).to_numpy()
    mgmt = d["Management"].fillna("").astype(str).to_numpy()

    Z = np.full((rows, W), np.nan)
    S = np.full((rows, W), "", dtype=object)
    R = np.full((rows, W), "", dtype=object)
    DF = np.full((rows, W), "", dtype=object)
    MG = np.full((rows, W), "", dtype=object)
    for i in range(n):
        r = i // W
        c = i % W if r % 2 == 0 else (W - 1 - i % W)   # serpentine planting walk
        Z[r, c] = vals[i]; S[r, c] = seeds[i]; R[r, c] = reps[i]
        DF[r, c] = defect[i]; MG[r, c] = mgmt[i]

    customdata = np.dstack([S, R, DF, MG])
    fig = go.Figure(go.Heatmap(
        z=Z, x=list(range(1, W + 1)), y=list(range(1, rows + 1)),
        zmin=zmin, zmax=zmax, colorscale=config.HEATMAP_COLORSCALE,
        xgap=1, ygap=1, hoverongaps=False,
        text=S, texttemplate="%{text}", textfont=dict(size=7.5, color=Color.INK),
        customdata=customdata,
        colorbar=dict(thickness=9, len=0.85, outlinewidth=0, tickfont=dict(size=9)),
        hovertemplate=("Seedlot %{customdata[0]} · %{customdata[1]}<br>Value: %{z:.1f}"
                       "<br>Defect: %{customdata[2]}<br>Mgmt: %{customdata[3]}<extra></extra>"),
    ))
    fig.update_xaxes(showticklabels=False, title=None, type="category")
    fig.update_yaxes(autorange="reversed", showticklabels=False, title=None, type="category")
    return _theme(fig, height=height, legend=False, margin=dict(l=6, r=6, t=8, b=6))


def _transfer_field_map(d: pd.DataFrame, *, zmin=None, zmax=None, height=300) -> go.Figure:
    """Exact TRANSFER field map. Each tree is placed at its real (row, col) from
    the Plot Design workbook (transfer_layout.POSITIONS), so the layout matches the
    PLOT1-6 design diagrams. The few data trees whose replication has no design
    cell (e.g. an extra R17/R18) drop into an empty cell of the same seedlot."""
    d = d.dropna(subset=["Value"]).copy()
    if d.empty:
        return empty_fig("No measurements in this plot", height=height)
    d["Seedlot"] = d["Seedlot"].astype(str)
    d["_rep"] = d["Replication"].map(lambda r: _rep_sort_key(r)[0])
    R, Cc = transfer_layout.GRID_ROWS, transfer_layout.GRID_COLS
    Z = np.full((R, Cc), np.nan)
    S = np.full((R, Cc), "", dtype=object)
    RP = np.full((R, Cc), "", dtype=object)
    DF = np.full((R, Cc), "", dtype=object)
    MG = np.full((R, Cc), "", dtype=object)

    plot_seedlots = set(d["Seedlot"])
    seedlot_cells = {}                      # cells this plot's seedlots own
    for (sl, _rp), pos in transfer_layout.POSITIONS.items():
        if sl in plot_seedlots:
            seedlot_cells.setdefault(sl, []).append(pos)
    used = set()

    def _place(pos, row):
        r, c = pos
        Z[r, c] = row["Value"]; S[r, c] = str(row["Seedlot"]); RP[r, c] = str(row["Replication"])
        DF[r, c] = str(row.get("Defect") or ""); MG[r, c] = str(row.get("Management") or "")
        used.add(pos)

    leftover = []
    for _, row in d.iterrows():
        pos = transfer_layout.POSITIONS.get((row["Seedlot"], row["_rep"]))
        if pos is not None and pos not in used:
            _place(pos, row)
        else:
            leftover.append(row)
    for row in leftover:                    # same-seedlot empty cell, else any empty
        cells = [p for p in seedlot_cells.get(row["Seedlot"], []) if p not in used]
        if not cells:
            cells = [(r, c) for r in range(R) for c in range(Cc) if (r, c) not in used]
        if cells:
            _place(cells[0], row)

    customdata = np.dstack([S, RP, DF, MG])
    fig = go.Figure(go.Heatmap(
        z=Z, x=list(range(1, Cc + 1)), y=list(range(1, R + 1)),
        zmin=zmin, zmax=zmax, colorscale=config.HEATMAP_COLORSCALE,
        xgap=1, ygap=1, hoverongaps=False,
        text=S, texttemplate="%{text}", textfont=dict(size=7.5, color=Color.INK),
        customdata=customdata,
        colorbar=dict(thickness=9, len=0.85, outlinewidth=0, tickfont=dict(size=9)),
        hovertemplate=("Seedlot %{customdata[0]} · %{customdata[1]}<br>Value: %{z:.1f}"
                       "<br>Defect: %{customdata[2]}<br>Mgmt: %{customdata[3]}<extra></extra>"),
    ))
    fig.update_xaxes(showticklabels=False, title=None, type="category")
    fig.update_yaxes(autorange="reversed", showticklabels=False, title=None, type="category")
    return _theme(fig, height=height, legend=False, margin=dict(l=6, r=6, t=8, b=6))


def avg_max_min(com_df: pd.DataFrame, *, metric=None, height=340) -> go.Figure:
    if com_df is None or com_df.empty:
        return empty_fig(height=height)
    fig = go.Figure()
    for source in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        sub = com_df[com_df["Source"] == source].sort_values("Seedlot")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["Seedlot"].astype(str), y=sub["Overall Avg"], mode="markers", name=source,
            marker=dict(size=9, color=source_color(source),
                        line=dict(width=1, color="white")),
            error_y=dict(type="data", symmetric=False,
                         array=sub.get("array"), arrayminus=sub.get("arrayminus"),
                         color=lighten(source_color(source), 0.2), thickness=1.4, width=4),
            hovertemplate="Seedlot %{x}<br>Mean: %{y:.2f}<extra>" + source + "</extra>",
        ))
    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_yaxes(title=axis)
    fig.update_xaxes(title="Seedlot", type="category", tickangle=270)
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 3. Grouped bar: seedlot means coloured by installation (one source)
# --------------------------------------------------------------------------- #
def seedlot_bars(plot_df: pd.DataFrame, *, source, inst_order, colour_map,
                 ymax=None, metric=None, height=360) -> go.Figure:
    sub = plot_df[plot_df["Source"] == source].copy()
    if sub.empty:
        return empty_fig(f"No {source} seedlots", height=height)
    sub["Seedlot"] = sub["Seedlot"].astype(str)
    seed_order = sorted(sub["Seedlot"].unique())
    fig = go.Figure()
    for inst in inst_order:
        s = sub[sub["Installation"] == inst]
        if s.empty:
            continue
        fig.add_trace(go.Bar(
            name=inst, x=s["Seedlot"], y=s["Overall Avg"],
            marker_color=colour_map.get(inst, Color.NEUTRAL),
            hovertemplate="%{x}<br>%{y:.2f}<extra>" + inst + "</extra>",
        ))
    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_xaxes(categoryorder="array", categoryarray=seed_order, tickangle=270,
                     type="category", title=None)
    fig.update_yaxes(title=axis, range=[0, ymax] if ymax else None)
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 4. Boxplot of tree values by seedlot, split by source
# --------------------------------------------------------------------------- #
def seedlot_box(trees: pd.DataFrame, *, metric=None, height=420) -> go.Figure:
    if trees is None or trees.empty:
        return empty_fig(height=height)
    fig = go.Figure()
    for source in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        sub = trees[trees["Source"] == source]
        if sub.empty:
            continue
        fig.add_trace(go.Box(
            x=sub["Seedlot"].astype(str), y=sub["Value"], name=source,
            marker_color=source_color(source), boxpoints="outliers",
            line=dict(width=1.2), fillcolor=lighten(source_color(source), 0.55),
        ))
    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_layout(boxmode="group")
    fig.update_xaxes(title="Seedlot", type="category", tickangle=270)
    fig.update_yaxes(title=axis)
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 5. Installation-level comparison (horizontal grouped bars + SE)
# --------------------------------------------------------------------------- #
def installation_comparison(inst_df: pd.DataFrame, *, metric=None, height=360) -> go.Figure:
    if inst_df is None or inst_df.empty:
        return empty_fig(height=height)
    fig = go.Figure()
    order = (inst_df[inst_df["Source"] == config.SOURCE_WOODS]
             .sort_values("Average")["Installation"].tolist())
    for source in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        sub = inst_df[inst_df["Source"] == source].set_index("Installation").reindex(order).reset_index()
        fig.add_trace(go.Bar(
            name=source, orientation="h", y=sub["Installation"], x=sub["Average"],
            marker_color=source_color(source),
            error_x=dict(type="data", array=sub["se"], thickness=1.2, width=3,
                         color=Color.MUTED),
            hovertemplate="%{y}<br>%{x:.2f}<extra>" + source + "</extra>",
        ))
    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_layout(barmode="group")
    fig.update_xaxes(title=axis)
    fig.update_yaxes(title=None, automargin=True)
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 6. NEW — Realized genetic gain by installation
# --------------------------------------------------------------------------- #
def gain_chart(gain_df: pd.DataFrame, *, metric=None, height=420) -> go.Figure:
    if gain_df is None or gain_df.empty:
        return empty_fig("No gain estimates for this selection", height=height)
    d = gain_df.dropna(subset=["gain_pct"]).sort_values("gain_pct")
    if d.empty:
        return empty_fig("No gain estimates for this selection", height=height)

    def bar_color(row):
        if row["gain_pct"] >= 0:
            return Color.POSITIVE if row["significant"] else lighten(Color.POSITIVE, 0.55)
        return Color.NEGATIVE if row["significant"] else lighten(Color.NEGATIVE, 0.5)

    colors = [bar_color(r) for _, r in d.iterrows()]
    labels = [f"{g:+.1f}%{(' ' + s) if s and s != 'ns' else ''}"
              for g, s in zip(d["gain_pct"], d["stars"])]
    fig = go.Figure(go.Bar(
        orientation="h", y=d["installation"], x=d["gain_pct"],
        marker_color=colors, text=labels, textposition="outside", cliponaxis=False,
        customdata=np.stack([d["woods_mean"], d["improved_mean"],
                             d["p_value"].fillna(np.nan)], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Gain: %{x:+.1f}%"
                       "<br>Woods Run: %{customdata[0]:.2f}"
                       "<br>Improved: %{customdata[1]:.2f}"
                       "<br>p = %{customdata[2]:.3f}<extra></extra>"),
    ))
    fig.add_vline(x=0, line_width=1.5, line_color=Color.MUTED)
    unit = config.METRICS.get(metric, {}).get("short", "growth")
    fig.update_xaxes(title=f"Realized gain in {unit} (%)  ·  Improved vs Woods Run", ticksuffix="%")
    fig.update_yaxes(title=None, automargin=True)
    return _theme(fig, height=height, legend=False)


# --------------------------------------------------------------------------- #
# 6b. NEW — Dumbbell: Woods Run -> Improved mean per installation
# --------------------------------------------------------------------------- #
def gain_dumbbell(gain_df: pd.DataFrame, *, metric=None, height=460) -> go.Figure:
    """Paired Woods Run -> Improved means per site. The connector shows the
    direction and size of realized gain (green = positive, red = negative);
    significant sites (p<0.05) get a gold ring on the Improved dot. A grey
    horizontal whisker on the Improved dot is the 95% CI of the gain -- when it
    reaches back across the Woods Run dot, the gain is not significant."""
    if gain_df is None or gain_df.empty:
        return empty_fig("No gain estimates for this selection", height=height)
    d = gain_df.dropna(subset=["woods_mean", "improved_mean", "gain_pct"]).copy()
    if d.empty:
        return empty_fig("No gain estimates for this selection", height=height)
    d = d.sort_values("gain_pct")
    n = len(d)
    ys    = list(range(n))
    insts = d["installation"].astype(str).tolist()
    woods = [float(v) for v in d["woods_mean"]]
    imp   = [float(v) for v in d["improved_mean"]]
    gains = [float(v) for v in d["gain_pct"]]
    stars = (d["stars"].fillna("").astype(str).tolist() if "stars" in d.columns else [""] * n)
    sig   = (list(d["significant"]) if "significant" in d.columns else [g >= 0 for g in gains])

    # 95% CI on the gain (the Improved - Woods difference) -> a horizontal error
    # bar on the Improved dot. The CI maps to [woods + diff_lo, woods + diff_hi]
    # in x-units; arms are measured from the Improved dot. NaN CI (small samples)
    # yields a zero-length arm (no whisker drawn).
    dlo = [(float(v) if pd.notna(v) else None)
           for v in (d["diff_lo"] if "diff_lo" in d.columns else [float("nan")] * n)]
    dhi = [(float(v) if pd.notna(v) else None)
           for v in (d["diff_hi"] if "diff_hi" in d.columns else [float("nan")] * n)]
    err_plus  = [max(0.0, dhi[i] - (imp[i] - woods[i])) if dhi[i] is not None else 0.0 for i in range(n)]
    err_minus = [max(0.0, (imp[i] - woods[i]) - dlo[i]) if dlo[i] is not None else 0.0 for i in range(n)]
    ci_right  = [woods[i] + dhi[i] for i in range(n) if dhi[i] is not None]
    ci_left   = [woods[i] + dlo[i] for i in range(n) if dlo[i] is not None]

    xr = max([max(woods), max(imp)] + ci_right)
    xl = min([min(woods), min(imp)] + ci_left)
    span = (xr - xl) or 1.0

    fig = go.Figure()

    # connector segments, coloured by gain sign
    def _seg(keep, color):
        xs, yy = [], []
        for i in range(n):
            if keep(i):
                xs += [woods[i], imp[i], None]
                yy += [ys[i], ys[i], None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=yy, mode="lines",
                          line=dict(color=color, width=3.5),
                          hoverinfo="skip", showlegend=False))
    _seg(lambda i: gains[i] >= 0, lighten(Color.POSITIVE, 0.10))
    _seg(lambda i: gains[i] < 0,  lighten(Color.NEGATIVE, 0.10))

    # Woods Run dots
    fig.add_trace(go.Scatter(
        x=woods, y=ys, mode="markers", name="Woods Run",
        marker=dict(size=12, color=Color.WOODS, line=dict(width=1.5, color="white")),
        customdata=insts,
        hovertemplate="<b>%{customdata}</b><br>Woods Run mean: %{x:.1f}<extra></extra>"))

    # Improved dots — gold ring when significant; grey whisker = 95% CI of the gain
    fig.add_trace(go.Scatter(
        x=imp, y=ys, mode="markers", name="Improved",
        error_x=dict(type="data", symmetric=False, array=err_plus, arrayminus=err_minus,
                     color=Color.MUTED, thickness=1.3, width=5),
        marker=dict(size=14, color=Color.IMPROVED,
                    line=dict(width=[2.4 if s else 1.2 for s in sig],
                              color=[Color.GOLD if s else "white" for s in sig])),
        customdata=list(zip(insts, gains, woods)),
        hovertemplate=("<b>%{customdata[0]}</b><br>Improved mean: %{x:.1f}"
                       "<br>Woods Run: %{customdata[2]:.1f}"
                       "<br>Realized gain: %{customdata[1]:+.1f}%<extra></extra>")))

    # gain % labels just right of each pair (clear of the CI whisker)
    right_end = [max(woods[i], imp[i], (woods[i] + dhi[i]) if dhi[i] is not None else imp[i])
                 for i in range(n)]
    label_x = [right_end[i] + span * 0.03 for i in range(n)]
    labels  = [f"{gains[i]:+.0f}%{(' ' + stars[i]) if stars[i] and stars[i] != 'ns' else ''}"
               for i in range(n)]
    lcol    = [Color.POSITIVE if gains[i] >= 0 else Color.NEGATIVE for i in range(n)]
    fig.add_trace(go.Scatter(
        x=label_x, y=ys, mode="text", text=labels, textposition="middle right",
        textfont=dict(size=10.5, color=lcol), cliponaxis=False,
        hoverinfo="skip", showlegend=False))

    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_xaxes(title=axis, range=[max(0, xl - span * 0.06), xr + span * 0.24])
    fig.update_yaxes(tickmode="array", tickvals=ys, ticktext=insts, title=None, automargin=True)
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 7. NEW — Gain vs site productivity (the trial's core question)
# --------------------------------------------------------------------------- #
def gain_vs_productivity(gain_df: pd.DataFrame, rel: dict, *, metric=None, height=420) -> go.Figure:
    """Realized gain vs site productivity. The y-axis is ABSOLUTE gain
    (Improved - Woods Run, in metric units), not gain %, because gain % has the
    Woods Run mean in its denominator and regressing it on that same mean would
    fabricate a negative slope. Hover still reports the % for context."""
    if gain_df is None or gain_df.empty:
        return empty_fig(height=height)
    d = gain_df.dropna(subset=["woods_mean", "gain_abs"])
    if d.empty:
        return empty_fig(height=height)
    unit = config.METRICS.get(metric, {}).get("unit", "")
    sig = d[d["significant"]]
    nsig = d[~d["significant"]]
    hov = ("%{text}<br>Woods Run mean %{x:.1f}<br>"
           "Realized gain %{y:+.2f} " + unit + "  (%{customdata:+.1f}%)<extra></extra>")
    fig = go.Figure()
    fig.add_hline(y=0, line_width=1, line_color=Color.GRID)
    fig.add_trace(go.Scatter(
        x=nsig["woods_mean"], y=nsig["gain_abs"], mode="markers+text", customdata=nsig["gain_pct"],
        text=nsig["installation"], textposition="top center", textfont=dict(size=9, color=Color.MUTED),
        marker=dict(size=11, color=lighten(Color.NAVY, 0.4), line=dict(width=1, color="white")),
        name="n.s.", hovertemplate=hov))
    if not sig.empty:
        fig.add_trace(go.Scatter(
            x=sig["woods_mean"], y=sig["gain_abs"], mode="markers+text", customdata=sig["gain_pct"],
            text=sig["installation"], textposition="top center", textfont=dict(size=9, color=Color.INK),
            marker=dict(size=13, color=Color.GOLD, line=dict(width=1.4, color=Color.NAVY)),
            name="p < 0.05", hovertemplate=hov))
    # regression line (fit on absolute gain)
    if rel and rel.get("n", 0) >= 3 and not np.isnan(rel.get("slope", np.nan)):
        xs = np.linspace(d["woods_mean"].min(), d["woods_mean"].max(), 50)
        ys = rel["intercept"] + rel["slope"] * xs
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", name=f"fit (r={rel['r']:.2f}, p={rel['p']:.2f})",
            line=dict(color=Color.GOLD, width=2, dash="dash"), hoverinfo="skip"))
    axis = config.METRICS.get(metric, {}).get("axis", "Growth")
    fig.update_xaxes(title=f"Site productivity — Woods Run mean ({axis})")
    fig.update_yaxes(title=f"Realized gain — Improved − Woods Run ({unit})")
    return _theme(fig, height=height)


# --------------------------------------------------------------------------- #
# 8. NEW — Survival & damage (shown on the Genetic Gain & Summary tab)
# --------------------------------------------------------------------------- #
def mortality_by_site(trees: pd.DataFrame, *, height=440) -> go.Figure:
    """Horizontal grouped bars: mortality % (Woods Run vs Improved) per
    installation. ``trees`` is a single-metric tree slice (all rows incl dead)."""
    if trees is None or trees.empty:
        return empty_fig("No survival data for this selection", height=height)
    g = (trees.groupby(["Installation", "Source"])["IsDead"].mean().mul(100).round(1)
         .reset_index(name="mort"))
    if g.empty:
        return empty_fig("No survival data for this selection", height=height)
    order = g.groupby("Installation")["mort"].mean().sort_values().index.tolist()
    fig = go.Figure()
    for src in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        s = g[g["Source"] == src].set_index("Installation").reindex(order).reset_index()
        fig.add_trace(go.Bar(
            name=src, orientation="h", y=s["Installation"], x=s["mort"],
            marker_color=source_color(src),
            hovertemplate="%{y}<br>%{x:.1f}% dead<extra>" + src + "</extra>"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Mortality (%)", ticksuffix="%")
    fig.update_yaxes(title=None, automargin=True)
    return _theme(fig, height=height)


def damage_agents(trees: pd.DataFrame, *, height=440, top=8) -> go.Figure:
    """Top damage / defect agents as a % of each source's trees. ``trees`` is a
    single-metric slice (all rows) so each tree is counted once, not per metric."""
    if trees is None or trees.empty:
        return empty_fig("No data for this selection", height=height)
    n_by_src = trees.groupby("Source").size()
    d = trees[trees["HasDefect"]]
    if d.empty:
        return empty_fig("No recorded damage for this selection", height=height)
    cnt = d.groupby(["Defect", "Source"]).size().reset_index(name="n")
    cnt["pct"] = cnt.apply(lambda r: 100 * r["n"] / n_by_src.get(r["Source"], 1), axis=1)
    totals = cnt.groupby("Defect")["n"].sum().nlargest(top).index.tolist()
    cnt = cnt[cnt["Defect"].isin(totals)]
    fig = go.Figure()
    for src in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        s = cnt[cnt["Source"] == src].set_index("Defect").reindex(totals).reset_index()
        fig.add_trace(go.Bar(
            name=src, x=s["Defect"], y=s["pct"], marker_color=source_color(src),
            hovertemplate="%{x}<br>%{y:.1f}% of trees<extra>" + src + "</extra>"))
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_xaxes(title=None, tickangle=-25, type="category")
    fig.update_yaxes(title="% of trees affected", ticksuffix="%")
    return _theme(fig, height=height)
