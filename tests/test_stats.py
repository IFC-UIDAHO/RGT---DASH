# -*- coding: utf-8 -*-
"""Golden-value tests for the statistics layer: realized gain (living cohort),
the Benjamini-Hochberg FDR helper, the absolute-gain productivity regression,
and the deployment verdict. These protect the headline math through refactors."""
import math

import numpy as np

from rgt_dashboard import stats


def test_realized_gain_living_cohort(store):
    """Gains match the surviving-cohort values verified for the #3 fix."""
    r = stats.compare_sources(store, region="K-S", installation="PLAN D #1",
                              year="Year1", metric="VOLUME GROWTH (CM3)")
    assert r is not None
    assert abs(r.gain_pct - 14.5) < 0.6

    r2 = stats.compare_sources(store, region="INW", installation="CASA",
                               year="Year1", metric="VOLUME GROWTH (CM3)")
    assert abs(r2.gain_pct - 33.1) < 0.6


def test_gain_pct_matches_formula(store):
    r = stats.compare_sources(store, region="INW", installation="HOODOO",
                              year="Year1", metric="HEIGHT GROWTH (CM)")
    expected = 100 * (r.improved_mean - r.woods_mean) / r.woods_mean
    assert abs(r.gain_pct - expected) < 0.1


def test_benjamini_hochberg_golden():
    q = stats.benjamini_hochberg([0.001, 0.01, 0.02, 0.5])
    assert np.allclose(q, [0.004, 0.02, 0.0266667, 0.5], atol=1e-4)


def test_benjamini_hochberg_properties():
    # NaN preserved in place
    q = stats.benjamini_hochberg([0.01, float("nan"), 0.9])
    assert math.isnan(q[1])
    # q >= p, and FDR is never more liberal than raw
    p = np.sort(np.random.RandomState(0).uniform(0, 0.2, 12))
    q = stats.benjamini_hochberg(p)
    assert np.all(q >= p - 1e-12)
    assert int((q < 0.05).sum()) <= int((p < 0.05).sum())


def test_apply_fdr_is_conservative_and_keeps_raw(store):
    gdf = stats.gain_by_installation(store, region="INW", year="Year1",
                                     metric="VOLUME GROWTH (CM3)", inst_type="CORE")
    adj = stats.apply_fdr(gdf)
    assert "p_raw" in adj.columns
    assert int(adj["significant"].sum()) <= int(gdf["significant"].sum())


def test_productivity_relationship_runs(store):
    gdf = stats.gain_by_installation(store, region="INW", year="Year1",
                                     metric="HEIGHT GROWTH (CM)", inst_type="CORE")
    rel = stats.productivity_relationship(gdf)
    assert rel["n"] >= 3
    assert not math.isnan(rel["r"])


def test_deployment_call_verdict(store):
    dc = stats.deployment_call(store, region="INW", installation="HOODOO")
    assert dc["level"] in {"deploy", "caution", "hold", "none"}
    assert dc["n"] >= 1
    # HOODOO shows large, significant positive gains with low mortality.
    assert dc["level"] == "deploy"
