# -*- coding: utf-8 -*-
"""
ForestTask report generator.

Turns a natural-language request ("report on installation HOODOO", "report on
seedlot 97-72", "overall report for Year 3", "report on 2 seedlots 97-72 and
1333") into a structured, IFC-branded report: request-specific tables and charts
computed straight from the data, with an LLM-written interpretation that is
grounded ONLY in those computed numbers (deterministic fallback if the LLM is
unavailable). Renders to Dash components for the on-screen view and to a
self-contained HTML file for download.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import config, figures as F, stats
from .config import Color

IFC_LOGO = "https://ifc.nkn.uidaho.edu/static/img/ifc_logo_official.png"


# =========================================================================== #
# Request parsing
# =========================================================================== #
@dataclass
class ReportSpec:
    kind: str                      # installation | seedlot | year | overall
    installations: list = field(default_factory=list)
    seedlots: list = field(default_factory=list)
    years: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    source: str = None        # Woods run / Improved filter
    regions: list = field(default_factory=list)   # multi-region comparison
    region: str = None        # INW / K-S
    inst_type: str = None     # CORE / TRANSFER
    focus: str = ""           # free-text emphasis (mortality, trend, ...)
    raw: str = ""
    seedlot_corrections: dict = field(default_factory=dict)  # typed id -> resolved id
    seedlots_not_found: list = field(default_factory=list)   # explicitly requested, unresolved
    compare_axis: str = None   # region | installation | seedlot | source | site_type
    compare_items: list = field(default_factory=list)        # the things being contrasted

    @property
    def title(self):
        if self.kind == "installation":
            return "Installation Report — " + ", ".join(self.installations)
        if self.kind == "seedlot":
            return "Seedlot Report — " + ", ".join(self.seedlots)
        if self.kind == "year":
            return "Annual Report — " + ", ".join(self.years)
        if self.kind == "seedlot_group":
            return f"{self.source} Seedlots — Performance Report"
        if self.kind == "region_compare":
            return "Regional Comparison — " + " vs ".join(self.regions)
        if self.kind == "compare":
            label = {"seedlot": "Seedlot", "installation": "Installation",
                     "site_type": "Site-type"}.get(self.compare_axis, "")
            return f"{label} Comparison — " + " vs ".join(str(i) for i in self.compare_items)
        # "overall" — check if the request is specifically a comparison
        tl = (self.raw or "").lower()
        _has_woods = any(w in tl for w in ("woods run", "woods-run", "woodsrun",
                                           "unimproved", "wild type", "wild-type", "check lot"))
        _has_imp   = "improved" in tl
        if _has_woods and _has_imp:
            yrs = " & ".join(self.years) if len(self.years) <= 3 else "All Years"
            return f"Woods Run vs Improved — {yrs}"
        return "Overall Trial Report"


def _match_named(text_lower: str, names) -> list:
    """Robustly find catalog names in free text. Matches the full name, OR every
    significant word of the name appearing as whole words (any order) — so
    'wild turkey', 'Wild-Turkey', 'the wild turkey site', and double-spaced
    variants all resolve to 'WILD TURKEY', while 'LODGEPOLE 1' still needs both
    'lodgepole' and '1' (never collides with 'LODGEPOLE 2')."""
    norm = re.sub(r"[^a-z0-9]+", " ", text_lower).strip()
    norm = f" {norm} "
    hits = []
    for name in names:
        nl = name.lower()
        if nl in text_lower:
            hits.append(name); continue
        toks = [w for w in re.split(r"[^a-z0-9]+", nl) if w]
        if toks and all(f" {w} " in norm for w in toks):
            hits.append(name)
    return hits


def parse_request(text: str, store) -> ReportSpec:
    """Deterministically extract entities (matched against the real catalogs) and
    infer the report kind from the request text."""
    t = (text or "")
    tl = t.lower()
    insts = _match_named(tl, store.installations_all())
    # seedlots: match whole tokens to avoid '80-01' matching inside other text
    catalog = list(store.seedlots_all())
    seedlots = []
    for sl in catalog:
        if re.search(r"(?<![\w-])" + re.escape(sl.lower()) + r"(?![\w-])", tl):
            seedlots.append(sl)
    # Fuzzy seedlot resolution: the user may type a seedlot id that doesn't match
    # exactly (typo / transposition, e.g. '97-27' for '97-72'). Find id-shaped
    # tokens the user typed; resolve any that aren't exact to the closest catalog
    # seedlot (preferring seedlots actually planted at any named installation), and
    # record the correction so the report can state it. Never silently drop them.
    seedlot_corrections, seedlots_not_found = {}, []
    if "seedlot" in tl or "seed lot" in tl or "family" in tl or re.search(r"\b\d{1,4}-\d{1,4}\b", t):
        cand = set(re.findall(r"\b\d{1,4}-\d{1,4}[a-z0-9]*\b", tl))          # 97-72, 2193-16
        cand |= set(re.findall(r"(?:seed\s*lot|family|entry)\s*#?\s*([a-z0-9][a-z0-9-]{1,12})", tl))
        cand |= set(re.findall(r"\b\d{3,5}\b", tl))                          # 1121, 40089
        cat_lower = {c.lower(): c for c in catalog}
        scope = [c for c in catalog if c.lower() in cat_lower]
        if insts:
            at = set(store.df[store.df["Installation"].isin(insts)]["Seedlot"].dropna().astype(str))
            scope = sorted(at) or catalog
        else:
            scope = catalog
        import difflib
        for tok in cand:
            if tok in cat_lower:                       # exact (case-insensitive)
                real = cat_lower[tok]
                if real not in seedlots:
                    seedlots.append(real)
                continue
            if any(tok in s.lower() for s in seedlots):
                continue
            m = (difflib.get_close_matches(tok, [s.lower() for s in scope], n=1, cutoff=0.6)
                 or difflib.get_close_matches(tok, list(cat_lower.keys()), n=1, cutoff=0.6))
            if m:
                real = cat_lower.get(m[0]) or next((s for s in scope if s.lower() == m[0]), m[0])
                if real not in seedlots:
                    seedlots.append(real)
                    seedlot_corrections[tok] = real
            else:
                seedlots_not_found.append(tok)
    # Year detection — accept every natural phrasing a user might type:
    # "year 1", "yr1", "year one", "1st year", "first year", "1 year", "year #1".
    _YEAR_TOKENS = {"1": ["1", "1st", "first", "one"],
                    "2": ["2", "2nd", "second", "two"],
                    "3": ["3", "3rd", "third", "three"]}
    years_explicit = []
    for y in store.years():
        n = y.replace("Year", "")
        toks = _YEAR_TOKENS.get(n, [n])
        pats = []
        for tok in toks:
            t_ = re.escape(tok)
            pats.append(rf"\byears?\s*#?\s*{t_}\b")   # year 1 / year #1 / years one
            pats.append(rf"\byr\s*{t_}\b")            # yr1 / yr 1
            pats.append(rf"\b{t_}\s*(?:st|nd|rd)?\s+years?\b")  # 1st year / first year / 1 year
        if y.lower() in tl or any(re.search(p, tl) for p in pats):
            years_explicit.append(y)
    metrics = [m for m in store.metrics()
               if config.METRICS[m]["short"].lower() in tl or m.lower() in tl]
    years = years_explicit or list(store.years())
    if not metrics:
        metrics = list(store.metrics())

    # An explicit seedlot request (resolved OR just typed-but-unresolved) is a
    # seedlot report; any named installation then acts as a scope filter, NOT a
    # fallback installation report.
    if seedlots or seedlots_not_found:
        kind = "seedlot"
    elif insts:
        kind = "installation"
    elif years_explicit:          # a specific year, no entity -> annual report
        kind = "year"
    else:
        kind = "overall"
    # Source filter — only set when ONE side is requested; leave None for comparisons.
    # NB: "wild" is NOT a Woods-Run synonym (collides with the WILD TURKEY site).
    _has_woods = any(w in tl for w in ("woods run", "woods-run", "woodsrun", "unimproved",
                                       "wild type", "wild-type", "check lot"))
    _has_imp   = "improved" in tl
    source = None
    if _has_woods and not _has_imp:
        source = config.SOURCE_WOODS
    elif _has_imp and not _has_woods:
        source = config.SOURCE_IMPROVED
    # both present → comparison; leave source=None so both sides are shown
    regions_found = []
    if re.search(r"\binw\b", tl) or "inland northwest" in tl:
        regions_found.append("INW")
    if re.search(r"\bk[-\s]?s\b", tl) or "kootenai" in tl or "stillwater" in tl:
        regions_found.append("K-S")
    region = regions_found[0] if len(regions_found) == 1 else None
    regions = regions_found if len(regions_found) > 1 else []
    # Site type — but "core vs transfer" is a COMPARISON, not a single-type filter.
    site_type_compare = ("core" in tl and "transfer" in tl)
    inst_type = None
    if not site_type_compare:
        if "transfer" in tl:
            inst_type = "TRANSFER"
        elif "core" in tl:
            inst_type = "CORE"
    focus = ", ".join(w for w in ("mortality", "survival", "significance", "significant",
                                  "trend", "productivity", "deployment", "compare", "comparison",
                                  "ranking", "best", "worst") if w in tl)
    if source and not seedlots and not insts:
        kind = "seedlot_group"     # e.g. "report on all improved seedlots"
    if len(regions) > 1 and not seedlots and not insts:
        kind = "region_compare"    # e.g. "compare INW vs K-S"
    # General comparison axis: 2+ entities of one facet => focused side-by-side.
    compare_axis, compare_items = None, []
    if len(seedlots) >= 2:
        compare_axis, compare_items = "seedlot", list(seedlots)
    elif len(insts) >= 2:
        compare_axis, compare_items = "installation", list(insts)
    elif site_type_compare and not seedlots and not insts:
        compare_axis, compare_items = "site_type", ["CORE", "TRANSFER"]
    if compare_axis:
        kind = "compare"
    return ReportSpec(kind=kind, installations=insts, seedlots=seedlots,
                      years=years, metrics=metrics, source=source, region=region, regions=regions,
                      inst_type=inst_type, focus=focus, raw=t,
                      seedlot_corrections=seedlot_corrections, seedlots_not_found=seedlots_not_found,
                      compare_axis=compare_axis, compare_items=compare_items)


# =========================================================================== #
# Report model
# =========================================================================== #
@dataclass
class Block:
    type: str                      # narrative | table | figure | kpis | note
    payload: object
    title: str = ""


@dataclass
class Section:
    heading: str
    blocks: list = field(default_factory=list)
    level: int = 2


@dataclass
class Report:
    title: str
    subtitle: str
    sections: list = field(default_factory=list)


# =========================================================================== #
# Narrative (LLM grounded in computed numbers, with deterministic fallback)
# =========================================================================== #
def _narrate(client, instruction: str, data_context: dict, fallback: str, *, deep=False) -> str:
    sys = (
        "You are ForestTask, a forest-biometrics analyst writing a formal report for the "
        "Intermountain Forestry Cooperative Realized Genetic Gain Trials (RGT), which compare "
        "genetically Improved Douglas-fir against local Woods Run (unimproved) checks across "
        "installations in two regions: the Inland Northwest (INW) and the Klamath-Siskiyou (K-S), over "
        "three measurement years and three growth metrics (caliper, height, volume).\n"
        "Use ONLY these region names: INW = Inland Northwest, K-S = Klamath-Siskiyou. Never use any other.\n"
        "Write clear, professional, INTERPRETIVE Markdown prose: explain what the numbers mean, "
        "compare entities, note patterns, magnitudes, significance and practical implications for "
        "deployment. Use a '- ' list for findings when helpful; '###' sub-headings only in long "
        "passages.\n"
        "DEFINITIONS: realized gain % = (Improved mean - Woods Run mean) / Woods Run mean x 100; "
        "p<0.05 = significant (* <0.05, ** <0.01, *** <0.001); negative gain = Improved under-"
        "performed the check; CORE = main sites, TRANSFER = off-site climate tests.\n"
        "HARD RULES: Ground EVERY number strictly in the DATA JSON provided — never invent, round "
        "differently, or recall outside figures. Be appropriately cautious about non-significant "
        "results, small samples, and the under-sampled Year 3. No LaTeX, no images.")
    if client is None or not getattr(client, "configured", False):
        return fallback
    msgs = [{"role": "system", "content": sys},
            {"role": "system", "content": "DATA (the only numbers you may cite):\n"
             + json.dumps(data_context, default=str)},
            {"role": "user", "content": instruction}]
    try:
        r = client.chat(msgs, model=config.MindRouter.LARGE_MODEL,
                        max_tokens=config.MindRouter.MAX_TOKENS,
                        reasoning_effort="high", timeout=300)
        if r.get("ok") and r.get("content"):
            return r["content"]
    except Exception:
        pass
    return fallback


# =========================================================================== #
# Helpers
# =========================================================================== #
def _fmt(x, pct=False, plus=False):
    if x is None or (isinstance(x, float) and (np.isnan(x))):
        return "—"
    s = f"{x:+.1f}" if plus else f"{x:.1f}"
    return s + ("%" if pct else "")


def _gain_rows_for_installation(store, inst, region, years, metrics):
    rows = []
    for y in years:
        for m in metrics:
            r = stats.compare_sources(store, region=region, installation=inst, year=y, metric=m)
            if r:
                rows.append(dict(Year=y, Metric=config.METRICS[m]["short"],
                                 **{"Woods Run": r.woods_mean, "Improved": r.improved_mean,
                                    "Gain %": r.gain_pct, "p": r.p_value, "Sig.": r.stars,
                                    "Imp. mort.%": r.improved_mortality}))
    return pd.DataFrame(rows)


def _region_of(store, inst):
    m = store.inst_type_map
    hit = m[m["Installation"] == inst]
    return hit["Region"].iloc[0] if not hit.empty else None


def _plot_detail(store, inst, years, metric):
    """Per-plot mean growth for one installation & metric, by year.
    Plots 1-3 are Woods Run, 4-6 are Improved (config.PLOT_SOURCE_MAP), so this
    exposes the spatial/plot layout the field maps visualise."""
    pt = store.plot_table
    sub = pt[(pt["Installation"] == inst) & (pt["Metric"] == metric)]
    if years:
        sub = sub[sub["Year"].isin(years)]
    plot_cols = [c for c in sub.columns if c.startswith("Plot ") and c.endswith(" Avg")]
    out = {}
    for y in (years or sorted(sub["Year"].unique())):
        yt = sub[sub["Year"] == y]
        if yt.empty:
            continue
        rec = {}
        for c in plot_cols:
            v = pd.to_numeric(yt[c], errors="coerce").mean()
            if pd.notna(v):
                pnum = int(c.split()[1])
                src = config.PLOT_SOURCE_MAP.get(pnum, "?")
                rec[f"Plot {pnum} ({'W' if src == config.SOURCE_WOODS else 'I'})"] = round(float(v), 2)
        if rec:
            out[y] = rec
    return out


def _survival_defects(store, inst, years, metric):
    """Compact survival + defect/management summary for an installation."""
    t = store.trees(installation=inst, metric=metric)
    if years:
        t = t[t["Year"].isin(years)]
    if t.empty:
        return {}
    out = {}
    for src in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        s = t[t["Source"] == src]
        if s.empty:
            continue
        n = len(s)
        dead = int(s["IsDead"].sum())
        defc = int(s["HasDefect"].sum())
        top_def = (s.loc[s["HasDefect"], "Defect"].astype(str).value_counts().head(3).to_dict())
        out[src] = {"trees_measured": n,
                    "mortality_pct": round(100 * dead / n, 1) if n else None,
                    "defect_pct": round(100 * defc / n, 1) if n else None,
                    "top_defects": top_def}
    return out


# =========================================================================== #
# Report builders
# =========================================================================== #
def _dispatch(spec: ReportSpec, store, client=None) -> Report:
    if spec.kind == "seedlot":
        return _seedlot_report(spec, store, client)
    if spec.kind == "installation":
        return _installation_report(spec, store, client)
    if spec.kind == "year":
        return _year_report(spec, store, client)
    return _overall_report(spec, store, client)


def _installation_report(spec, store, client):
    rep = Report(spec.title, f"Years: {', '.join(spec.years)} · generated {_today()}")
    for inst in spec.installations:
        region = _region_of(store, inst)
        gdf = _gain_rows_for_installation(store, inst, region, spec.years, spec.metrics)
        ctx = dict(installation=inst, region=region, gain=gdf.to_dict("records"))
        fb = _fallback_installation(inst, gdf)
        rep.sections.append(Section(
            heading=inst, level=2,
            blocks=[Block("narrative", _narrate(
                client, f"Write a 2-3 sentence overview of how the Improved stock performed "
                f"versus Woods Run at {inst} across the years and metrics.", ctx, fb))]))
        for y in spec.years:
            yblocks = []
            ygdf = gdf[gdf["Year"] == y]
            if ygdf.empty:
                continue
            # KPI line
            kpis = []
            for _, r in ygdf.iterrows():
                kpis.append((f"{r['Metric']} gain", _fmt(r["Gain %"], pct=True, plus=True),
                             f"Woods {r['Woods Run']:.1f} → Imp {r['Improved']:.1f} · {r['Sig.']}"))
            yblocks.append(Block("kpis", kpis))
            yblocks.append(Block("table", ygdf[["Metric", "Woods Run", "Improved", "Gain %",
                                                 "Sig.", "p", "Imp. mort.%"]].round(2),
                                 "Realized gain by metric"))
            # per-seedlot table for this installation/year (default metric)
            metric = spec.metrics[0]
            sl = store.seedlots(region=region, installation=inst, year=y, metric=metric)
            if not sl.empty:
                slt = sl[["Source", "Seedlot", "Average", "Standard error", "Mortality %"]].copy()
                slt.columns = ["Source", "Seedlot",
                               f"Mean ({config.METRICS[metric]['unit']})", "Std err", "Mort. %"]
                yblocks.append(Block("table", slt.sort_values(["Source", "Seedlot"]).round(2),
                                     f"Per-seedlot means — {config.METRICS[metric]['short']}"))
            yblocks.append(Block("figure", _fig_gain_by_metric(ygdf),
                                 f"Realized gain by metric — {y}"))
            rep.sections.append(Section(heading=f"{inst} · {y}", level=3, blocks=yblocks))
        # combined trend
        rep.sections.append(Section(
            heading=f"{inst} · combined", level=3,
            blocks=[Block("figure", _fig_gain_trend(gdf), "Realized gain across years"),
                    Block("narrative", _narrate(
                        client, f"Interpret the year-over-year trend in realized gain at {inst}: "
                        f"is the advantage growing, shrinking or inconsistent across metrics, and "
                        f"what does that imply?", ctx, _fallback_trend(inst, gdf), deep=True))]))
    return rep


def _seedlot_report(spec, store, client):
    rep = Report(spec.title, f"Years: {', '.join(spec.years)} · generated {_today()}")
    df = store.df
    for sl in spec.seedlots:
        sub = df[df["Seedlot"].astype(str) == sl]
        source = sub["Source"].iloc[0] if not sub.empty else "?"
        sct = dict(seedlot=sl, source=source)
        # per year x metric: this seedlot's mean across installations, vs its source-group mean
        recs = []
        for y in spec.years:
            for m in spec.metrics:
                st = store.seedlot_table
                this = st[(st["Seedlot"].astype(str) == sl) & (st["Year"] == y) & (st["Metric"] == m)]
                grp = st[(st["Source"] == source) & (st["Year"] == y) & (st["Metric"] == m)]
                if this.empty:
                    continue
                recs.append(dict(Year=y, Metric=config.METRICS[m]["short"],
                                 **{"Seedlot mean": round(this["Average"].mean(), 2),
                                    f"{source} avg": round(grp["Average"].mean(), 2),
                                    "Installations": this["Installation"].nunique(),
                                    "Mort. %": round(this["Mortality %"].mean(), 1)}))
        rdf = pd.DataFrame(recs)
        rep.sections.append(Section(
            heading=f"{sl}  ({source})", level=2,
            blocks=[Block("narrative", _narrate(
                client, f"Overview of how seedlot {sl} ({source}) performed across the "
                f"installations where it is planted, versus the {source} group average.",
                dict(seedlot=sl, source=source, summary=rdf.to_dict("records")),
                _fallback_seedlot(sl, source, rdf))),
                Block("table", rdf, "Seedlot mean vs source-group average")]))
        # chart: seedlot mean by installation for the first year & metric present
        metric = spec.metrics[0]
        for y in spec.years:
            byinst = (store.seedlot_table
                      [(store.seedlot_table["Seedlot"].astype(str) == sl)
                       & (store.seedlot_table["Year"] == y)
                       & (store.seedlot_table["Metric"] == metric)])
            if byinst.empty:
                continue
            rep.sections.append(Section(
                heading=f"{sl} · {y} · {config.METRICS[metric]['short']}", level=3,
                blocks=[Block("figure", _fig_seedlot_by_installation(byinst, sl, metric),
                              "Mean by installation")]))
    return rep


def _year_report(spec, store, client):
    itype = spec.inst_type or "CORE"
    scope = " · ".join(x for x in [spec.region, itype] if x) or "all CORE installations"
    rep = Report(spec.title, f"{scope} · generated {_today()}")
    for y in spec.years:
        for m in spec.metrics:
            gdf = stats.gain_by_installation(store, region=spec.region, year=y, metric=m, inst_type=itype)
            if gdf.empty:
                continue
            summ = stats.summarize_for_llm(store, region=None, year=y, metric=m, inst_type="CORE") \
                if False else None
            disp = gdf[["installation", "region", "woods_mean", "improved_mean",
                        "gain_pct", "stars", "improved_mortality"]].copy()
            disp.columns = ["Installation", "Region", "Woods", "Improved", "Gain %", "Sig.", "Mort.%"]
            rep.sections.append(Section(
                heading=f"{y} · {config.METRICS[m]['short']}", level=2,
                blocks=[Block("figure", F.gain_chart(gdf, metric=m, height=380),
                              "Realized gain by site"),
                        Block("table", disp.round(2), "Site-by-site gain"),
                        Block("narrative", _narrate(
                            client, f"Summarise realized gain across CORE sites for {y}, "
                            f"{config.METRICS[m]['short']}.",
                            dict(year=y, metric=config.METRICS[m]["short"],
                                 sites=disp.to_dict("records")),
                            _fallback_year(y, m, gdf)))]))
    return rep


def _overall_report(spec, store, client):
    ov = stats.trial_overview(store)
    rep = Report("Overall Trial Report", f"All regions, years, metrics · generated {_today()}")
    comp = pd.DataFrame([{"Year": k, "Installations measured": v}
                         for k, v in ov["installations_measured_by_year"].items()])
    rep.sections.append(Section("Trial at a glance", level=2, blocks=[
        Block("narrative", _narrate(
            client, "Write a 3-4 sentence executive summary of the whole trial: overall "
            "direction of realized gain, the strongest metric, mortality, and the Year-3 "
            "caveat.", ov, _fallback_overall(ov))),
        Block("table", comp, "Data completeness"),
    ]))
    # gain by year/metric table + chart
    rows = []
    for y, md in ov["gain_by_year_and_metric_CORE_percent"].items():
        for met, d in md.items():
            rows.append(dict(Year=y, Metric=met, **{"Mean gain %": d["mean_gain_pct"],
                        "Sig.+": d["n_sig_positive"], "Sig.-": d["n_sig_negative"], "Sites": d["n_sites"]}))
    gdf = pd.DataFrame(rows)
    rep.sections.append(Section("Realized gain by year & metric (CORE)", level=2, blocks=[
        Block("figure", _fig_overall_gain(gdf), "Mean realized gain by year and metric"),
        Block("table", gdf, "")]))
    # top winners/losers
    pos = pd.DataFrame(ov["top_significant_positive_gains"])
    neg = pd.DataFrame(ov["top_significant_negative_gains"])
    blocks = []
    if not pos.empty:
        blocks.append(Block("table", pos[["site", "year", "metric", "gain_pct", "p"]], "Top significant gains"))
    if not neg.empty:
        blocks.append(Block("table", neg[["site", "year", "metric", "gain_pct", "p"]], "Significant under-performance"))
    mort = pd.DataFrame([{"Region": k, "Woods Run mort.%": v["woods_run"], "Improved mort.%": v["improved"]}
                         for k, v in ov["mean_mortality_by_region_percent"].items()])
    blocks.append(Block("table", mort, "Mortality by region"))
    rep.sections.append(Section("Highlights & survival", level=2, blocks=blocks))
    return rep


def _today():
    return _dt.date.today().strftime("%B %d, %Y")


# =========================================================================== #
# Report-specific figures
# =========================================================================== #
def _theme(fig, h=360):
    fig.update_layout(template="plotly_white", height=h, font=dict(family=config.FONT_FAMILY, size=12),
                      margin=dict(l=50, r=20, t=30, b=50), paper_bgcolor="white")
    return fig


def _fig_gain_by_metric(ygdf):
    fig = go.Figure(go.Bar(x=ygdf["Metric"], y=ygdf["Gain %"],
                    marker_color=[Color.POSITIVE if v >= 0 else Color.NEGATIVE for v in ygdf["Gain %"]],
                    text=[f"{v:+.1f}%" for v in ygdf["Gain %"]], textposition="outside"))
    fig.add_hline(y=0, line_color=Color.MUTED)
    fig.update_yaxes(title="Realized gain (%)", ticksuffix="%")
    return _theme(fig, 320)


def _fig_gain_trend(gdf):
    fig = go.Figure()
    for met in gdf["Metric"].unique():
        d = gdf[gdf["Metric"] == met].sort_values("Year")
        fig.add_trace(go.Scatter(x=d["Year"], y=d["Gain %"], mode="lines+markers", name=met))
    fig.add_hline(y=0, line_color=Color.MUTED)
    fig.update_yaxes(title="Realized gain (%)", ticksuffix="%")
    return _theme(fig, 340)


def _fig_seedlot_by_installation(byinst, sl, metric):
    d = byinst.sort_values("Average", ascending=False)
    fig = go.Figure(go.Bar(x=d["Installation"], y=d["Average"], marker_color=Color.WOODS,
                           text=[f"{v:.1f}" for v in d["Average"]], textposition="outside"))
    fig.update_yaxes(title=config.METRICS[metric]["axis"])
    fig.update_xaxes(tickangle=270)
    return _theme(fig, 360)


def _fig_overall_gain(gdf):
    fig = go.Figure()
    for met in gdf["Metric"].unique():
        d = gdf[gdf["Metric"] == met]
        fig.add_trace(go.Bar(name=met, x=d["Year"], y=d["Mean gain %"]))
    fig.add_hline(y=0, line_color=Color.MUTED)
    fig.update_layout(barmode="group"); fig.update_yaxes(title="Mean realized gain (%)", ticksuffix="%")
    return _theme(fig, 340)


# --------------------------------------------------------------------------- #
# Question-aware figures: growth trajectories over years + productivity scatter
# --------------------------------------------------------------------------- #
def _fig_traj(series, ytitle, *, height=340, pct=False, zero=False, xtitle="Measurement year"):
    """Generic multi-line trajectory. ``series`` is a list of
    {name, x, y, color?, dash?}. Used for 'how each line changes across years'."""
    fig = go.Figure()
    for s in series:
        fig.add_trace(go.Scatter(
            x=s["x"], y=s["y"], mode="lines+markers", name=s["name"],
            line=dict(color=s.get("color"), dash=s.get("dash"), width=2.5),
            marker=dict(size=8, line=dict(width=1, color="white")),
            connectgaps=True,
            hovertemplate="%{x}<br>%{y:.2f}<extra>" + str(s["name"]) + "</extra>"))
    if zero:
        fig.add_hline(y=0, line_color=Color.MUTED, line_dash="dot")
    fig.update_yaxes(title=ytitle, ticksuffix="%" if pct else None)
    fig.update_xaxes(title=xtitle, type="category")
    return _theme(fig, height)


def _source_growth_series(df, metric, years):
    """Two lines (Improved, Woods Run) of mean growth across years, from a frame
    that has Year/Source/Metric/Average columns."""
    sub = df[(df["Metric"] == metric) & (df["Year"].isin(years))]
    out = []
    for src, color in ((config.SOURCE_IMPROVED, Color.IMPROVED),
                       (config.SOURCE_WOODS, Color.WOODS)):
        s = sub[sub["Source"] == src].groupby("Year")["Average"].mean().reindex(years)
        if s.notna().any():
            out.append({"name": src, "x": list(years),
                        "y": [None if pd.isna(v) else round(float(v), 2) for v in s.values],
                        "color": color})
    return out


def _fig_productivity_scatter(gain_df, metric, rel):
    """ABSOLUTE realized gain (Improved - Woods Run, metric units) vs site
    productivity (Woods Run mean) — one point per site, with the fitted line.
    Absolute gain (not %) avoids the denominator coupling that would bias a
    gain-% regression against the Woods Run mean."""
    unit = config.METRICS[metric]["unit"]
    d = gain_df.dropna(subset=["woods_mean", "gain_abs"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["woods_mean"], y=d["gain_abs"], mode="markers+text", customdata=d["gain_pct"],
        text=d["installation"], textposition="top center", textfont=dict(size=8),
        marker=dict(size=11, color=[Color.POSITIVE if v >= 0 else Color.NEGATIVE for v in d["gain_abs"]],
                    line=dict(width=1, color="white")),
        hovertemplate="%{text}<br>Woods Run mean %{x:.1f}<br>Gain %{y:+.2f} " + unit
                      + "  (%{customdata:+.1f}%)<extra></extra>", name="Sites"))
    if rel and rel.get("n", 0) >= 3 and pd.notna(rel.get("slope")):
        xs = [float(d["woods_mean"].min()), float(d["woods_mean"].max())]
        ys = [rel["slope"] * x + rel["intercept"] for x in xs]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"fit (r={rel['r']:+.2f})",
                                 line=dict(color=Color.NAVY, dash="dash", width=2)))
    fig.add_hline(y=0, line_color=Color.MUTED, line_dash="dot")
    fig.update_xaxes(title=f"Site productivity — Woods Run mean {config.METRICS[metric]['short']} "
                           f"({config.METRICS[metric]['unit']})")
    fig.update_yaxes(title=f"Realized gain — Improved − Woods Run ({unit})")
    return _theme(fig, 360)


# =========================================================================== #
# Deterministic fallbacks (used when the LLM is unavailable)
# =========================================================================== #
def _fallback_installation(inst, gdf):
    if gdf.empty:
        return f"No measured data is available for {inst} in the selected years."
    g = gdf.dropna(subset=["Gain %"])
    mean = g["Gain %"].mean() if not g.empty else float("nan")
    nsig = (g["Sig."].isin(["*", "**", "***"])).sum()
    return (f"Across {gdf['Year'].nunique()} year(s) and {gdf['Metric'].nunique()} metric(s) at "
            f"{inst}, realized genetic gain averaged {_fmt(mean, pct=True, plus=True)}, with "
            f"{int(nsig)} significant comparison(s) (p<0.05).")


def _fallback_trend(inst, gdf):
    return _fallback_installation(inst, gdf)


def _fallback_seedlot(sl, source, rdf):
    if rdf.empty:
        return f"No measured data is available for seedlot {sl}."
    return (f"Seedlot {sl} ({source}) is summarised below across the installations where it is "
            f"planted, alongside the {source} group average for context.")


def _fallback_year(y, m, gdf):
    g = gdf.dropna(subset=["gain_pct"])
    return (f"In {y} ({config.METRICS[m]['short']}), realized gain across {len(gdf)} CORE sites "
            f"averaged {_fmt(g['gain_pct'].mean(), pct=True, plus=True)}; "
            f"{int(g['significant'].sum())} site(s) were significant.")


def _fallback_overall(ov):
    return ("This report summarises realized genetic gain across all installations, years and "
            "metrics. " + ov["key_notes"])


# =========================================================================== #
# Tiny Markdown -> HTML (for the export; the on-screen view uses dcc.Markdown)
# =========================================================================== #
def _md_to_html(md: str) -> str:
    out, in_ul = [], False
    for raw in (md or "").split("\n"):
        line = raw.rstrip()
        ls = line.strip()
        # process inline formatting on the content part
        b = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _html.escape(line))
        b = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", b)
        # bullet: support both "- " and "* " markers
        if ls.startswith("- ") or ls.startswith("* "):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            content = ls[2:]
            bc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _html.escape(content))
            bc = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", bc)
            out.append("<li>" + bc + "</li>")
            continue
        if in_ul:
            out.append("</ul>"); in_ul = False
        if line.startswith("### "):
            out.append("<h4>" + b[4:] + "</h4>")
        elif line.startswith("## "):
            out.append("<h3>" + b[3:] + "</h3>")
        elif ls:
            out.append("<p>" + b + "</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


# =========================================================================== #
# On-screen Dash view
# =========================================================================== #
def to_components(report: Report):
    from dash import dcc, html
    from . import components as C
    GC = {"displaylogo": False, "displayModeBar": False, "responsive": True}

    def block(b: Block):
        if b.type == "narrative":
            return dcc.Markdown(b.payload, className="rep-narr")
        if b.type == "kpis":
            return html.Div([C.kpi(lbl, val, sub) for (lbl, val, sub) in b.payload],
                            className="kpi-row")
        if b.type == "table":
            df = b.payload
            t = C.data_table(df, height="auto", numeric_cols=[c for c in df.columns
                             if df[c].dtype.kind in "fi"])
            return html.Div([html.Div(b.title, className="rep-block-title") if b.title else None, t])
        if b.type == "figure":
            return html.Div([html.Div(b.title, className="rep-block-title") if b.title else None,
                             dcc.Graph(figure=b.payload, config=GC, style={"height": "380px"})])
        if b.type == "note":
            return dcc.Markdown(str(b.payload), className="rep-note")
        return html.Div(str(b.payload))

    secs = []
    for s in report.sections:
        tag = html.H3 if s.level <= 2 else html.H4
        head = [tag(s.heading, className="rep-h")] if s.heading else []
        secs.append(html.Div(head + [block(b) for b in s.blocks],
                             className=f"rep-section lvl{s.level}"))
    return html.Div([
        html.Div([
            html.Img(src=IFC_LOGO, className="rep-logo"),
            html.Div([html.H2("Realized Genetic Gain Trials", className="rep-title"),
                      html.H3(report.title, className="rep-subtitle"),
                      html.P(report.subtitle, className="rep-meta")]),
        ], className="rep-header"),
        html.Div(secs, className="rep-sections"),
        html.P("© Intermountain Forestry Cooperative · University of Idaho — all figures derived "
               "from the trial data; no values were invented.", className="rep-foot"),
    ], className="report-doc")


# =========================================================================== #
# Self-contained HTML export
# =========================================================================== #
def to_html(report: Report) -> str:
    import plotly.io as pio
    parts, first = [], True
    for s in report.sections:
        tag = "h2" if s.level <= 2 else "h3"
        if s.heading:
            parts.append(f'<{tag} class="rh">{_html.escape(s.heading)}</{tag}>')
        for b in s.blocks:
            if b.type == "narrative":
                parts.append('<div class="narr">' + _md_to_html(b.payload) + '</div>')
            elif b.type == "kpis":
                cells = "".join(
                    f'<div class="kpi"><div class="kl">{_html.escape(str(l))}</div>'
                    f'<div class="kv">{_html.escape(str(v))}</div>'
                    f'<div class="ks">{_html.escape(str(sub))}</div></div>'
                    for (l, v, sub) in b.payload)
                parts.append(f'<div class="kpirow">{cells}</div>')
            elif b.type == "table":
                if b.title:
                    parts.append(f'<div class="bt">{_html.escape(b.title)}</div>')
                parts.append(b.payload.to_html(index=False, border=0,
                             classes="rep-table", float_format=lambda x: f"{x:.2f}"))
            elif b.type == "note":
                parts.append('<div class="note">' + _md_to_html(str(b.payload)) + '</div>')
            elif b.type == "figure":
                if b.title:
                    parts.append(f'<div class="bt">{_html.escape(b.title)}</div>')
                parts.append(pio.to_html(b.payload, include_plotlyjs=("cdn" if first else False),
                                         full_html=False, config={"displayModeBar": False}))
                first = False
    body = "\n".join(parts)
    css = """
    body{font-family:Inter,'Segoe UI',Arial,sans-serif;color:#1f2933;margin:0;background:#f4f7fa}
    .wrap{max-width:1000px;margin:0 auto;background:#fff;padding:0 0 40px}
    .hdr{display:flex;align-items:center;gap:18px;background:linear-gradient(120deg,#16467a,#0f3257);
      color:#fff;padding:22px 32px}
    .hdr img{height:60px;background:#fff;border-radius:8px;padding:4px}
    .hdr h1{margin:0;font-size:22px}.hdr h2{margin:3px 0 0;font-size:16px;color:#DBA800;font-weight:600}
    .hdr p{margin:4px 0 0;font-size:12px;color:#cfe0f0}
    .content{padding:10px 32px}
    h2.rh{color:#16467a;border-left:4px solid #DBA800;padding-left:10px;margin:26px 0 8px}
    h3.rh{color:#2F6E8F;margin:18px 0 6px}
    .narr p{line-height:1.55;margin:6px 0}.narr ul{margin:6px 0 6px 18px}
    .bt{font-weight:700;color:#16467a;margin:12px 0 4px;font-size:13px}
    table.rep-table{border-collapse:collapse;width:100%;font-size:12.5px;margin:4px 0 10px}
    table.rep-table th{background:#16467a;color:#fff;padding:6px 8px;text-align:center}
    table.rep-table td{padding:5px 8px;border-bottom:1px solid #e6eaee;text-align:center}
    table.rep-table tr:nth-child(even){background:#f4f7fa}
    .kpirow{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
    .kpi{flex:1;min-width:150px;border:1px solid #dce3ea;border-top:3px solid #16467a;border-radius:10px;padding:10px 12px}
    .kl{font-size:11px;color:#5b6671;text-transform:uppercase;font-weight:600}
    .kv{font-size:22px;font-weight:750;color:#16467a}.ks{font-size:11px;color:#5b6671}
    .note{background:#fff8e1;border-left:4px solid #DBA800;padding:10px 14px;margin:10px 0;
      border-radius:6px;font-size:13px;color:#5b4a00}.note p{margin:4px 0}
    .foot{color:#5b6671;font-size:11px;padding:18px 32px;border-top:1px solid #e6eaee;margin-top:20px}
    @media print{body{background:#fff}.wrap{max-width:none}}
    """
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(report.title)}</title><style>{css}</style></head><body>"
            f"<div class='wrap'><div class='hdr'>"
            f"<img src='{IFC_LOGO}'><div><h1>Realized Genetic Gain Trials</h1>"
            f"<h2>{_html.escape(report.title)}</h2><p>{_html.escape(report.subtitle)}</p></div></div>"
            f"<div class='content'>{body}</div>"
            f"<div class='foot'>© Intermountain Forestry Cooperative · University of Idaho — "
            f"all figures derived from the trial data; no values were invented.</div>"
            f"</div></body></html>")


# =========================================================================== #
# Dynamic scope summary + analytical wrapper sections (exec / findings / caveats)
# =========================================================================== #
def _scope_summary(spec: ReportSpec, store) -> dict:
    out = {"report_type": spec.kind, "title": spec.title, "years": spec.years,
           "metrics": [config.METRICS[m]["short"] for m in spec.metrics],
           "filters": {"source": spec.source, "region": spec.region,
                       "site_type": spec.inst_type, "focus": spec.focus or None}}
    if spec.seedlot_corrections:
        out["seedlot_id_corrections"] = {
            "note": "The requested id(s) were not in the catalog and were auto-corrected to the "
                    "closest real seedlot. State this correction in the report.",
            "mapping": spec.seedlot_corrections}
    if spec.seedlots_not_found:
        out["seedlots_not_found"] = spec.seedlots_not_found
    if spec.compare_axis:
        cmp = {"axis": spec.compare_axis, "items": spec.compare_items,
               "value": ("realized gain %" if spec.compare_axis in ("installation", "site_type")
                         else "mean growth"), "by_metric": {}}
        for m in spec.metrics:
            ms = config.METRICS[m]["short"]
            cmp["by_metric"][ms] = {
                _cmp_label(spec.compare_axis, it): {
                    y: _none_round(_cmp_value(store, spec.compare_axis, it, y, m, spec))
                    for y in spec.years}
                for it in spec.compare_items}
        out["comparison"] = cmp
    if spec.installations and spec.kind == "installation":
        d = {}
        plotd = {}
        survd = {}
        for inst in spec.installations:
            g = _gain_rows_for_installation(store, inst, _region_of(store, inst),
                                            spec.years, spec.metrics)
            d[inst] = g.round(2).to_dict("records")
            # Plot means + survival/defects for EVERY in-scope metric, not just one.
            pm_metrics = {}
            for m in spec.metrics:
                pd_ = _plot_detail(store, inst, spec.years, m)
                if pd_:
                    pm_metrics[config.METRICS[m]["short"]] = pd_
            if pm_metrics:
                plotd[inst] = pm_metrics
            sv_metrics = {}
            for m in spec.metrics:
                sv = _survival_defects(store, inst, spec.years, m)
                if sv:
                    sv_metrics[config.METRICS[m]["short"]] = sv
            if sv_metrics:
                survd[inst] = sv_metrics
        out["installations"] = d
        if plotd:
            out["installations_plot_means"] = {
                "metrics": [config.METRICS[m]["short"] for m in spec.metrics],
                "note": "Plots 1-3 = Woods Run (W), Plots 4-6 = Improved (I); means per plot per year, per metric.",
                "by_installation": plotd}
        if survd:
            out["installations_survival_defects"] = {"by_installation": survd}
    if spec.seedlots:
        d = {}
        base = store.seedlot_table
        if spec.region:
            base = base[base["Region"] == spec.region]
        inst_set = set(spec.installations) if spec.installations else None
        pm = spec.metrics[0]
        for sl in spec.seedlots:
            sub = base[base["Seedlot"].astype(str) == sl]
            if inst_set:
                sub = sub[sub["Installation"].isin(inst_set)]
            source = sub["Source"].iloc[0] if not sub.empty else "?"
            recs = []
            for y in spec.years:
                for m in spec.metrics:
                    this = sub[(sub["Year"] == y) & (sub["Metric"] == m)]
                    grp = base[(base["Source"] == source) & (base["Year"] == y) & (base["Metric"] == m)]
                    if inst_set:
                        grp = grp[grp["Installation"].isin(inst_set)]
                    if this.empty:
                        continue
                    recs.append(dict(year=y, metric=config.METRICS[m]["short"],
                                     seedlot_mean=round(float(this["Average"].mean()), 2),
                                     group_mean=round(float(grp["Average"].mean()), 2),
                                     installations=int(this["Installation"].nunique()),
                                     mortality=round(float(this["Mortality %"].mean()), 1)))
            byinst = (sub[sub["Metric"] == pm].groupby("Installation")["Average"]
                      .mean().round(2).sort_values(ascending=False).to_dict())
            d[sl] = {"source": source, "records": recs,
                     f"mean_by_installation_{config.METRICS[pm]['short']}": byinst}
        out["seedlots"] = d
        out["multiple_seedlots_compared"] = len(spec.seedlots) > 1
    if spec.kind == "seedlot_group" and spec.source:
        st = store.seedlot_table[store.seedlot_table["Source"] == spec.source]
        if spec.region:
            st = st[st["Region"] == spec.region]
        pm = spec.metrics[0]
        per = []
        for sl in sorted(st["Seedlot"].astype(str).unique()):
            sub = st[st["Seedlot"].astype(str) == sl]
            rec = {"seedlot": sl, "installations": int(sub["Installation"].nunique()),
                   "mortality_pct": round(float(sub["Mortality %"].mean()), 1)}
            for m in spec.metrics:
                d = sub[sub["Metric"] == m]
                if not d.empty:
                    rec[config.METRICS[m]["short"] + "_mean"] = round(float(d["Average"].mean()), 2)
            dpm = sub[sub["Metric"] == pm].groupby("Installation")["Average"].mean()
            if not dpm.empty:
                rec["best_at"] = {"site": dpm.idxmax(), "mean": round(float(dpm.max()), 2)}
                rec["worst_at"] = {"site": dpm.idxmin(), "mean": round(float(dpm.min()), 2)}
            per.append(rec)
        key = config.METRICS[pm]["short"] + "_mean"
        per.sort(key=lambda r: r.get(key, -1e9), reverse=True)
        out["seedlot_group"] = {"source": spec.source,
                                "primary_metric": config.METRICS[pm]["short"],
                                "n_seedlots": len(per),
                                "seedlots_ranked_best_to_worst": per}
    if spec.kind == "region_compare" and spec.regions:
        comp = {}
        for R in spec.regions:
            ym = {}
            for y in spec.years:
                for m in spec.metrics:
                    g = stats.gain_by_installation(store, region=R, year=y, metric=m, inst_type="CORE")
                    if g.empty:
                        continue
                    v = g["gain_pct"].dropna()
                    ym.setdefault(y, {})[config.METRICS[m]["short"]] = dict(
                        mean_gain_pct=round(float(v.mean()), 1) if not v.empty else None,
                        n_sites=int(len(g)), n_significant=int(g["significant"].sum()),
                        mean_woods=round(float(g["woods_mean"].mean()), 2),
                        mean_improved=round(float(g["improved_mean"].mean()), 2),
                        mean_improved_mortality=round(float(g["improved_mortality"].mean()), 1))
            comp[R] = {"installations": list(store.installations(R)), "by_year_and_metric": ym}
        out["region_comparison"] = comp
    if (spec.kind in ("year", "overall", "seedlot_group") or
            (not spec.installations and not spec.seedlots)) and spec.kind != "region_compare":
        yr = {}
        for y in spec.years:
            yr[y] = {}
            for m in spec.metrics:
                g = stats.gain_by_installation(store, region=spec.region, year=y, metric=m,
                                               inst_type=(spec.inst_type or "CORE"))
                if g.empty:
                    continue
                v = g["gain_pct"].dropna()
                yr[y][config.METRICS[m]["short"]] = dict(
                    mean_gain_pct=round(float(v.mean()), 1) if not v.empty else None,
                    n_sites=int(len(g)), n_significant=int(g["significant"].sum()),
                    best=dict(site=g.iloc[0]["installation"], gain=g.iloc[0]["gain_pct"]) if len(g) else None,
                    worst=dict(site=g.iloc[-1]["installation"], gain=g.iloc[-1]["gain_pct"]) if len(g) else None)
        out["gain_by_year_and_metric"] = yr
    out["trial_context"] = stats.trial_overview(store)
    return out


def _section_exec(spec, summ, client):
    fb = "This report summarises realized genetic gain for the requested scope. " + \
         summ["trial_context"]["key_notes"]
    txt = _narrate(client,
        "Write a 2-4 paragraph EXECUTIVE SUMMARY for this report. Open with the scope, then "
        "interpret: the overall direction and magnitude of realized genetic gain, where Improved "
        "stock clearly helped or under-performed, survival/mortality concerns, and the single "
        "headline takeaway for the cooperative. Interpret the numbers — do not just list them.",
        summ, fb, deep=True)
    return Section("Executive summary", level=2, blocks=[Block("narrative", txt)])


def _section_findings(spec, summ, client):
    fb = "- Refer to the tables and charts above for the detailed figures."
    txt = _narrate(client,
        "Write a KEY FINDINGS list of 4-8 concise '- ' bullets capturing the most decision-relevant "
        "results for this scope: strongest and weakest performers, significant gains and losses, "
        "year-over-year trends, mortality, and anything that stands out. Each bullet should cite the "
        "relevant number.", summ, fb, deep=True)
    return Section("Key findings", level=2, blocks=[Block("narrative", txt)])


def _section_caveats(spec, summ, client):
    fb = ("- Year 3 is under-sampled (only a few sites measured); its averages are unreliable.\n"
          "- Significance uses seedlot-entry means (Welch t-test); non-significant results are "
          "inconclusive, not evidence of no effect.\n"
          "- Improved stock tends to show higher mortality than the checks; weigh growth gains "
          "against survival before any deployment decision.")
    txt = _narrate(client,
        "Write a CAVEATS & RECOMMENDATIONS section (2-3 short paragraphs or bullets): the statistical "
        "limitations (small samples, pseudo-replication, under-sampled Year 3), the growth-vs-"
        "survival trade-off, and cautious, practical recommendations for deployment or further "
        "measurement — based ONLY on the data provided.", summ, fb, deep=True)
    return Section("Caveats & recommendations", level=2, blocks=[Block("narrative", txt)])


def _subtitle(spec):
    bits = []
    if spec.installations: bits.append("Installations: " + ", ".join(spec.installations))
    if spec.seedlots:      bits.append("Seedlots: " + ", ".join(spec.seedlots))
    if spec.source:        bits.append(spec.source)
    if spec.region:        bits.append(spec.region)
    if spec.regions:       bits.append(" vs ".join(spec.regions))
    if spec.inst_type:     bits.append(spec.inst_type)
    bits.append("Years: " + ", ".join(spec.years))
    return " \u00b7 ".join(bits) + f" \u00b7 generated {_today()}"


REPORT_SYS = (
    "You are ForestTask, a forest-biometrics analyst writing a formal, IFC-branded report on the "
    "Realized Genetic Gain Trials (RGT). The trials compare genetically IMPROVED Douglas-fir against "
    "local WOODS RUN (unimproved) checks across installations in two regions: the Inland Northwest "
    "(INW) and the Klamath-Siskiyou (K-S), over three measurement years and three growth metrics "
    "(caliper, height, volume).\n\n"
    "DEFINITIONS AND METHODOLOGY:\n"
    "- Realized genetic gain (%) = (Improved mean - Woods Run mean) / Woods Run mean x 100. "
    "This follows the standard realized-gain formula for forest tree improvement programs "
    "(White, Adams & Neale 2007, *Forest Genetics*, CABI; Zobel & Talbert 1984, *Applied Forest "
    "Tree Improvement*, Wiley). A positive value means genetically improved stock grew faster.\n"
    "- Growth means (hence gain) are computed on SURVIVING ORIGINAL trees only: trees coded dead "
    "or replacement are excluded, so genetic gain is not confounded with the younger age of "
    "interplanted replacements. Mortality is analysed separately and counts those trees.\n"
    "- Statistical significance: Welch two-sample t-test on seedlot (genetic-entry) means \u2014 NOT "
    "individual tree means \u2014 to respect the pseudo-replication structure of progeny trials "
    "(Cotterill & Dean 1990, *Successful Tree Breeding with Index Selection*, CSIRO). "
    "Thresholds: * p<0.05, ** p<0.01, *** p<0.001. Non-significant results are inconclusive.\n"
    "- Gain vs site productivity: Pearson r between the Woods Run site mean (used as a proxy for "
    "inherent site productivity) and ABSOLUTE realized gain (Improved - Woods Run, in metric units). "
    "Absolute gain, not gain %, is used because gain % carries the Woods Run mean in its denominator, "
    "so regressing it on that same mean would manufacture a spurious negative slope. A negative r "
    "indicates that gains are larger on poorer sites \u2014 a common pattern in Douglas-fir breeding "
    "('G\u00d7E interaction') described by Stonecypher et al. (1996, *Silvae Genetica* 45:148-157) and "
    "White et al. (2007). A positive r means gains are larger on better sites.\n"
    "- CORE = main trial sites; TRANSFER = off-site climate-transfer tests.\n\n"
    "REPORTING RULES:\n"
    "Write professional, INTERPRETIVE Markdown prose. Use '- ' bullets for lists of findings. "
    "Use '## ' for main sections, '### ' for sub-sections. "
    "Explain what the numbers mean, compare entities, note significance and practical implications. "
    "When discussing realized gain or gain vs productivity, briefly note the calculation method and "
    "cite the relevant methodology (e.g. 'following White et al. 2007'). "
    "Ground EVERY number STRICTLY in the DATA JSON provided \u2014 never invent, re-round, or recall "
    "outside figures. Be cautious about non-significant results, small samples and the under-sampled "
    "Year 3. No LaTeX, no images. Use '- ' for all bullet points.")


def _write_full_report(client, spec, data, outline="") -> str:
    """DRAFT pass: one model call writes the whole narrative, answering the SPECIFIC request."""
    req = (spec.raw or spec.title).strip()
    scope_line = (
        f"SCOPE (honor exactly \u2014 do NOT widen it): years = {', '.join(spec.years)}; "
        f"metrics = {', '.join(config.METRICS[m]['short'] for m in spec.metrics)}; "
        f"installations = {', '.join(spec.installations) or 'all in scope'}; "
        f"seedlots = {', '.join(spec.seedlots) or 'all in scope'}; "
        f"source = {spec.source or 'both (Improved vs Woods Run)'}; "
        f"region = {spec.region or (' vs '.join(spec.regions) if spec.regions else 'all')}; "
        f"site type = {spec.inst_type or 'all'}.")
    instruction = (
        f"Write a COMPREHENSIVE, DETAILED report that DIRECTLY answers this request:\n\"{req}\"\n\n"
        f"{scope_line}\n"
        "If the request names a single year (e.g. 'year 1'), the SCOPE above already restricts the "
        "data to that year \u2014 discuss ONLY that year; never report other years.\n\n"
        "Structure the report with EXACTLY these eight Markdown section headings, in this order, each "
        "written verbatim as a '## ' heading with NOTHING appended \u2014 no dash, no colon, no description "
        "on the heading line. The heading is the short title only:\n"
        "## Executive summary\n"
        "## Realized genetic gain\n"
        "## Site / installation detail\n"
        "## Seedlot detail\n"
        "## Plot-level & spatial pattern\n"
        "## Survival & defects\n"
        "## Key findings\n"
        "## Caveats & recommendations\n\n"
        "Be thorough \u2014 this is a formal technical report, not a summary; aim for depth and use EVERY "
        "relevant number in the DATA. Content for each section (write this as the body BELOW the heading, "
        "never in the heading itself):\n"
        "- Executive summary: the scope and the headline answer to the request.\n"
        "- Realized genetic gain: Improved vs Woods Run for the scope, broken down by year and metric "
        "\u2014 magnitudes, direction, statistical significance (cite p / stars), and which sites or "
        "entities drive the result.\n"
        "- Site / installation detail: go installation-by-installation where the DATA provides it; the "
        "best- and worst-performing sites with numbers.\n"
        "- Seedlot detail: if the DATA contains per-seedlot or seedlot-ranking figures, name the standout "
        "seedlots (best AND worst, with numbers) and how individual seedlots behave across installations.\n"
        "- Plot-level & spatial pattern: if the DATA contains per-plot means ('installations_plot_means'), "
        "interpret the plot layout \u2014 how Woods plots (1-3) compare with Improved plots (4-6) and any "
        "within-site spatial variability.\n"
        "- Survival & defects: if the DATA contains survival/defect figures, report mortality and defect "
        "rates by source and the growth-vs-survival trade-off.\n"
        "- Key findings: 5-9 '- ' bullets of the most decision-relevant results, each citing a number.\n"
        "- Caveats & recommendations: limitations and cautious, practical recommendations.\n\n"
        "RULES: Answer the SPECIFIC request; never fall back to a generic whole-trial summary when a "
        "particular entity, filter or year was asked for. Cover EVERY metric present in the DATA "
        "(caliper, height AND volume) unless the request named fewer — never report only one metric "
        "when several are present. If the request uses a superlative or comparison ('best', 'top', "
        "'worst', 'highest', 'lowest', 'X vs Y'), identify the specific entities that satisfy it from "
        "the DATA and name them with their numbers. OMIT a section only if the DATA truly has nothing "
        "for it. Use ONLY numbers present in the DATA JSON. Be exhaustive but precise.\n"
        "NEVER claim the dataset 'aggregates only by source' or 'lacks individual seedlot data' — "
        "per-seedlot means, mortality and per-installation breakdowns ARE provided when a seedlot is "
        "in scope; use them. If 'seedlot_id_corrections' is present, OPEN the report by stating the "
        "requested id was not found and that the closest real seedlot is reported instead.")
    if outline:
        instruction += (
            "\n\nThe report is accompanied by these computed FIGURES and TABLES (rendered after your "
            "text). Refer to each by name in the relevant section so every visual is explained — e.g. "
            "'the growth-over-years trajectory shows…', 'the per-plot table indicates…':\n" + outline)
    if client is None or not getattr(client, "configured", False):
        return _fallback_full(spec, data)
    msgs = [{"role": "system", "content": REPORT_SYS},
            {"role": "system", "content": "DATA (the only numbers you may cite):\n"
             + json.dumps(data, default=str)},
            {"role": "user", "content": instruction}]
    try:
        r = client.chat(msgs, model=config.MindRouter.LARGE_MODEL,
                        max_tokens=config.MindRouter.MAX_TOKENS,
                        reasoning_effort="high", timeout=300)
        if r.get("ok") and r.get("content"):
            return r["content"]
    except Exception:
        pass
    return _fallback_full(spec, data)


# =========================================================================== #
# Evaluator–optimizer: an expert reviewer critiques the draft, then it is revised
# =========================================================================== #
REPORT_RUBRIC = (
    "RGT REPORT QUALITY RUBRIC — a complete, excellent report must:\n"
    "1. Answer the EXACT request and honor its scope (years/metrics/entities) — no scope drift.\n"
    "2. State realized gain for EVERY in-scope metric (caliper, height, volume) with direction, "
    "magnitude, and statistical significance (p / stars); never report only one metric.\n"
    "3. Name the specific standouts — best AND worst sites and seedlots — WITH their numbers.\n"
    "4. Interpret time trend (how growth/gain changes across years), not just single-year values.\n"
    "5. Address survival: Improved vs Woods mortality and the growth-vs-survival trade-off.\n"
    "6. Where present, interpret spatial/plot pattern, G×E / seedlot stability, and damage agents.\n"
    "7. Reference the accompanying figures/tables by name so each visual is explained.\n"
    "8. End with a clear, decision-grade recommendation (deploy / hold / which seedlots) with caveats "
    "(small samples, under-sampled Year 3, non-significance ≠ no effect).\n"
    "9. Cite ONLY numbers in the DATA; be specific and quantitative, never vague.")


def _critique_report(client, spec, data, draft) -> str:
    """CRITIC pass: a senior forest geneticist scores the draft against the rubric and
    lists concrete, fixable deficiencies. Returns '' if the draft already passes."""
    if client is None or not getattr(client, "configured", False) or not draft:
        return ""
    msgs = [
        {"role": "system", "content":
            "You are a senior forest geneticist and biometrician peer-reviewing a colleague's draft "
            "RGT report. Be exacting. Using the RUBRIC and the DATA, list the SPECIFIC, actionable "
            "deficiencies of the DRAFT: missing metrics, un-named standouts, numbers that should be "
            "cited but aren't, missing trend/survival/G×E interpretation, figures not referenced, a "
            "weak or absent recommendation, or any vagueness. Output a terse '- ' bullet list of fixes "
            "only (no praise, no rewrite). If the draft already satisfies every rubric point, output "
            "exactly 'PASS'."},
        {"role": "system", "content": REPORT_RUBRIC},
        {"role": "system", "content": "DATA:\n" + json.dumps(data, default=str)},
        {"role": "user", "content": "DRAFT REPORT:\n\n" + draft}]
    try:
        r = client.chat(msgs, model=config.MindRouter.LARGE_MODEL, max_tokens=2000,
                        reasoning_effort="high", timeout=180)
        c = (r.get("content") or "").strip() if r.get("ok") else ""
        return "" if c.upper().startswith("PASS") else c
    except Exception:
        return ""


def _revise_report(client, spec, data, draft, critique) -> str:
    """REVISE pass: rewrite the draft to fix every deficiency the critic raised."""
    if client is None or not getattr(client, "configured", False) or not critique:
        return draft
    msgs = [
        {"role": "system", "content": REPORT_SYS},
        {"role": "system", "content": "DATA (the only numbers you may cite):\n"
            + json.dumps(data, default=str)},
        {"role": "user", "content":
            "Revise the DRAFT into the FINAL report, fixing EVERY point in the REVIEW. Keep everything "
            "that was correct; add the missing analysis and numbers; keep the section structure; make "
            "it specific, quantitative and decision-grade. Output ONLY the final Markdown report.\n\n"
            "REVIEW (fix all of these):\n" + critique + "\n\nDRAFT:\n\n" + draft}]
    try:
        r = client.chat(msgs, model=config.MindRouter.LARGE_MODEL,
                        max_tokens=config.MindRouter.MAX_TOKENS, reasoning_effort="high", timeout=300)
        if r.get("ok") and r.get("content"):
            return r["content"]
    except Exception:
        pass
    return draft


def _evidence_outline(sections) -> str:
    """Compact list of the figures & tables that will accompany the report, so the
    writer can reference each by name."""
    lines = []
    for s in sections:
        for b in s.blocks:
            if b.type in ("figure", "table") and b.title:
                lines.append(f"- {b.type.upper()}: {b.title}")
    return "\n".join(lines)


# Canonical narrative section titles. If the model ever echoes the prompt's
# guidance into a heading (e.g. "## Key findings — 5-9 bullets ..."), collapse it
# back to the clean title.
_REPORT_HEADINGS = (
    "Executive summary", "Realized genetic gain", "Site / installation detail",
    "Seedlot detail", "Plot-level & spatial pattern", "Survival & defects",
    "Key findings", "Caveats & recommendations",
)


def _normalize_headings(md: str) -> str:
    """Force every Markdown heading that starts with a known section title down to
    just that title, stripping any dash/colon guidance the model appended."""
    if not md:
        return md
    out = []
    for line in md.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            hashes = stripped[:len(stripped) - len(stripped.lstrip("#"))]
            title = stripped[len(hashes):].strip()
            low = title.lower()
            for h in _REPORT_HEADINGS:
                if low.startswith(h.lower()) and low != h.lower():
                    line = f"{hashes} {h}"
                    break
        out.append(line)
    return "\n".join(out)


def _compose_report(client, spec, data, evidence) -> str:
    """Full generation pipeline: DRAFT -> expert CRITIQUE -> REVISE. Each stage falls
    back safely to the previous result so a report is always produced. The final
    Markdown is heading-normalized so section titles are always clean."""
    outline = _evidence_outline(evidence)
    draft = _write_full_report(client, spec, data, outline)
    critique = _critique_report(client, spec, data, draft)
    final = draft if not critique else _revise_report(client, spec, data, draft, critique)
    return _normalize_headings(final)


def _fallback_full(spec, data) -> str:
    ov = data.get("trial_context", {})
    out = ["## Executive summary",
           f"This report addresses: *{(spec.raw or spec.title)}*. All figures below are computed "
           "directly from the trial data; see the charts and tables that follow."]
    by = data.get("gain_by_year_and_metric")
    if by:
        out.append("## Analysis")
        for y, md in by.items():
            for met, d in md.items():
                if d.get("mean_gain_pct") is None:
                    continue
                out.append(f"- **{y} \u00b7 {met}:** mean realized gain "
                           f"{d['mean_gain_pct']:+.1f}% across {d['n_sites']} sites, "
                           f"{d['n_significant']} significant; best {d['best']['site']} "
                           f"({d['best']['gain']:+.1f}%).")
    if data.get("installations"):
        out.append("## Analysis")
        for inst, rows in data["installations"].items():
            gs = [r["Gain %"] for r in rows if r.get("Gain %") is not None]
            if gs:
                out.append(f"- **{inst}:** mean gain {sum(gs)/len(gs):+.1f}% over {len(rows)} "
                           "year/metric comparisons.")
    out.append("## Key findings")
    out.append("- " + ov.get("key_notes", "See the tables and charts below for details.")
               .replace(". ", ".\n- "))
    out.append("## Caveats & recommendations")
    out.append("- Year 3 is under-sampled; its averages are unreliable.\n"
               "- Non-significant results are inconclusive, not evidence of no effect.\n"
               "- Improved stock shows higher mortality than the checks \u2014 weigh growth gains "
               "against survival before deployment.")
    return "\n\n".join(out)


def _none_round(v, n=2):
    return None if v is None else round(float(v), n)


def _cmp_label(axis, item):
    if axis == "site_type":
        return "CORE" if item == "CORE" else "TRANSFER"
    return str(item)


def _cmp_value(store, axis, item, year, metric, spec):
    """The comparison metric for one item in one year. Seedlot -> mean growth;
    installation / site_type -> realized gain %."""
    if axis == "seedlot":
        st = store.seedlot_table
        sub = st[(st["Seedlot"].astype(str) == str(item)) & (st["Year"] == year) & (st["Metric"] == metric)]
        if spec.installations:
            sub = sub[sub["Installation"].isin(spec.installations)]
        if spec.region:
            sub = sub[sub["Region"] == spec.region]
        return float(sub["Average"].mean()) if not sub.empty else None
    if axis == "installation":
        r = stats.compare_sources(store, region=_region_of(store, item),
                                  installation=item, year=year, metric=metric)
        return r.gain_pct if r else None
    if axis == "site_type":
        g = stats.gain_by_installation(store, region=spec.region, year=year, metric=metric, inst_type=item)
        v = g["gain_pct"].dropna() if not g.empty else None
        return float(v.mean()) if (v is not None and not v.empty) else None
    return None


def _comparison_section(spec, store):
    """General side-by-side comparison for ANY axis (seedlot / installation /
    site_type): per metric, a Year x items table + a trajectory line per item."""
    axis, items = spec.compare_axis, spec.compare_items
    pct = axis in ("installation", "site_type")
    palette = [Color.NAVY, Color.IMPROVED, Color.WOODS, Color.GOLD, Color.POSITIVE, Color.NEGATIVE]
    secs = []
    for metric in spec.metrics:
        ms = config.METRICS[metric]["short"]
        series, rows = [], []
        for idx, item in enumerate(items):
            lbl = _cmp_label(axis, item)
            xs, ys = [], []
            for y in spec.years:
                v = _cmp_value(store, axis, item, y, metric, spec)
                xs.append(y); ys.append(None if v is None else round(v, 2))
            series.append({"name": lbl, "x": xs, "y": ys, "color": palette[idx % len(palette)]})
        for y in spec.years:
            row = {"Year": y}
            for item in items:
                v = _cmp_value(store, axis, item, y, metric, spec)
                row[_cmp_label(axis, item)] = None if v is None else round(v, 2)
            rows.append(row)
        ytitle = "Realized gain (%)" if pct else config.METRICS[metric]["axis"]
        what = "realized gain %" if pct else f"mean {config.METRICS[metric]['unit']}"
        blocks = [Block("table", pd.DataFrame(rows), f"{ms} — {what} by {axis.replace('_', ' ')}"),
                  Block("figure", _fig_traj(series, ytitle, pct=pct, zero=pct),
                        f"{ms} over years — {' vs '.join(_cmp_label(axis, i) for i in items)}")]
        secs.append(Section(f"Comparison — {ms}", level=2, blocks=blocks))
    return secs


def _deployment_section(spec, store):
    """Manager bottom line: expected gain per metric, significance, survival cost,
    a deploy/hold verdict, and the recommended Improved seedlots. Uses the latest
    in-scope year for the headline."""
    hy = spec.years[-1]
    insts = spec.installations if (spec.kind == "installation" and spec.installations) else None
    kpis, rows = [], []
    for m in spec.metrics:
        ms = config.METRICS[m]["short"]
        if insts:
            rs = [stats.compare_sources(store, region=_region_of(store, i), installation=i,
                                        year=hy, metric=m) for i in insts]
            rs = [r for r in rs if r and pd.notna(r.gain_pct)]
            if not rs:
                continue
            meang = sum(r.gain_pct for r in rs) / len(rs)
            nsig = sum(1 for r in rs if r.significant and r.gain_pct > 0)
            N = len(rs)
            imort = float(np.nanmean([r.improved_mortality for r in rs]))
            wmort = float(np.nanmean([r.woods_mortality for r in rs]))
        else:
            g = stats.gain_by_installation(store, region=spec.region, year=hy, metric=m,
                                           inst_type=(spec.inst_type or "CORE")).dropna(subset=["gain_pct"])
            if g.empty:
                continue
            meang = float(g["gain_pct"].mean())
            nsig = int(((g["gain_pct"] > 0) & g["significant"]).sum())
            N = len(g)
            imort = float(g["improved_mortality"].mean())
            wmort = float(g["woods_mortality"].mean())
        kpis.append((f"Gain · {ms}", f"{meang:+.1f}%", f"{nsig}/{N} sites sig."))
        rows.append({"Metric": ms, "Mean gain %": round(meang, 1), "Sites sig.+": f"{nsig}/{N}",
                     "Improved mort.%": round(imort, 1), "Woods mort.%": round(wmort, 1)})
    if not rows:
        return None
    pm = spec.metrics[0]
    sl = store.seedlots(region=spec.region, year=hy, metric=pm, source=config.SOURCE_IMPROVED)
    if insts:
        sl = sl[sl["Installation"].isin(insts)]
    rec = (sl.groupby("Seedlot").agg(mean=("Average", "mean"), mort=("Mortality %", "mean"))
           .reset_index().sort_values("mean", ascending=False).head(5).round(2))
    avg_gain = sum(r["Mean gain %"] for r in rows) / len(rows)
    sig_num = sum(int(r["Sites sig.+"].split("/")[0]) for r in rows)
    sig_den = max(1, sum(int(r["Sites sig.+"].split("/")[1]) for r in rows))
    cost = rows[0]["Improved mort.%"] - rows[0]["Woods mort.%"]
    verdict = "**Deploy**" if (avg_gain > 0 and sig_num / sig_den >= 0.4) else "**Marginal — hold / test further**"
    note = (f"{verdict}. Mean realized gain {avg_gain:+.1f}% across metrics in {hy}; statistically "
            f"significant and positive in {sig_num}/{sig_den} site×metric tests; survival cost "
            f"~{cost:+.1f} points (Improved vs Woods Run). Weigh growth gain against survival before "
            "operational deployment.")
    blocks = [Block("kpis", kpis),
              Block("table", pd.DataFrame(rows), f"Deployment summary — {hy}"),
              Block("note", note)]
    if not rec.empty:
        rec.columns = ["Seedlot", f"Mean {config.METRICS[pm]['short']}", "Mort.%"]
        blocks.append(Block("table", rec,
                      f"Recommended Improved seedlots — {config.METRICS[pm]['short']} · {hy}"))
    return Section("Deployment decision summary", level=2, blocks=blocks)


def _stability_section(spec, store):
    """Seedlot stability / G×E: how consistently each seedlot ranks across sites.
    CV = spread across sites (low = stable); Kendall's W = overall concordance."""
    source = spec.source or config.SOURCE_IMPROVED
    pm = spec.metrics[0]; hy = spec.years[-1]
    sub = store.seedlot_table
    sub = sub[(sub["Source"] == source) & (sub["Metric"] == pm) & (sub["Year"] == hy)]
    if spec.region:
        sub = sub[sub["Region"] == spec.region]
    if sub.empty:
        return None
    piv = sub.pivot_table("Average", "Seedlot", "Installation")
    piv = piv.dropna(thresh=3, axis=0)                 # seedlots present at >=3 sites
    piv = piv.loc[:, piv.notna().sum() >= 3]           # sites with >=3 such seedlots
    if piv.shape[0] < 3 or piv.shape[1] < 2:
        return None
    ranks = piv.rank(ascending=False)
    mshort = config.METRICS[pm]["short"]
    rows = []
    for sl_ in piv.index:
        vals = piv.loc[sl_].dropna()
        mean = float(vals.mean())
        cv = float(vals.std() / mean * 100) if mean else float("nan")
        rows.append({"Seedlot": str(sl_), f"Mean {mshort}": round(mean, 2), "CV %": round(cv, 1),
                     "Mean rank": round(float(ranks.loc[sl_].dropna().mean()), 1), "Sites": int(vals.size)})
    df = pd.DataFrame(rows)
    med_mean = df[f"Mean {mshort}"].median(); med_cv = df["CV %"].median()

    def _flag(r):
        hi = r[f"Mean {mshort}"] >= med_mean
        stable = r["CV %"] <= med_cv
        return ("safe bet" if hi and stable else "site-specific star" if hi else
                "consistently low" if stable else "weak")
    df["Profile"] = df.apply(_flag, axis=1)
    df = df.sort_values(f"Mean {mshort}", ascending=False)
    R = ranks.dropna()
    blocks = []
    if R.shape[0] >= 3 and R.shape[1] >= 2:
        n, k = R.shape
        Rsum = R.sum(axis=1)
        S = float(((Rsum - Rsum.mean()) ** 2).sum())
        W = 12 * S / (k ** 2 * (n ** 3 - n)) if (n ** 3 - n) else None
        if W is not None:
            blocks.append(Block("note",
                f"Across-site rank concordance (Kendall's W) = **{W:.2f}** "
                "(1 = identical ranking at every site; near 0 = strong G×E, winners are "
                f"site-specific) — {source} seedlots, {mshort}, {hy}."))
    blocks.append(Block("table", df, f"Seedlot stability across sites — {source} · {mshort} · {hy}"))
    fig = go.Figure(go.Scatter(
        x=df["CV %"], y=df[f"Mean {mshort}"], mode="markers+text", text=df["Seedlot"],
        textposition="top center", textfont=dict(size=8),
        marker=dict(size=10, line=dict(width=1, color="white"),
                    color=Color.IMPROVED if source == config.SOURCE_IMPROVED else Color.WOODS)))
    fig.add_vline(x=med_cv, line_color=Color.MUTED, line_dash="dot")
    fig.add_hline(y=med_mean, line_color=Color.MUTED, line_dash="dot")
    fig.update_xaxes(title="Instability — CV of mean across sites (%)")
    fig.update_yaxes(title=config.METRICS[pm]["axis"])
    blocks.append(Block("figure", _theme(fig, 380),
                  "Stability map — upper-left quadrant = high & stable ('safe bet')"))
    return Section("Seedlot stability / G×E", level=2, blocks=blocks)


def _damage_section(spec, store):
    """Top damage / mortality agents by source — planting-risk view."""
    t = store.trees(region=spec.region, year=spec.years[-1], metric=spec.metrics[0],
                    inst_type=spec.inst_type)
    if spec.installations:
        t = t[t["Installation"].isin(spec.installations)]
    if t.empty or int(t["HasDefect"].sum()) == 0:
        return None
    rows = []
    for src in (config.SOURCE_WOODS, config.SOURCE_IMPROVED):
        d = t[t["Source"] == src]; n = len(d)
        if not n:
            continue
        for agent, c in d.loc[d["HasDefect"], "Defect"].astype(str).value_counts().head(8).items():
            rows.append({"Damage agent": agent, "Source": src, "pct": round(100 * c / n, 1)})
    if not rows:
        return None
    wide = (pd.DataFrame(rows).pivot_table(index="Damage agent", columns="Source",
            values="pct", fill_value=0).reset_index())
    num = wide.select_dtypes("number")
    wide["_t"] = num.sum(axis=1)
    wide = wide.sort_values("_t", ascending=False).drop(columns="_t").round(1)
    return Section("Damage & risk", level=2, blocks=[Block("table", wide,
                  f"Top damage agents (% of trees) — {spec.years[-1]}")])


def _evidence_sections(spec, store):
    """Computed charts & tables relevant to the request (no model involved)."""
    secs = []
    # Transparent resolution note: typo-corrected or not-found seedlots.
    if spec.seedlot_corrections or spec.seedlots_not_found:
        bits = []
        for typed, used in spec.seedlot_corrections.items():
            bits.append(f"No seedlot **{typed}** exists; showing the closest match **{used}**.")
        if spec.seedlots_not_found:
            avail = ", ".join((sorted(set(store.df[store.df['Installation'].isin(spec.installations)]
                              ['Seedlot'].dropna().astype(str))) if spec.installations
                              else list(store.seedlots_all()))[:24])
            bits.append("Not found: **" + ", ".join(spec.seedlots_not_found) +
                        f"**. Available seedlots include: {avail}.")
        secs.append(Section("", level=2, blocks=[Block("note", "  \n".join(bits))]))
    # General comparison (seedlot / installation / site-type): focused side-by-side,
    # not two full reports. Return early so it stays bounded and on-point.
    if spec.compare_axis:
        secs += _comparison_section(spec, store)
        return secs
    # Manager bottom line up front for deployment-oriented reports.
    if spec.kind in ("installation", "overall", "year"):
        try:
            ds = _deployment_section(spec, store)
            if ds:
                secs.append(ds)
        except Exception:
            pass
    # Full installation evidence only when the request is primarily about a site;
    # for a seedlot report a named installation is just a scope filter.
    if spec.installations and spec.kind == "installation":
        for inst in spec.installations:
            region = _region_of(store, inst)
            g = _gain_rows_for_installation(store, inst, region, spec.years, spec.metrics)
            blocks = []
            if not g.empty:
                blocks.append(Block("table", g[["Year", "Metric", "Woods Run", "Improved",
                              "Gain %", "Sig.", "p", "Imp. mort.%"]].round(2),
                              "Realized gain by year & metric"))
                blocks.append(Block("figure", _fig_gain_trend(g), "Realized gain across years"))
            y0 = spec.years[0] if spec.years else None
            # Cover EVERY in-scope metric (all three when the user named none).
            itab = store.installation_table[store.installation_table["Installation"] == inst]
            for metric in spec.metrics:
                short = config.METRICS[metric]["short"]
                # Growth trajectory across years — Improved vs Woods Run lines
                gs = _source_growth_series(itab, metric, spec.years)
                if gs and any(len(s["x"]) for s in gs):
                    blocks.append(Block("figure",
                                  _fig_traj(gs, config.METRICS[metric]["axis"]),
                                  f"Growth over years — {short} (Improved vs Woods Run)"))
                # Per-plot mean table (spatial layout: plots 1-3 Woods, 4-6 Improved)
                pdet = _plot_detail(store, inst, spec.years, metric)
                if pdet:
                    prows = []
                    for y, rec in pdet.items():
                        r = {"Year": y}; r.update(rec); prows.append(r)
                    blocks.append(Block("table", pd.DataFrame(prows),
                                  f"Per-plot mean {short} (W = Woods plots 1-3, I = Improved plots 4-6)"))
                # Per-seedlot means, each in-scope year
                for y in spec.years:
                    sl = store.seedlots(region=region, installation=inst, year=y, metric=metric)
                    if sl.empty:
                        continue
                    t = sl[["Source", "Seedlot", "Average", "Standard error", "Mortality %"]].copy()
                    t.columns = ["Source", "Seedlot", f"Mean ({config.METRICS[metric]['unit']})",
                                 "Std err", "Mort. %"]
                    blocks.append(Block("table", t.sort_values(["Source", "Seedlot"]).round(2),
                                  f"Per-seedlot means \u2014 {short} \u00b7 {y}"))
                # Field-map heatmaps for the first in-scope year, this metric
                if y0 is not None:
                    plots_here = (store.trees(installation=inst, year=y0, metric=metric)["PLOT"]
                                  .dropna().unique())
                    for p in sorted(int(x) for x in plots_here):
                        tp = store.trees(installation=inst, year=y0, metric=metric, plot=p)
                        if tp.empty or tp["Value"].notna().sum() == 0:
                            continue
                        src = config.PLOT_SOURCE_MAP.get(p, "?")
                        s_lbl = "Woods Run" if src == config.SOURCE_WOODS else (
                            "Improved" if src == config.SOURCE_IMPROVED else src)
                        blocks.append(Block("figure", F.heatmap(tp, height=240),
                                      f"Field map \u2014 Plot {p} ({s_lbl}) \u00b7 {short} \u00b7 {y0}"))
            secs.append(Section(f"Evidence \u2014 {inst}", level=2, blocks=blocks))
    if spec.seedlots:
        st = store.seedlot_table
        if spec.region:
            st = st[st["Region"] == spec.region]
        _inst = set(spec.installations) if spec.installations else None
        for sl in spec.seedlots:
            sub = st[st["Seedlot"].astype(str) == sl]
            if _inst:
                sub = sub[sub["Installation"].isin(_inst)]
            source = sub["Source"].iloc[0] if not sub.empty else "?"
            blocks = []
            recs = []
            for y in spec.years:
                for m in spec.metrics:
                    this = sub[(sub["Year"] == y) & (sub["Metric"] == m)]
                    grp = st[(st["Source"] == source) & (st["Year"] == y) & (st["Metric"] == m)]
                    if this.empty:
                        continue
                    recs.append({"Year": y, "Metric": config.METRICS[m]["short"],
                                 "Seedlot mean": round(float(this["Average"].mean()), 2),
                                 f"{source} avg": round(float(grp["Average"].mean()), 2),
                                 "Mort. %": round(float(this["Mortality %"].mean()), 1)})
            if recs:
                blocks.append(Block("table", pd.DataFrame(recs), "Seedlot mean vs source-group average"))
            for metric in spec.metrics:
                short = config.METRICS[metric]["short"]
                # Trajectory: this seedlot vs its source-group average, across years
                s_this = sub[sub["Metric"] == metric].groupby("Year")["Average"].mean().reindex(spec.years)
                s_grp = (st[(st["Source"] == source) & (st["Metric"] == metric)]
                         .groupby("Year")["Average"].mean().reindex(spec.years))
                tser = []
                if s_this.notna().any():
                    tser.append({"name": f"Seedlot {sl}", "x": list(spec.years),
                                 "y": [None if pd.isna(v) else round(float(v), 2) for v in s_this.values],
                                 "color": Color.IMPROVED if source == config.SOURCE_IMPROVED else Color.WOODS})
                if s_grp.notna().any():
                    tser.append({"name": f"{source} average", "x": list(spec.years),
                                 "y": [None if pd.isna(v) else round(float(v), 2) for v in s_grp.values],
                                 "color": Color.NEUTRAL, "dash": "dash"})
                if tser:
                    blocks.append(Block("figure", _fig_traj(tser, config.METRICS[metric]["axis"]),
                                  f"Growth over years \u2014 {short} (seedlot {sl} vs {source} average)"))
                for y in spec.years:
                    byinst = sub[(sub["Year"] == y) & (sub["Metric"] == metric)]
                    if not byinst.empty:
                        blocks.append(Block("figure", _fig_seedlot_by_installation(byinst, sl, metric),
                                      f"Mean by installation \u2014 {short} \u00b7 {y}"))
            secs.append(Section(f"Evidence \u2014 {sl} ({source})", level=2, blocks=blocks))
    if spec.kind == "seedlot_group" and spec.source:
        st = store.seedlot_table[store.seedlot_table["Source"] == spec.source]
        if spec.region:
            st = st[st["Region"] == spec.region]
        rows = []
        for sl in sorted(st["Seedlot"].astype(str).unique()):
            sub = st[st["Seedlot"].astype(str) == sl]
            rec = {"Seedlot": sl}
            for m in spec.metrics:
                d = sub[sub["Metric"] == m]
                rec[config.METRICS[m]["short"]] = round(float(d["Average"].mean()), 2) if not d.empty else None
            rec["Mort. %"] = round(float(sub["Mortality %"].mean()), 1)
            rec["Installs"] = int(sub["Installation"].nunique())
            rows.append(rec)
        rank = pd.DataFrame(rows)
        pm = config.METRICS[spec.metrics[0]]["short"]
        if pm in rank.columns:
            rank = rank.sort_values(pm, ascending=False, na_position="last")
        blk = [Block("table", rank, f"All {spec.source} seedlots ranked by mean {pm}")]
        col = Color.IMPROVED if spec.source == config.SOURCE_IMPROVED else Color.WOODS
        # One ranking bar chart per in-scope metric (all three when none was named).
        for m in spec.metrics:
            ms = config.METRICS[m]["short"]
            if ms not in rank.columns:
                continue
            d = rank.dropna(subset=[ms]).sort_values(ms, ascending=False)
            if d.empty:
                continue
            fig = go.Figure(go.Bar(x=d["Seedlot"].astype(str), y=d[ms], marker_color=col,
                            text=[f"{v:.1f}" for v in d[ms]], textposition="outside"))
            fig.update_xaxes(tickangle=270, type="category")
            fig.update_yaxes(title=config.METRICS[m]["axis"])
            blk.append(Block("figure", _theme(fig, 420), f"{spec.source} seedlots by mean {ms}"))
        secs.append(Section(f"Evidence — {spec.source} seedlot ranking", level=2, blocks=blk))
    if spec.kind == "region_compare" and spec.regions:
        rows = []
        for y in spec.years:
            for m in spec.metrics:
                row = {"Year": y, "Metric": config.METRICS[m]["short"]}
                for R in spec.regions:
                    g = stats.gain_by_installation(store, region=R, year=y, metric=m, inst_type="CORE")
                    v = g["gain_pct"].dropna() if not g.empty else None
                    row[f"{R} gain %"] = round(float(v.mean()), 1) if (v is not None and not v.empty) else None
                    row[f"{R} mort.%"] = round(float(g["improved_mortality"].mean()), 1) if not g.empty else None
                rows.append(row)
        blk = [Block("table", pd.DataFrame(rows), "Mean realized gain & improved-mortality by region")]
        palette = {"INW": Color.NAVY, "K-S": Color.GOLD}
        # One grouped bar chart per in-scope metric (all three when none was named).
        for m in spec.metrics:
            ms = config.METRICS[m]["short"]
            fig = go.Figure()
            any_data = False
            for R in spec.regions:
                ys, gs = [], []
                for y in spec.years:
                    g = stats.gain_by_installation(store, region=R, year=y, metric=m, inst_type="CORE")
                    if g.empty:
                        continue
                    vv = g["gain_pct"].dropna()
                    ys.append(y); gs.append(round(float(vv.mean()), 1) if not vv.empty else 0.0)
                if ys:
                    any_data = True
                fig.add_trace(go.Bar(name=R, x=ys, y=gs, marker_color=palette.get(R),
                              text=[f"{v:+.1f}%" for v in gs], textposition="outside"))
            if not any_data:
                continue
            fig.update_layout(barmode="group")
            fig.add_hline(y=0, line_color=Color.MUTED)
            fig.update_yaxes(title=f"Mean realized gain in {ms} (%)", ticksuffix="%")
            blk.append(Block("figure", _theme(fig, 380), f"Mean realized gain by region — {ms}"))
        secs.append(Section("Evidence — " + " vs ".join(spec.regions), level=2, blocks=blk))
    if (not spec.installations and not spec.seedlots
            and spec.kind not in ("seedlot_group", "region_compare")):
        itype = spec.inst_type or "CORE"
        for y in spec.years:
            for m in spec.metrics:
                g = stats.gain_by_installation(store, region=spec.region, year=y, metric=m, inst_type=itype)
                if g.empty:
                    continue
                disp = g[["installation", "region", "woods_mean", "improved_mean",
                          "gain_pct", "stars", "improved_mortality"]].copy()
                disp.columns = ["Installation", "Region", "Woods", "Improved", "Gain %", "Sig.", "Mort.%"]
                ev_blocks = [Block("figure", F.gain_chart(g, metric=m, height=380),
                                   "Realized gain by site"),
                             Block("table", disp.round(2), "Site-by-site gain")]
                # Gain vs site productivity \u2014 does Improved help more on poor or rich sites?
                rel = stats.productivity_relationship(g)
                if rel and rel.get("n", 0) >= 3:
                    ev_blocks.append(Block("figure", _fig_productivity_scatter(g, m, rel),
                                     "Realized gain vs site productivity"))
                secs.append(Section(f"Evidence \u2014 {y} \u00b7 {config.METRICS[m]['short']}", level=2,
                            blocks=ev_blocks))
    # Practitioner add-ons (best-effort; never break the report).
    try:
        if spec.kind in ("seedlot_group", "region_compare", "overall"):
            sb = _stability_section(spec, store)
            if sb:
                secs.append(sb)
        if spec.kind in ("installation", "overall", "year"):
            dm = _damage_section(spec, store)
            if dm:
                secs.append(dm)
    except Exception:
        pass
    return secs


def build_report(spec: ReportSpec, store, client=None) -> Report:
    """Request-driven report. Pipeline: compute the data bundle and the evidence
    (charts/tables), then DRAFT -> expert CRITIQUE -> REVISE the narrative grounded
    strictly in the computed numbers and referencing the evidence by name.
    Every stage falls back safely so a report is always produced."""
    try:
        data = _scope_summary(spec, store)
    except Exception:
        data = {"report_type": spec.kind, "trial_context": stats.trial_overview(store)}
    try:
        evidence = _evidence_sections(spec, store)
    except Exception:
        evidence = []
    narrative = _compose_report(client, spec, data, evidence)
    rep = Report("Realized Genetic Gain Trials", _subtitle(spec))
    rep.sections.append(Section("", level=2, blocks=[Block("narrative", narrative)]))
    rep.sections += evidence
    return rep
