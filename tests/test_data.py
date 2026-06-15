# -*- coding: utf-8 -*-
"""Golden-value tests for the data layer (DataStore loading, cleaning, and the
living-cohort growth rule). These pin the dataset's shape and the #3 correctness
fix so a refactor can't silently change the numbers."""


def test_row_and_category_counts(store):
    df = store.df
    assert len(df) == 86400
    assert set(df["Region"].dropna().unique()) == {"INW", "K-S"}
    assert set(df["Source"].dropna().unique()) == {"Woods run", "Improved"}
    assert len(store.years()) == 3
    assert len(store.metrics()) == 3
    assert len(store.installations_all()) == 16


def test_installations_measured_per_year(store):
    measured = store.df.dropna(subset=["Value"]).groupby("Year")["Installation"].nunique()
    assert measured["Year1"] == 16
    assert measured["Year2"] == 13
    assert measured["Year3"] == 6          # Year 3 is under-sampled by design


def test_growth_means_exclude_dead_and_replacement(store):
    """seedlot_table 'n' must equal the *living* tree count (dead/replacement
    excluded), and that must be strictly fewer than the raw row count for a
    replacement-heavy cell."""
    raw = store.df
    sel = ((raw["Installation"] == "CASA") & (raw["Year"] == "Year1")
           & (raw["Metric"] == "VOLUME GROWTH (CM3)") & (raw["Source"] == "Improved"))
    cell = raw[sel]
    living = cell[~cell["IsDead"]]
    st = store.seedlot_table
    n = st[(st["Installation"] == "CASA") & (st["Year"] == "Year1")
           & (st["Metric"] == "VOLUME GROWTH (CM3)") & (st["Source"] == "Improved")]["n"].sum()
    assert int(n) == len(living)
    assert len(living) < len(cell)          # some rows were dead/replacement


def test_mortality_counts_dead_and_replacement(store):
    """Mortality keeps counting dead + replacement even though growth excludes them."""
    mt = store.mortality_table
    m = mt[(mt["Installation"] == "CASA") & (mt["Year"] == "Year1")
           & (mt["Metric"] == "VOLUME GROWTH (CM3)") & (mt["Source"] == "Improved")]["Mortality %"].mean()
    assert m > 0


def test_isdead_consistent_across_metrics(store):
    """A tree's dead flag is identical on its caliper/height/volume rows."""
    key = ["Installation", "Year", "PLOT", "TREE", "Replication", "Seedlot"]
    varies = store.df.groupby(key)["IsDead"].nunique()
    assert int((varies > 1).sum()) == 0
