# -*- coding: utf-8 -*-
"""
Applied forest-biometrics statistics for the realized gain trials.

The headline quantity is *realized genetic gain*: how much more growth the
Improved Douglas-fir seedlots show over the local Woods Run (unimproved) checks
at a site.  We treat each **seedlot (genetic entry) mean** as the unit of
replication for the population-level Improved-vs-Woods-Run contrast, which is the
defensible choice here because source is confounded with physical plot (plots
1-3 vs 4-6) -- so the plots themselves are pseudo-replicates of source, whereas
the seedlots are genuine independent genetic entries drawn from each population.

Everything degrades gracefully on small / empty samples and never raises inside
a callback.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats

from . import config


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def mean_ci(values, conf: float = 0.95) -> dict:
    """Mean with a t-based confidence interval. NaNs are dropped."""
    a = pd.Series(values, dtype="float64").dropna().to_numpy()
    n = a.size
    if n == 0:
        return dict(mean=np.nan, sem=np.nan, lo=np.nan, hi=np.nan, n=0, sd=np.nan)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if n > 1 else 0.0
    sem = sd / math.sqrt(n) if n > 1 else 0.0
    if n > 1 and sem > 0:
        h = stats.t.ppf(0.5 + conf / 2, n - 1) * sem
    else:
        h = 0.0
    return dict(mean=mean, sem=sem, lo=mean - h, hi=mean + h, n=n, sd=sd)


def hedges_g(a, b) -> float:
    """Bias-corrected standardized mean difference (a - b)."""
    a = pd.Series(a, dtype="float64").dropna().to_numpy()
    b = pd.Series(b, dtype="float64").dropna().to_numpy()
    na, nb = a.size, b.size
    if na < 2 or nb < 2:
        return np.nan
    sp2 = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if sp2 <= 0:
        return np.nan
    d = (a.mean() - b.mean()) / math.sqrt(sp2)
    j = 1 - 3 / (4 * (na + nb) - 9)
    return float(d * j)


def p_to_stars(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


def benjamini_hochberg(pvals) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted p-values (q-values), aligned to the input.

    NaNs are preserved and excluded from the ranking. Controls the expected
    false-discovery rate across the family of tests shown together (the gain
    table runs one Welch test per site, so the stars are a multiple-comparison
    family). Standard step-up procedure with monotonicity enforced.
    """
    p = np.asarray([np.nan if v is None else v for v in pvals], dtype="float64")
    q = np.full(p.shape, np.nan)
    idx = np.where(~np.isnan(p))[0]
    m = idx.size
    if m == 0:
        return q
    order = idx[np.argsort(p[idx])]                       # positions, ascending p
    adj = p[order] * m / np.arange(1, m + 1)              # p * m / rank
    adj = np.minimum.accumulate(adj[::-1])[::-1]          # step-up monotonicity
    q[order] = np.clip(adj, 0, 1)
    return q


def apply_fdr(gdf: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of a gain table with significance re-derived from
    Benjamini-Hochberg FDR-adjusted p-values (q). The raw p is preserved as
    'p_raw'; 'p_value' becomes the q-value so every downstream visual (stars,
    gold rings, the significant flag, the p column) reflects the
    multiplicity-controlled call. The 95% CI columns are left untouched."""
    if gdf is None or gdf.empty or "p_value" not in gdf.columns:
        return gdf
    out = gdf.copy()
    out["p_raw"] = out["p_value"]
    q = benjamini_hochberg(out["p_value"].tolist())
    out["p_value"] = q
    out["stars"] = [p_to_stars(v) for v in q]
    out["significant"] = [bool(pd.notna(v) and v < 0.05) for v in q]
    return out


# --------------------------------------------------------------------------- #
# Genetic-gain contrast at one installation
# --------------------------------------------------------------------------- #
@dataclass
class GainResult:
    region: str
    installation: str
    year: str
    metric: str
    inst_type: str
    woods_mean: float
    improved_mean: float
    gain_abs: float
    gain_pct: float
    diff_lo: float
    diff_hi: float
    p_value: float
    hedges_g: float
    n_woods_entries: int
    n_improved_entries: int
    n_woods_trees: int
    n_improved_trees: int
    woods_mortality: float
    improved_mortality: float

    @property
    def stars(self) -> str:
        return p_to_stars(self.p_value)

    @property
    def significant(self) -> bool:
        return isinstance(self.p_value, float) and self.p_value < 0.05

    def as_dict(self) -> dict:
        return asdict(self)


def _entry_means(trees: pd.DataFrame, source: str) -> np.ndarray:
    sub = trees[trees["Source"] == source]
    if sub.empty:
        return np.array([])
    return sub.groupby("Seedlot", observed=True)["Value"].mean().dropna().to_numpy()


def compare_sources(store, *, region, installation, year, metric):
    """Realized-gain contrast (Improved vs Woods Run) at a single installation.

    Growth means and tree counts use the surviving original cohort
    (living_only) so gain isn't biased by younger replacement trees; mortality
    is read separately from the full-frame seedlot table below.
    """
    trees = store.trees(region=region, installation=installation, year=year,
                        metric=metric, living_only=True)
    if trees.empty:
        return None

    woods = _entry_means(trees, config.SOURCE_WOODS)
    imp = _entry_means(trees, config.SOURCE_IMPROVED)
    if woods.size == 0 or imp.size == 0:
        return None

    wmean, imean = float(woods.mean()), float(imp.mean())
    gain_abs = imean - wmean
    gain_pct = 100 * gain_abs / wmean if wmean else np.nan

    if woods.size >= 2 and imp.size >= 2:
        t = stats.ttest_ind(imp, woods, equal_var=False)
        p = float(t.pvalue)
        vi, vw = imp.var(ddof=1), woods.var(ddof=1)
        se_diff = math.sqrt(vi / imp.size + vw / woods.size)
        num = (vi / imp.size + vw / woods.size) ** 2
        den = ((vi / imp.size) ** 2 / (imp.size - 1) +
               (vw / woods.size) ** 2 / (woods.size - 1))
        df = num / den if den else (imp.size + woods.size - 2)
        tcrit = stats.t.ppf(0.975, df) if df > 0 else np.nan
        lo, hi = gain_abs - tcrit * se_diff, gain_abs + tcrit * se_diff
    else:
        p, lo, hi = np.nan, np.nan, np.nan

    mort = store.seedlots(region=region, installation=installation, year=year, metric=metric)
    wmort = mort.loc[mort["Source"] == config.SOURCE_WOODS, "Mortality %"].mean()
    imort = mort.loc[mort["Source"] == config.SOURCE_IMPROVED, "Mortality %"].mean()
    itype = trees["InstallationType"].iloc[0]

    return GainResult(
        region=region, installation=installation, year=year, metric=metric, inst_type=itype,
        woods_mean=round(wmean, 3), improved_mean=round(imean, 3),
        gain_abs=round(gain_abs, 3), gain_pct=round(gain_pct, 1) if pd.notna(gain_pct) else np.nan,
        diff_lo=round(lo, 3) if pd.notna(lo) else np.nan,
        diff_hi=round(hi, 3) if pd.notna(hi) else np.nan,
        p_value=p, hedges_g=round(hedges_g(imp, woods), 3) if imp.size > 1 else np.nan,
        n_woods_entries=int(woods.size), n_improved_entries=int(imp.size),
        n_woods_trees=int((trees["Source"] == config.SOURCE_WOODS).sum()),
        n_improved_trees=int((trees["Source"] == config.SOURCE_IMPROVED).sum()),
        woods_mortality=round(float(wmort), 1) if pd.notna(wmort) else np.nan,
        improved_mortality=round(float(imort), 1) if pd.notna(imort) else np.nan,
    )


def gain_by_installation(store, *, region=None, year, metric, inst_type="ALL") -> pd.DataFrame:
    """Genetic-gain table across every installation matching the filters."""
    rows = []
    insts = store.installation_table
    sel = insts[(insts["Year"] == year) & (insts["Metric"] == metric)]
    if region:
        sel = sel[sel["Region"] == region]
    if inst_type and inst_type != "ALL":
        sel = sel[sel["InstallationType"] == inst_type]
    for (reg, inst), _ in sel.groupby(["Region", "Installation"], observed=True):
        res = compare_sources(store, region=reg, installation=inst, year=year, metric=metric)
        if res:
            rows.append(res.as_dict())
    cols = list(GainResult.__dataclass_fields__.keys())
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df["stars"] = df["p_value"].apply(p_to_stars)
        df["significant"] = df["p_value"].apply(lambda p: bool(pd.notna(p) and p < 0.05))
        df = df.sort_values("gain_pct", ascending=False).reset_index(drop=True)
    return df


# Mortality gap (Improved - Woods, percentage points) above which survival is a
# real concern even when growth gain is positive.
DEPLOY_MORT_GAP_WARN = 15.0


def deployment_call(store, *, region, installation) -> dict:
    """Deterministic deploy / caution / hold verdict for ONE installation, using
    the latest measured year of each growth metric plus the survival trade-off.
    Transparent (returns the evidence it used) -- not an LLM guess.

    Logic: for each metric take the most recent year that has a gain estimate.
    - HOLD  if any metric shows a *significant negative* gain and none is
            significantly positive (Improved underperformed the local check).
    - DEPLOY            if >=1 metric is significantly positive, none significantly
            negative, and Improved mortality is not far above the check.
    - DEPLOY WITH CAUTION if growth gains are positive but either not significant
            or paired with markedly higher Improved mortality.
    - HOLD  if gains are mostly non-positive.
    - INSUFFICIENT if there are no gain estimates yet.
    """
    metrics = list(store.metrics())
    years = list(store.years())
    per_metric, mort_gaps = [], []
    for m in metrics:
        latest = None
        for y in reversed(years):                     # most recent measured year
            r = compare_sources(store, region=region, installation=installation, year=y, metric=m)
            if r and pd.notna(r.gain_pct):
                latest = r
                break
        if latest is None:
            continue
        per_metric.append(dict(
            metric=m, short=config.METRICS.get(m, {}).get("short", m), year=latest.year,
            gain_pct=float(latest.gain_pct), significant=bool(latest.significant),
            stars=latest.stars, woods_mort=latest.woods_mortality,
            improved_mort=latest.improved_mortality))
        if pd.notna(latest.improved_mortality) and pd.notna(latest.woods_mortality):
            mort_gaps.append(latest.improved_mortality - latest.woods_mortality)

    n = len(per_metric)
    pos_sig = sum(1 for d in per_metric if d["significant"] and d["gain_pct"] > 0)
    neg_sig = sum(1 for d in per_metric if d["significant"] and d["gain_pct"] < 0)
    pos_any = sum(1 for d in per_metric if d["gain_pct"] > 0)
    mort_gap = (sum(mort_gaps) / len(mort_gaps)) if mort_gaps else None
    severe_mort = mort_gap is not None and mort_gap > DEPLOY_MORT_GAP_WARN

    if n == 0:
        level, verdict = "none", "Insufficient data"
        headline = "No realized-gain estimates at this site yet."
    elif neg_sig > 0 and pos_sig == 0:
        level, verdict = "negative", "Negative"
        headline = "Improved stock significantly underperformed the local Woods Run check."
    elif pos_sig >= 1 and neg_sig == 0 and not severe_mort:
        level, verdict = "strong", "Very positive"
        headline = "Significant positive realized gain with acceptable survival."
    elif pos_sig >= 1 and severe_mort:
        level, verdict = "positive", "Positive"
        headline = (f"Positive growth gain, but Improved mortality runs ~{mort_gap:.0f} pts "
                    "above the check — weigh survival before any operational call.")
    elif pos_any >= max(1, n - 1):
        level, verdict = "positive", "Positive"
        headline = "Gains lean positive but aren't statistically conclusive (treat as provisional)."
    else:
        level, verdict = "neutral", "Neutral"
        headline = "Realized gains are inconclusive at this site."

    return dict(level=level, verdict=verdict, headline=headline, n=n,
                per_metric=per_metric, mort_gap=mort_gap,
                region=region, installation=installation)


def productivity_relationship(gain_df: pd.DataFrame) -> dict:
    """Regression of ABSOLUTE realized gain (Improved - Woods Run, metric units)
    on site productivity (Woods Run mean).

    Deliberately absolute gain, NOT gain %: gain % = (Improved-Woods)/Woods
    carries the Woods Run mean in its denominator, so regressing it on the Woods
    Run mean manufactures a spurious negative slope by construction. Absolute
    gain has no such coupling (under an additive-gain null it is uncorrelated
    with the site mean), so this is the unbiased test of whether gain depends on
    site productivity. The returned keys are unchanged (slope/intercept/r/p/n)
    but are now in metric units per unit of Woods Run mean.
    """
    if gain_df is None or gain_df.empty or gain_df["gain_abs"].notna().sum() < 3:
        return dict(slope=np.nan, intercept=np.nan, r=np.nan, p=np.nan, n=0)
    d = gain_df.dropna(subset=["woods_mean", "gain_abs"])
    if len(d) < 3:
        return dict(slope=np.nan, intercept=np.nan, r=np.nan, p=np.nan, n=len(d))
    lr = stats.linregress(d["woods_mean"], d["gain_abs"])
    return dict(slope=float(lr.slope), intercept=float(lr.intercept),
                r=float(lr.rvalue), p=float(lr.pvalue), n=int(len(d)))


def summarize_for_llm(store, *, region, year, metric, inst_type="ALL") -> dict:
    """Compact, model-friendly snapshot of the current view used to ground the
    report assistant."""
    gdf = gain_by_installation(store, region=region, year=year, metric=metric, inst_type=inst_type)
    rel = productivity_relationship(gdf)
    unit = config.METRICS.get(metric, {}).get("unit", "")
    sites = []
    for _, r in gdf.iterrows():
        sites.append(dict(
            installation=r["installation"], type=r["inst_type"],
            woods_mean=r["woods_mean"], improved_mean=r["improved_mean"],
            gain_pct=r["gain_pct"], p_value=None if pd.isna(r["p_value"]) else round(r["p_value"], 4),
            significant=bool(pd.notna(r["p_value"]) and r["p_value"] < 0.05),
            improved_mortality=r["improved_mortality"], woods_mortality=r["woods_mortality"],
        ))
    valid = gdf["gain_pct"].dropna() if not gdf.empty else pd.Series([], dtype=float)
    return dict(
        region=region or "ALL", year=year, metric=metric, unit=unit, inst_type=inst_type,
        n_installations=int(len(gdf)),
        mean_gain_pct=round(float(valid.mean()), 1) if not valid.empty else None,
        median_gain_pct=round(float(valid.median()), 1) if not valid.empty else None,
        n_significant=int(sum(s["significant"] for s in sites)),
        productivity_relationship=rel,
        sites=sites,
    )


# --------------------------------------------------------------------------- #
# Trial-wide overview (cached) — lets the assistant answer general / overall /
# year-over-year questions, not just the currently filtered view.
# --------------------------------------------------------------------------- #
_OVERVIEW_CACHE: dict = {}


def trial_overview(store) -> dict:
    """Compact aggregate snapshot across all regions / years / metrics, suitable
    for grounding general questions. Computed once, then cached."""
    if "data" in _OVERVIEW_CACHE:
        return _OVERVIEW_CACHE["data"]

    df = store.df
    completeness = (df.dropna(subset=["Value"]).groupby("Year")["Installation"]
                    .nunique().astype(int).to_dict())

    gym: dict = {}
    notable: list = []
    for year in store.years():
        gym[year] = {}
        for metric in store.metrics():
            short = config.METRICS.get(metric, {}).get("short", metric)
            frames = []
            for region in store.regions():
                g = gain_by_installation(store, region=region, year=year,
                                         metric=metric, inst_type="CORE")
                if not g.empty:
                    frames.append(g)
            if not frames:
                continue
            allg = pd.concat(frames, ignore_index=True)
            v = allg["gain_pct"].dropna()
            gym[year][short] = dict(
                mean_gain_pct=round(float(v.mean()), 1) if not v.empty else None,
                median_gain_pct=round(float(v.median()), 1) if not v.empty else None,
                n_sites=int(len(allg)),
                n_sig_positive=int(((allg["significant"]) & (allg["gain_pct"] > 0)).sum()),
                n_sig_negative=int(((allg["significant"]) & (allg["gain_pct"] < 0)).sum()),
            )
            for _, r in allg.iterrows():
                if pd.notna(r["gain_pct"]):
                    notable.append(dict(site=r["installation"], region=r["region"], year=year,
                                        metric=short, gain_pct=r["gain_pct"],
                                        p=None if pd.isna(r["p_value"]) else round(float(r["p_value"]), 4),
                                        significant=bool(r["significant"])))

    nd = pd.DataFrame(notable)
    sig = nd[nd["significant"]] if not nd.empty else nd
    top_pos = (sig.nlargest(6, "gain_pct").to_dict("records") if not sig.empty else [])
    top_neg = (sig.nsmallest(6, "gain_pct").to_dict("records") if not sig.empty else [])

    mort_region: dict = {}
    for region in store.regions():
        ms = (store.mortality_table[store.mortality_table["Region"] == region]
              .groupby("Source")["Mortality %"].mean())
        mort_region[region] = {
            "woods_run": round(float(ms.get(config.SOURCE_WOODS, float("nan"))), 1)
            if pd.notna(ms.get(config.SOURCE_WOODS, float("nan"))) else None,
            "improved": round(float(ms.get(config.SOURCE_IMPROVED, float("nan"))), 1)
            if pd.notna(ms.get(config.SOURCE_IMPROVED, float("nan"))) else None,
        }

    overview = dict(
        what=("Realized Gain Trials comparing genetically Improved vs local Woods Run "
              "(unimproved) Douglas-fir across INW (13 core sites) and K-S (3 sites), over "
              "3 measurement years, on 3 growth metrics (caliper mm, height cm, volume cm³)."),
        installations_measured_by_year=completeness,
        gain_by_year_and_metric_CORE_percent=gym,
        top_significant_positive_gains=top_pos,
        top_significant_negative_gains=top_neg,
        mean_mortality_by_region_percent=mort_region,
        key_notes=("Volume shows the strongest and most frequently significant gains. "
                   "Gain shows no significant dependence on site productivity in any "
                   "year/metric. Improved stock has higher mortality than Woods Run in "
                   "both regions, severe in K-S. Year3 is under-sampled (only a few sites "
                   "measured) so its averages are unreliable and should be caveated."),
    )
    _OVERVIEW_CACHE["data"] = overview
    return overview
