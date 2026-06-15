# -*- coding: utf-8 -*-
"""
Data access layer.

A single :class:`DataStore` loads the CSV exactly once, validates and cleans it,
and pre-computes every derived frame the dashboard needs (plot pivots, seedlot
and installation summaries, mortality).  Callbacks then slice these cached frames
instead of re-aggregating 86k rows on every dropdown change.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger("rgt.data")

REQUIRED_COLUMNS = [
    "Region", "Installation", "Source", "Seedlot", "PLOT", "TREE",
    "Replication", "Year", "Value", "Metric", "Management", "Defect",
]


# --------------------------------------------------------------------------- #
# Loading + cleaning
# --------------------------------------------------------------------------- #
def load_raw(path=None) -> pd.DataFrame:
    """Read the CSV and apply defensive cleaning. Raises a clear error if the
    file is missing or structurally wrong."""
    path = path or config.DATA_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"RGT data file not found at {path}. Set RGT_DATA_FILE or place the "
            f"CSV under data/."
        )
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Data file {path} is missing required columns: {missing}")

    # --- dtype coercion -----------------------------------------------------
    df["Seedlot"] = df["Seedlot"].astype("string")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df["PLOT"] = pd.to_numeric(df["PLOT"], errors="coerce").astype("Int64")
    for c in ("Region", "Installation", "Source", "Year", "Metric"):
        df[c] = df[c].astype("string").str.strip()

    # --- derived flags ------------------------------------------------------
    df["InstallationType"] = np.where(
        df["Installation"].isin(config.TRANSFER_INSTALLATIONS), "TRANSFER", "CORE"
    )
    df["IsDead"] = df["Management"].isin(config.DEAD_CODES)
    df["HasDefect"] = df["Defect"].notna() & (df["Defect"].astype("string").str.len() > 0)

    _validate_design(df)
    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def _validate_design(df: pd.DataFrame) -> None:
    """Warn (don't crash) if the plot->source layout differs from expectations."""
    observed = df.dropna(subset=["PLOT"]).groupby("PLOT")["Source"].agg(lambda s: set(s.dropna()))
    for plot, expected in config.PLOT_SOURCE_MAP.items():
        if plot in observed.index and observed.loc[plot] - {expected}:
            logger.warning(
                "PLOT %s expected source %r but found %s", plot, expected, observed.loc[plot]
            )


# --------------------------------------------------------------------------- #
# Derived-frame helpers
# --------------------------------------------------------------------------- #
_PLOT_KEYS = ["Year", "Region", "Installation", "Source", "Seedlot", "Metric"]


def _plot_pivot(sub: pd.DataFrame) -> pd.DataFrame:
    """Seedlot x plot mean table for a single source, with row summaries used by
    the mean tables and the avg/max/min error-bar chart."""
    if sub.empty:
        return pd.DataFrame()
    cell = (sub.groupby(_PLOT_KEYS + ["PLOT"], observed=True)["Value"]
               .mean().reset_index())
    wide = cell.pivot_table("Value", _PLOT_KEYS, "PLOT")
    wide.columns = [f"Plot {int(c)} Avg" for c in wide.columns]
    wide = wide.reset_index()
    plot_cols = [c for c in wide.columns if c.startswith("Plot ")]
    if plot_cols:
        vals = wide[plot_cols]
        wide["Overall Avg"] = vals.mean(axis=1)
        wide["min"] = vals.min(axis=1)
        wide["max"] = vals.max(axis=1)
        wide["array"] = wide["max"] - wide["Overall Avg"]        # upper error bar
        wide["arrayminus"] = wide["Overall Avg"] - wide["min"]   # lower error bar
        wide["STDEV"] = vals.std(axis=1)
        wide["n_plots"] = vals.notna().sum(axis=1)
    return wide.round(3)


@dataclass
class DataStore:
    """Holds the raw frame plus every cached derivative."""

    df: pd.DataFrame = field(default_factory=load_raw)

    plot_table: pd.DataFrame = field(init=False)
    seedlot_table: pd.DataFrame = field(init=False)
    installation_table: pd.DataFrame = field(init=False)
    mortality_table: pd.DataFrame = field(init=False)
    inst_type_map: pd.DataFrame = field(init=False)

    def __post_init__(self):
        df = self.df
        # Growth analyses use the surviving ORIGINAL cohort only: trees coded
        # dead or replaced (IsDead) are excluded from every growth mean / SE /
        # gain calc, because interplanted replacements are a younger cohort and
        # would confound realized genetic gain with planting age. Mortality
        # (below) still counts them. See README "Statistics methodology".
        growth = df[~df["IsDead"]]
        self.inst_type_map = (
            df[["Region", "Installation", "InstallationType"]].drop_duplicates()
        )

        # --- dropdown option lists (computed once) --------------------------
        self._regions = tuple(sorted(df["Region"].dropna().unique()))
        self._years = tuple(sorted(df["Year"].dropna().unique()))
        present = set(df["Metric"].dropna().unique())
        ordered = [m for m in config.METRICS if m in present]
        self._metrics = tuple(ordered + sorted(present - set(ordered)))
        self._installations = {
            r: tuple(sorted(df.loc[df["Region"] == r, "Installation"].dropna().unique()))
            for r in self._regions
        }

        # --- plot-level pivots (per source, then stacked) -------------------
        # growth-only: dead/replacement trees excluded (see note above)
        pivots = [_plot_pivot(growth[growth["Source"] == s]) for s in
                  (config.SOURCE_WOODS, config.SOURCE_IMPROVED)]
        self.plot_table = (
            pd.concat([p for p in pivots if not p.empty], ignore_index=True)
              .merge(self.inst_type_map, on=["Region", "Installation"], how="left")
        )

        # --- mortality (seedlot level) --------------------------------------
        mort = (df.groupby(["Year", "Region", "Installation", "Source", "Seedlot", "Metric"],
                           observed=True)
                  .agg(total_obs=("IsDead", "size"), dead_obs=("IsDead", "sum"))
                  .reset_index())
        mort["Mortality %"] = (100 * mort["dead_obs"] / mort["total_obs"]).round(1)
        self.mortality_table = mort

        # --- seedlot-level mean / sem + mortality ---------------------------
        # Average/SE/n computed on the growth (living) cohort; Mortality % is
        # merged from the full-frame mort table below.
        seedlot = (growth.groupby(["Year", "Region", "Installation", "Source", "Seedlot", "Metric"],
                              observed=True)
                     .agg(Average=("Value", "mean"),
                          **{"Standard error": ("Value", "sem")},
                          n=("Value", "count"))
                     .reset_index()
                     .round(3))
        seedlot = seedlot.merge(self.inst_type_map, on=["Region", "Installation"], how="left")
        seedlot = seedlot.merge(
            mort[["Year", "Region", "Installation", "Source", "Seedlot", "Metric", "Mortality %"]],
            on=["Year", "Region", "Installation", "Source", "Seedlot", "Metric"], how="left",
        )
        self.seedlot_table = seedlot

        # --- installation-level mean / sem ----------------------------------
        # growth-only cohort (dead/replacement excluded)
        inst = (growth.groupby(["Year", "Region", "Installation", "Source", "Metric"],
                           observed=True)
                  .agg(Average=("Value", "mean"),
                       se=("Value", "sem"),
                       n=("Value", "count"))
                  .reset_index()
                  .merge(self.inst_type_map, on=["Region", "Installation"], how="left")
                  .round(3))
        self.installation_table = inst

    # ------------------------------------------------------------------ #
    # Dropdown option helpers
    # ------------------------------------------------------------------ #
    def regions(self) -> tuple:
        return self._regions

    def years(self) -> tuple:
        return self._years

    def metrics(self) -> tuple:
        return self._metrics

    def installations(self, region: str) -> tuple:
        return self._installations.get(region, ())

    def installations_all(self) -> tuple:
        return tuple(sorted({i for v in self._installations.values() for i in v}))

    def seedlots_all(self) -> tuple:
        return tuple(sorted(self.df["Seedlot"].dropna().astype(str).unique()))

    # ------------------------------------------------------------------ #
    # Slicers used by callbacks
    # ------------------------------------------------------------------ #
    def trees(self, *, region=None, installation=None, year=None, metric=None,
              source=None, plot=None, inst_type=None, living_only=False) -> pd.DataFrame:
        """Filtered view of the raw tree-level frame.

        living_only=True drops trees coded dead/replacement (IsDead) -- use it
        for growth statistics so realized gain reflects the surviving original
        cohort. Leave False for the field-map heatmap and mortality, which need
        every planted position.
        """
        d = self.df
        mask = pd.Series(True, index=d.index)
        if region:        mask &= d["Region"] == region
        if installation:  mask &= d["Installation"] == installation
        if year:          mask &= d["Year"] == year
        if metric:        mask &= d["Metric"] == metric
        if source:        mask &= d["Source"] == source
        if plot is not None: mask &= d["PLOT"] == plot
        if inst_type and inst_type != "ALL":
            mask &= d["InstallationType"] == inst_type
        if living_only:
            mask &= ~d["IsDead"]
        return d[mask]

    @staticmethod
    def _slice(frame: pd.DataFrame, *, region=None, installation=None, year=None,
               metric=None, source=None, inst_type=None) -> pd.DataFrame:
        m = pd.Series(True, index=frame.index)
        if region and "Region" in frame:             m &= frame["Region"] == region
        if installation and "Installation" in frame: m &= frame["Installation"] == installation
        if year and "Year" in frame:                 m &= frame["Year"] == year
        if metric and "Metric" in frame:             m &= frame["Metric"] == metric
        if source and "Source" in frame:             m &= frame["Source"] == source
        if inst_type and inst_type != "ALL" and "InstallationType" in frame:
            m &= frame["InstallationType"] == inst_type
        return frame[m].reset_index(drop=True)

    def plots(self, **kw) -> pd.DataFrame:
        return self._slice(self.plot_table, **kw)

    def seedlots(self, **kw) -> pd.DataFrame:
        return self._slice(self.seedlot_table, **kw)

    def installations_summary(self, **kw) -> pd.DataFrame:
        return self._slice(self.installation_table, **kw)


STORE = None


def get_store() -> "DataStore":
    global STORE
    if STORE is None:
        STORE = DataStore()
    return STORE
