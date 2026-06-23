# -*- coding: utf-8 -*-
"""
build_dataset.py — turn a raw field-data Excel workbook into the long-format CSV
the RGT dashboard consumes (data/rgt_data.csv).

Replaces the old hand-run notebook. Designed to be ROBUST to how new data arrives:

  * Whatever INSTALLATIONS are in the workbook get refreshed; every other
    installation already in the dashboard is kept untouched. So it handles:
      - only INW  (keeps K-S)            - only K-S (keeps INW)
      - both regions                     - a new installation (added)
      - a partial file of some sites     - a corrected re-export
  * Number of measurement YEARS is auto-detected (CAL0..CALn), so a future
    Year-4 just works.
  * Column names are matched flexibly; if an ESSENTIAL column is missing the
    build fails loudly instead of writing silent garbage.
  * REGION is resolved from the workbook's REGION code, and—if unknown—from how
    that installation is already classified in the dashboard. Truly unknown ones
    are reported, never silently mislabelled.

Run:
    python tools/build_dataset.py -i <workbook.xlsx>         # update the live CSV
    python tools/build_dataset.py -i <workbook.xlsx> --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SHEET = "DATA"

SOURCE_MAP = {"WR": "Woods run", "IMP": "Improved",
              "WOODS RUN": "Woods run", "WOODSRUN": "Woods run", "IMPROVED": "Improved"}

KNOWN_REGIONS = {"INW", "K-S"}
# Raw REGION code -> dashboard region. Add new codes here as programmes appear.
REGION_MAP = {
    "NID": "INW", "NEWA": "INW", "NEOR": "INW",          # INW programme
    "K-S": "K-S", "KS": "K-S", "K_S": "K-S", "KLAMATH": "K-S", "SISKIYOU": "K-S",
    "INW": "INW",
}
# Raw SITE NAME -> dashboard canonical Installation name (only where they differ).
INSTALLATION_RENAME = {"SHERRY TRAN": "SHERRY TRANSFER"}

METRIC_LABEL = {"CAL": "CALIPER GROWTH (MM)", "HT": "HEIGHT GROWTH (CM)",
                "VOL": "VOLUME GROWTH (CM3)"}
UNIT = {"CAL": "mm", "HT": "cm", "VOL": "cm3"}

MANAGEMENT_MAP = {"1": "MINOR", "2": "MAJOR", "80": "DEAD", "81": "DEAD (REPLACEMENT)"}
DEFECT_MAP = {
    "11": "UNHEALTHY", "12": "SUPPRESSED", "13": "HERBICIDE", "31": "FORKED STEM",
    "32": "EXCESSIVE LEAN", "34": "DEFORMED STEM", "35": "EXCESSIVELY SMALL CROWN",
    "37": "MULTIPLE LEADERS", "38": "BAYONET TOP", "39": "BROKEN TOP", "40": "DEAD TOP",
    "41": "STEM DAMAGE", "42": "SCALPED TOP", "51": "BARK BEETLE", "61": "RUST",
    "63": "ROOT ROT", "64": "BLIGHT", "65": "STEM CANKER", "72": "RODENT",
    "73": "PORCUPINE", "74": "DEER OR ELK DAMAGE", "75": "WILDLIFE", "81": "WIND",
    "83": "SNOW", "84": "FROST",
}

FINAL_COLUMNS = ["Region", "Installation", "Source", "Seedlot", "PLOT", "TREE",
                 "Replication", "Year", "Value", "Metric", "Management", "Defect"]


# --------------------------------------------------------------------------- #
# Column finding (flexible) + helpers
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _find_col(df: pd.DataFrame, *patterns: str) -> str | None:
    """Return the first column whose normalised name matches any normalised pattern."""
    norm = {_norm(c): c for c in df.columns}
    for p in patterns:
        np_ = _norm(p)
        if np_ in norm:
            return norm[np_]
    # loose contains-match fallback
    for p in patterns:
        np_ = _norm(p)
        for k, orig in norm.items():
            if np_ and np_ in k:
                return orig
    return None


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace(".", np.nan), errors="coerce")


def _code_str(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64").astype("string")


def _detect_years(df: pd.DataFrame) -> list[int]:
    """How many measurement years (CAL0..CALn & HT0..HTn) are present? -> [1..n]."""
    n = 0
    for y in range(0, 20):
        if _find_col(df, f"CAL{y} (mm)", f"CAL{y}") and _find_col(df, f"HT{y} (cm)", f"HT{y}"):
            n = y
        else:
            break
    return list(range(1, n + 1))  # growth years (relative to year 0)


# --------------------------------------------------------------------------- #
class BuildError(Exception):
    pass


def transform_workbook(xlsx_path: Path, sheet: str = SHEET):
    """Raw workbook -> (long dashboard frame, notes list)."""
    df = pd.read_excel(xlsx_path, sheet_name=sheet)
    notes: list[str] = []

    c_site = _find_col(df, "SITE NAME", "Installation", "SITE")
    c_blk = _find_col(df, "BLK NAME", "Source", "BLOCK", "BLK")
    c_seed = _find_col(df, "SEEDLOT NAME", "Seedlot", "SEEDLOT")
    c_region = _find_col(df, "REGION")
    c_plot = _find_col(df, "PLOT")
    c_tree = _find_col(df, "TREE")
    essential = {"SITE NAME": c_site, "BLK NAME": c_blk, "PLOT": c_plot, "TREE": c_tree}
    missing = [k for k, v in essential.items() if v is None]
    if missing:
        raise BuildError(f"workbook is missing essential column(s): {missing}. "
                         f"Found columns: {list(df.columns)}")

    years = _detect_years(df)
    if not years:
        raise BuildError("could not find measurement columns CAL0/HT0 .. ; "
                         "is this the right sheet/format?")
    notes.append(f"detected {len(years)} growth year(s): {years}")

    d = pd.DataFrame()
    d["Installation"] = df[c_site].astype(str).str.strip().replace(INSTALLATION_RENAME)
    d = d[df[c_site].notna().values].copy()
    src = df.loc[d.index, c_blk].astype(str).str.strip().str.upper()
    d["Source"] = src.map(SOURCE_MAP).fillna(src)
    d["Seedlot"] = (df.loc[d.index, c_seed].astype(str).str.strip() if c_seed else "")
    d["PLOT"] = pd.to_numeric(df.loc[d.index, c_plot], errors="coerce").astype("Int64")
    d["TREE"] = pd.to_numeric(df.loc[d.index, c_tree], errors="coerce").astype("Int64")

    # Region: map the raw code; unknowns are left as the raw code for now and
    # resolved against the existing dashboard data in build().
    if c_region is not None:
        raw_region = df.loc[d.index, c_region].astype(str).str.strip().str.upper()
        d["Region"] = raw_region.map(REGION_MAP).fillna(raw_region)
    else:
        d["Region"] = np.nan

    # Replication = replicate-plot rank within (Installation, Source): R1, R2 ...
    rank = (d.groupby(["Installation", "Source"])["PLOT"]
              .transform(lambda s: s.rank(method="dense").astype("Int64")))
    d["Replication"] = "R" + rank.astype(str)

    # numeric measurement columns + volume, per detected year
    meas = pd.DataFrame(index=d.index)
    for y in [0] + years:
        cal = _find_col(df, f"CAL{y} (mm)", f"CAL{y}")
        ht = _find_col(df, f"HT{y} (cm)", f"HT{y}")
        meas[f"CAL{y}"] = _num(df.loc[d.index, cal]) if cal else np.nan
        meas[f"HT{y}"] = _num(df.loc[d.index, ht]) if ht else np.nan
        meas[f"VOL{y}"] = (meas[f"CAL{y}"] / 10.0) ** 2 * meas[f"HT{y}"]

    id_cols = ["Region", "Installation", "Source", "Seedlot", "PLOT", "TREE", "Replication"]
    frames = []
    for prefix in ("CAL", "HT", "VOL"):
        m = d[id_cols].copy()
        for y in years:
            m[f"Year{y}"] = meas[f"{prefix}{y}"] - meas[f"{prefix}0"]
        m = m.melt(id_vars=id_cols, value_vars=[f"Year{y}" for y in years],
                   var_name="Year", value_name="Value")
        m["Metric"] = METRIC_LABEL[prefix]
        frames.append(m)
    long_df = pd.concat(frames, ignore_index=True)

    # Management / Defect codes -> labels
    def status_long(name, mapping, *find):
        s = d[id_cols].copy()
        for y in years:
            col = _find_col(df, *[p.format(y=y) for p in find])
            s[f"Year{y}"] = _code_str(df.loc[d.index, col]) if col else pd.NA
        s = s.melt(id_vars=id_cols, value_vars=[f"Year{y}" for y in years],
                   var_name="Year", value_name=name)
        s[name] = s[name].map(mapping)
        return s

    long_df = long_df.merge(status_long("Management", MANAGEMENT_MAP, "MC{y}"),
                            on=id_cols + ["Year"], how="left")
    long_df = long_df.merge(status_long("Defect", DEFECT_MAP, "DC{y}"),
                            on=id_cols + ["Year"], how="left")
    return long_df[FINAL_COLUMNS], notes


def merge_upsert(new: pd.DataFrame, old: pd.DataFrame | None):
    """Replace—in `old`—every installation present in `new`; keep all the rest.
    Also resolves any unknown Region on `new` from how `old` classifies that
    installation. Returns (combined_df, notes)."""
    notes = []
    new = new.copy()
    if old is not None and "Region" in old.columns and "Installation" in old.columns:
        inst_region = (old.dropna(subset=["Region"]).assign(
            Installation=lambda x: x["Installation"].astype(str).str.strip())
            .groupby("Installation")["Region"].first().to_dict())
        def fix_region(row):
            if row["Region"] in KNOWN_REGIONS:
                return row["Region"]
            return inst_region.get(str(row["Installation"]).strip(), row["Region"])
        new["Region"] = new.apply(fix_region, axis=1)

    if old is None or not len(old):
        return new.reset_index(drop=True), notes

    new_installs = set(new["Installation"].astype(str).str.strip())
    old_installs = set(old["Installation"].astype(str).str.strip())
    refreshed = sorted(new_installs & old_installs)
    added = sorted(new_installs - old_installs)
    kept = sorted(old_installs - new_installs)
    notes.append(f"refreshed {len(refreshed)} installation(s); "
                 f"added {len(added)}: {added or '—'}; "
                 f"kept {len(kept)} untouched: {kept or '—'}")

    keep = old[~old["Installation"].astype(str).str.strip().isin(new_installs)].copy()
    keep = keep[[c for c in FINAL_COLUMNS if c in keep.columns]]
    out = pd.concat([new, keep], ignore_index=True)
    return out, notes


def build(input_xlsx: Path, output_csv: Path, sheet: str = SHEET):
    new, notes = transform_workbook(input_xlsx, sheet=sheet)
    old = pd.read_csv(output_csv) if output_csv.exists() else None
    out, mnotes = merge_upsert(new, old)
    notes += mnotes
    out = out.sort_values(["Region", "Installation", "Source", "PLOT", "Seedlot",
                           "Year", "Metric"],
                          ascending=[True, True, False, True, True, True, True]
                          ).reset_index(drop=True)
    return out, notes


def validate(df: pd.DataFrame, map_installations: set | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). errors -> do NOT apply; warnings -> apply but tell the user."""
    errors, warns = [], []
    miss = [c for c in FINAL_COLUMNS if c not in df.columns]
    if miss:
        return [f"missing columns: {miss}"], warns
    bad_src = set(df["Source"].dropna().unique()) - {"Woods run", "Improved"}
    if bad_src:
        errors.append(f"unexpected Source values: {bad_src}")
    bad_metric = set(df["Metric"].dropna().unique()) - set(METRIC_LABEL.values())
    if bad_metric:
        errors.append(f"unexpected Metric values: {bad_metric}")
    if not re.fullmatch(r"Year\d+", str(df["Year"].dropna().iloc[0])):
        errors.append("Year column not formatted like 'Year1'")
    for c in ("Installation", "Source", "Year", "Metric"):
        if df[c].isna().any():
            errors.append(f"nulls in key column {c}")
    if df["Value"].notna().sum() == 0:
        errors.append("Value column is entirely empty")
    if len(df) < 500:
        errors.append(f"suspiciously few rows: {len(df)}")

    unknown_region = sorted(set(df["Region"].dropna().unique()) - KNOWN_REGIONS)
    if unknown_region:
        warns.append(f"region(s) not recognised (add to REGION_MAP): {unknown_region}")
    if map_installations is not None:
        new_to_map = sorted(set(df["Installation"].unique()) - map_installations)
        if new_to_map:
            warns.append(f"installation(s) with no map pin yet (data shows, map won't): {new_to_map}")
    return errors, warns


def _map_installations():
    """Installations the map knows about (so we can flag sites needing coordinates)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from rgt_dashboard.map_builder import LOCATIONS
        names = set()
        for loc in LOCATIONS:
            names.update(loc.get("csv", []))
        return names
    except Exception:
        return None


def main(argv=None):
    here = Path(__file__).resolve().parent
    default_out = here.parent / "data" / "rgt_data.csv"
    ap = argparse.ArgumentParser(description="Build the dashboard CSV from a raw RGT Excel workbook.")
    ap.add_argument("--input", "-i", required=True, type=Path)
    ap.add_argument("--output", "-o", type=Path, default=default_out)
    ap.add_argument("--sheet", default=SHEET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        out, notes = build(args.input, args.output, sheet=args.sheet)
    except BuildError as e:
        print(f"[build_dataset] ERROR: {e}")
        return 2

    errors, warns = validate(out, map_installations=_map_installations())
    for nt in notes:
        print(f"[build_dataset] {nt}")
    print(f"[build_dataset] result rows={len(out)} installations={out['Installation'].nunique()} "
          f"regions={sorted(out['Region'].dropna().unique())}")
    for w in warns:
        print(f"[build_dataset] NOTE: {w}")
    if errors:
        print("[build_dataset] VALIDATION FAILED (not applied):")
        for e in errors:
            print("   -", e)
        return 2
    if args.dry_run:
        print("[build_dataset] dry-run OK (not written)")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        import shutil
        shutil.copy2(args.output, args.output.with_name(args.output.stem + ".prev.csv"))
    out.to_csv(args.output, index=False)
    print(f"[build_dataset] wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
