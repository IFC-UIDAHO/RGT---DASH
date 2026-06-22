# -*- coding: utf-8 -*-
"""
map_builder.py  —  Generates assets/installations_map.html at startup.

Premium interactive map: ESRI satellite tiles, custom teardrop SVG pins
coloured by average realized gain, dark-glass slide-in info panel with
year × metric gain matrix, Google-Earth zoom animation on load.
"""
from __future__ import annotations

import json
import math
import traceback
from pathlib import Path

from . import config

# ─────────────────────────────────────────────────────────────────────────────
# Installation location table  (from AllRGT.xlsx)
# ─────────────────────────────────────────────────────────────────────────────
LOCATIONS = [
    # Pin coordinates are the CENTROID of each installation's 6 plots, derived
    # from plots.gdb (see data/plot_grids.geojson), so every pin sits on its plots.
    # Installations with both a Core and a Transfer site get a separate pin each.
    # INW — Idaho / Washington
    {"name": "Hoodoo Saddle", "lat": 48.036754, "lon": -116.912039, "region": "INW",
     "csv": ["HOODOO"]},
    {"name": "Lost Fromelt", "lat": 46.446858, "lon": -115.800729, "region": "INW",
     "csv": ["LOST FROMELT"]},
    {"name": "Silver Spur", "lat": 46.668815, "lon": -116.316722, "region": "INW",
     "csv": ["SILVER SPUR"]},
    {"name": "Wild Turkey", "lat": 48.790739, "lon": -117.725894, "region": "INW",
     "csv": ["WILD TURKEY"]},
    {"name": "Sherry Ridge — Core", "lat": 48.596225, "lon": -117.505798, "region": "INW",
     "csv": ["SHERRY CORE"]},
    {"name": "Sherry Ridge — Transfer", "lat": 48.598404, "lon": -117.502849, "region": "INW",
     "csv": ["SHERRY TRANSFER"]},
    {"name": "Sitka — Core", "lat": 45.525461, "lon": -118.468884, "region": "INW",
     "csv": ["SITKA CORE"]},
    {"name": "Sitka — Transfer", "lat": 45.526377, "lon": -118.467627, "region": "INW",
     "csv": ["SITKA TRAN"]},
    {"name": "Casa", "lat": 45.826505, "lon": -117.724993, "region": "INW",
     "csv": ["CASA"]},
    {"name": "Dawson's Delight", "lat": 48.767898, "lon": -116.247506, "region": "INW",
     "csv": ["DAWSON"]},
    {"name": "Gold View", "lat": 46.998902, "lon": -116.156557, "region": "INW",
     "csv": ["GOLDVIEW"]},
    {"name": "Carscallen — Core", "lat": 47.028726, "lon": -116.852722, "region": "INW",
     "csv": ["CARSCALLEN CORE"]},
    {"name": "Carscallen — Transfer", "lat": 47.028908, "lon": -116.850874, "region": "INW",
     "csv": ["CARSCALLEN TRANSFER"]},
    # K-S — Southern Oregon
    {"name": "Boundary North", "lat": 42.704539, "lon": -122.408166, "region": "K-S",
     "csv": []},
    {"name": "Plan D", "lat": 42.709518, "lon": -122.495879, "region": "K-S",
     "csv": ["PLAN D #1"]},
    {"name": "Lodgepole 1", "lat": 42.622863, "lon": -122.434097, "region": "K-S",
     "csv": ["LODGEPOLE 1"]},
    {"name": "Lodgepole 2", "lat": 42.600534, "lon": -122.427863, "region": "K-S",
     "csv": ["LODGEPOLE 2"]},
    {"name": "Rum Creek", "lat": 42.599773, "lon": -123.646166, "region": "K-S",
     "csv": []},
    {"name": "Lickity Split", "lat": 42.140928, "lon": -122.921594, "region": "K-S",
     "csv": []},
    {"name": "Big Butte", "lat": 42.549727, "lon": -122.537667, "region": "K-S",
     "csv": []},
    {"name": "Fish Hatchery", "lat": 42.535804, "lon": -122.54024, "region": "K-S",
     "csv": []},
]


def _safe(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except (TypeError, ValueError):
        return None


def build_map_data(store) -> list:
    """Compute per-installation gain KPIs for map popup cards."""
    try:
        from . import stats as _stats
    except ImportError:
        return [dict(loc, gains={}, avg_gain=None, vol_gain=None) for loc in LOCATIONS]

    metrics = list(store.metrics())
    years   = list(store.years())

    result = []
    for loc in LOCATIONS:
        if not loc.get("csv"):
            # Installed site with no trial data yet — still show a (grey) pin.
            result.append(dict(loc, gains={}, avg_gain=None, vol_gain=None, n_years=0))
            continue
        entry = dict(loc)
        entry["gains"]    = {}
        entry["n_years"]  = 0
        all_gains         = []

        for csv_name in loc["csv"]:
            region = loc["region"]
            try:
                df_r = store.df[store.df["Installation"] == csv_name]
                if not df_r.empty:
                    region = str(df_r["Region"].iloc[0])
            except Exception:
                pass

            entry["gains"][csv_name] = {}
            years_with_data = set()
            for year in years:
                entry["gains"][csv_name][year] = {}
                for metric in metrics:
                    short = config.METRICS.get(metric, {}).get("short", metric)
                    unit  = config.METRICS.get(metric, {}).get("unit",  "")
                    try:
                        r = _stats.compare_sources(
                            store, region=region, installation=csv_name,
                            year=year, metric=metric,
                        )
                        if r is None:
                            continue
                        g = _safe(r.gain_pct)
                        if g is not None:
                            all_gains.append(g)
                            years_with_data.add(year)
                        entry["gains"][csv_name][year][short] = {
                            "gain_pct":   g,
                            "stars":      r.stars or "",
                            "woods_mean": _safe(r.woods_mean),
                            "imp_mean":   _safe(r.improved_mean),
                            "unit":       unit,
                            "p":          _safe(r.p_value),
                            "imp_mort":   _safe(r.improved_mortality),
                            "woods_mort": _safe(r.woods_mortality),
                            "n_woods":    int(r.n_woods_trees or 0),
                            "n_imp":      int(r.n_improved_trees or 0),
                        }
                    except Exception:
                        pass
            entry["n_years"] = max(entry.get("n_years", 0), len(years_with_data))

        entry["avg_gain"] = (
            round(sum(all_gains) / len(all_gains), 1) if all_gains else None
        )
        # Pin colour metric = latest-year VOLUME realized gain (the standard
        # genetic-gain metric), not the cross-metric average.
        vol_gain = None
        for csv_name in loc["csv"]:
            cg = entry["gains"].get(csv_name, {})
            for year in years:                      # ascending -> keep the latest with data
                d = cg.get(year, {}).get("Volume")
                if d and d.get("gain_pct") is not None:
                    vol_gain = d["gain_pct"]
        entry["vol_gain"] = vol_gain
        result.append(entry)

    return result


def load_plot_grids() -> dict:
    """Load the per-plot grid polygons (6 plots per installation) as a GeoJSON
    FeatureCollection. The file is pre-generated from plots.gdb into data/ so the
    app stays self-contained (no geopandas/GDAL needed at runtime or on the host).

    Returns an empty FeatureCollection if the file is missing, so the map still
    renders (just without the zoom-in plot overlay)."""
    path = config.DATA_DIR / "plot_grids.geojson"
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        traceback.print_exc()
    return {"type": "FeatureCollection", "features": []}


def generate_map_html(store) -> None:
    """Build assets/installations_map.html with embedded KPI data."""
    try:
        data = build_map_data(store)
    except Exception:
        traceback.print_exc()
        data = [dict(loc, gains={}, avg_gain=None, vol_gain=None, n_years=0) for loc in LOCATIONS]

    json_blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    grids_blob = json.dumps(load_plot_grids(), ensure_ascii=False, separators=(",", ":"))
    html_text = (_TEMPLATE
                 .replace("/*__RGT_DATA__*/[]", json_blob)
                 .replace("/*__RGT_PLOTS__*/{}", grids_blob))

    n_plots = len(json.loads(grids_blob).get("features", []))
    out = config.ASSETS_DIR / "installations_map.html"
    out.write_text(html_text, encoding="utf-8")
    print(f"[map_builder] Written {out}  ({len(data)} installations, {n_plots} plot polygons)")


# ─────────────────────────────────────────────────────────────────────────────
# HTML template  (/*__RGT_DATA__*/[] is replaced with the JSON blob)
# ─────────────────────────────────────────────────────────────────────────────
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RGT Installations</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body,#map{width:100%;height:100%;background:#0d1b2a;font-family:'Inter',sans-serif}

/* ── Intro splash ──────────────────────────────────────────────────────────── */
#intro{
  position:absolute;inset:0;z-index:10000;
  background:radial-gradient(ellipse at 40% 60%,#0f2a4a 0%,#060e1a 70%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  transition:opacity 1s ease;pointer-events:none;
}
#intro.fade{opacity:0}
.i-badge{
  font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:#DBA800;background:rgba(219,168,0,.12);border:1px solid rgba(219,168,0,.3);
  padding:4px 14px;border-radius:20px;margin-bottom:18px;
}
.i-title{
  font-size:28px;font-weight:800;color:#fff;letter-spacing:-.5px;
  margin-bottom:6px;text-align:center;
}
.i-sub{font-size:13px;color:rgba(255,255,255,.45);margin-bottom:32px;text-align:center}
.i-dots{display:flex;gap:9px}
.i-dots span{
  width:8px;height:8px;border-radius:50%;background:#DBA800;
  animation:pulse 1.5s ease-in-out infinite;
}
.i-dots span:nth-child(2){animation-delay:.5s}
.i-dots span:nth-child(3){animation-delay:1s}
@keyframes pulse{0%,100%{opacity:.2;transform:scale(1)}50%{opacity:1;transform:scale(1.3)}}

/* ── Region filter chips ───────────────────────────────────────────────────── */
#chips{
  position:absolute;top:14px;left:50%;transform:translateX(-50%);
  z-index:9500;display:flex;gap:6px;opacity:0;transition:opacity .5s;
}
#chips.on{opacity:1}
.chip{
  padding:6px 16px;border-radius:30px;font-size:12px;font-weight:700;
  cursor:pointer;border:1.5px solid transparent;transition:all .2s;
  letter-spacing:.3px;box-shadow:0 2px 12px rgba(0,0,0,.4);
}
.chip-all{background:rgba(255,255,255,.12);color:#fff;border-color:rgba(255,255,255,.2)}
.chip-all:hover,.chip-all.active{background:rgba(255,255,255,.22);border-color:#DBA800;color:#DBA800}
.chip-inw{background:rgba(21,101,192,.7);color:#fff;border-color:rgba(21,101,192,.4)}
.chip-inw:hover,.chip-inw.active{background:#1565c0;border-color:#DBA800}
.chip-ks{background:rgba(136,14,79,.7);color:#fff;border-color:rgba(136,14,79,.4)}
.chip-ks:hover,.chip-ks.active{background:#880e4f;border-color:#DBA800}

/* ── Slide-in info panel ───────────────────────────────────────────────────── */
#panel{
  position:absolute;top:14px;right:14px;bottom:14px;
  width:360px;max-width:calc(100vw - 28px);
  background:rgba(10,20,36,.93);
  backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);
  border:1px solid rgba(219,168,0,.18);
  border-radius:20px;
  box-shadow:0 12px 60px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.06);
  z-index:9001;
  display:flex;flex-direction:column;
  transform:translateX(400px);
  transition:transform .4s cubic-bezier(.34,1.3,.64,1);
  overflow:hidden;color:#fff;
}
#panel.open{transform:translateX(0)}

/* Panel header */
.ph{
  padding:18px 20px 14px;
  background:linear-gradient(135deg,rgba(22,70,122,.6) 0%,rgba(10,20,36,.4) 100%);
  border-bottom:1px solid rgba(255,255,255,.06);flex-shrink:0;
}
.ph-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.ph-name{font-size:19px;font-weight:800;color:#fff;letter-spacing:-.3px;line-height:1.2}
.ph-close{
  width:28px;height:28px;border-radius:50%;border:none;
  background:rgba(255,255,255,.1);color:rgba(255,255,255,.7);
  cursor:pointer;font-size:16px;line-height:28px;text-align:center;
  transition:background .15s;flex-shrink:0;
}
.ph-close:hover{background:rgba(255,255,255,.2);color:#fff}
.ph-badges{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.pb{
  padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;
  letter-spacing:.5px;text-transform:uppercase;
}
.pb-inw{background:rgba(21,101,192,.35);border:1px solid rgba(21,101,192,.5);color:#90caf9}
.pb-ks{background:rgba(136,14,79,.35);border:1px solid rgba(136,14,79,.5);color:#f48fb1}
.pb-core{background:rgba(46,125,50,.3);border:1px solid rgba(46,125,50,.5);color:#a5d6a7}
.pb-xfer{background:rgba(230,81,0,.25);border:1px solid rgba(230,81,0,.4);color:#ffcc80}
.pb-nd{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:rgba(255,255,255,.45)}

/* Avg gain hero row */
.ph-gain{
  display:flex;align-items:center;justify-content:space-between;
  margin-top:12px;padding:10px 14px;
  background:rgba(255,255,255,.04);border-radius:10px;
  border:1px solid rgba(255,255,255,.06);
}
.ph-gain-lbl{font-size:11px;font-weight:600;color:rgba(255,255,255,.45);text-transform:uppercase;letter-spacing:.6px}
.ph-gain-val{font-size:24px;font-weight:800;letter-spacing:-.5px}
.gpos{color:#69f0ae}.gneg{color:#ff5252}.gns{color:rgba(255,255,255,.3)}

.ph-meta{
  display:flex;gap:12px;margin-top:10px;
}
.ph-meta-item{
  flex:1;padding:8px 12px;background:rgba(255,255,255,.04);
  border-radius:8px;border:1px solid rgba(255,255,255,.06);text-align:center;
}
.ph-meta-val{font-size:16px;font-weight:700;color:#DBA800}
.ph-meta-lbl{font-size:10px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}

/* Panel body */
.pb-body{flex:1;overflow-y:auto;padding:16px 20px 20px}
.pb-body::-webkit-scrollbar{width:4px}
.pb-body::-webkit-scrollbar-track{background:transparent}
.pb-body::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:4px}

/* Section title */
.sec{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;
     color:rgba(255,255,255,.3);margin:14px 0 8px;
     padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,.06)}
.sec:first-child{margin-top:0}

/* Gain matrix table */
.gm{width:100%;border-collapse:separate;border-spacing:3px;font-size:12px}
.gm th{
  padding:5px 8px;text-align:center;font-size:10px;font-weight:700;
  color:rgba(255,255,255,.35);text-transform:uppercase;letter-spacing:.5px;
}
.gm th:first-child{text-align:left}
.gm td{
  padding:6px 8px;text-align:center;border-radius:6px;
  font-weight:700;font-size:12px;
}
.gm td:first-child{text-align:left;color:rgba(255,255,255,.5);font-weight:600;
                   background:transparent!important;font-size:11px}

/* Mortality row */
.mort{
  margin-top:10px;padding:8px 12px;background:rgba(255,255,255,.03);
  border-radius:8px;font-size:11px;color:rgba(255,255,255,.4);
  border:1px solid rgba(255,255,255,.05);
}
.mort strong{color:rgba(255,255,255,.6)}

/* No-data notice */
.nodata{
  text-align:center;padding:24px;color:rgba(255,255,255,.3);
  font-size:13px;font-style:italic;
}

/* Mini year plots (Improved vs Woods Run means) */
.mini-legend{display:flex;gap:13px;align-items:center;font-size:10.5px;color:rgba(255,255,255,.55);margin:2px 0 8px}
.mini-legend i{display:inline-block;width:11px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.mini-legend .ml-x{margin-left:auto;font-style:italic;color:rgba(255,255,255,.35)}
.minis{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px}
.minis .mini:nth-child(3){grid-column:1 / -1}
.mini{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:9px;padding:6px 8px 2px}
.mini-h{font-size:10px;font-weight:700;color:rgba(255,255,255,.72)}
.mini-h span{color:rgba(255,255,255,.4);font-weight:500}
.mini-svg{width:100%;height:62px;display:block;overflow:visible}

/* Explore button */
.explore-btn{
  display:block;width:100%;margin-top:16px;padding:12px;
  background:linear-gradient(135deg,#1a5499,#16467a);
  color:#fff;border:none;border-radius:12px;
  cursor:pointer;font-size:14px;font-weight:700;
  letter-spacing:.3px;transition:all .2s;
  box-shadow:0 4px 16px rgba(22,70,122,.4);
}
.explore-btn:hover{background:linear-gradient(135deg,#1e63b5,#1a5499);
                   box-shadow:0 6px 24px rgba(22,70,122,.6);transform:translateY(-1px)}

/* ── Animated pins (compact, with always-on name labels) ───────────────────── */
.rgt-pin{position:relative;width:28px;height:36px;
  animation:pinDrop .55s cubic-bezier(.34,1.56,.64,1) both;transform-origin:50% 100%;}
.rgt-pin.staggered{animation-delay:calc(var(--i,0) * 55ms);}
.rgt-pin svg{transition:transform .16s ease;transform-origin:50% 100%;position:relative;z-index:2;}
.rgt-pin:hover{z-index:1000;}
.rgt-pin:hover svg{transform:scale(1.22) translateY(-3px);}
.rgt-pin:hover .pin-label{background:rgba(22,70,122,.96);border-color:#f0b429;color:#fff;}
@keyframes pinDrop{0%{transform:translateY(-44px) scale(.3);opacity:0}65%{opacity:1}100%{transform:none;opacity:1}}
.pin-pulse{position:absolute;left:14px;top:13px;width:20px;height:20px;border-radius:50%;
  background:var(--c,#1b5e20);transform:translate(-50%,-50%);opacity:.6;z-index:1;pointer-events:none;
  animation:pinPulse 2.4s ease-out infinite;}
@keyframes pinPulse{0%{transform:translate(-50%,-50%) scale(.5);opacity:.6}
  70%{transform:translate(-50%,-50%) scale(2.3);opacity:0}100%{opacity:0}}
.pin-label{position:absolute;top:34px;left:50%;transform:translateX(-50%);white-space:nowrap;z-index:3;
  font:700 10px/1 'Inter',sans-serif;color:#eaf2fb;background:rgba(8,16,28,.74);
  border:1px solid rgba(255,255,255,.16);padding:2px 6px;border-radius:6px;pointer-events:none;
  text-shadow:0 1px 2px rgba(0,0,0,.7);box-shadow:0 2px 8px rgba(0,0,0,.45);
  -webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);transition:background .15s ease,border-color .15s ease;}

/* ── Gain legend (bottom-left) ─────────────────────────────────────────────── */
#legend{position:absolute;left:14px;bottom:12px;z-index:9400;
  background:rgba(10,20,36,.62);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:8px 11px;color:#fff;
  font-size:10.5px;box-shadow:0 8px 30px rgba(0,0,0,.4);max-width:210px;opacity:0;
  transform:translateY(8px);transition:opacity .5s ease,transform .5s ease;}
#legend:hover{background:rgba(10,20,36,.82)}
#legend.on{opacity:1;transform:none;}
#legend .lg-title{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;
  color:rgba(255,255,255,.55);margin-bottom:7px;}
#legend .lg-scale{display:flex;height:10px;border-radius:5px;overflow:hidden;margin-bottom:5px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.08);}
#legend .lg-scale i{flex:1;}
#legend .lg-ends{display:flex;justify-content:space-between;color:rgba(255,255,255,.6);font-weight:700;font-size:10px;}
#legend .lg-row{display:flex;align-items:center;gap:7px;margin-top:8px;color:rgba(255,255,255,.6);}
#legend .lg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
#legend .lg-note{margin-top:7px;color:rgba(255,255,255,.4);font-style:italic;line-height:1.35;}

/* ── Plot-grid overlay (6 plots per installation) ───────────────────── */
.plot-label{
  background:transparent;border:none;box-shadow:none;
  font:700 9px/1 'Inter',sans-serif;color:rgba(255,255,255,.9);white-space:nowrap;
  text-shadow:0 1px 2px rgba(0,0,0,.8);
  pointer-events:none;
}
/* When zoomed into a site, drop the big pin name label so it does not crowd the
   plot squares (the info panel already shows the name). */
#map.zoomed-in .pin-label{opacity:0;transition:opacity .2s ease;}
.plot-label::before{border:none!important}
.leaflet-tooltip.plot-label{padding:0;margin:0}
.leaflet-popup-content-wrapper{
  background:rgba(10,20,36,.95)!important;color:#fff!important;
  border:1px solid rgba(219,168,0,.28)!important;border-radius:14px!important;
  box-shadow:0 12px 50px rgba(0,0,0,.6)!important;
  -webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);
}
.leaflet-popup-content{margin:13px 16px!important;font-family:'Inter',sans-serif!important;line-height:1.45}
.leaflet-popup-tip{background:rgba(10,20,36,.95)!important;border:1px solid rgba(219,168,0,.28)!important}
.leaflet-popup-close-button{color:rgba(255,255,255,.6)!important}
.pp-name{font-size:15px;font-weight:800;letter-spacing:-.2px;margin-bottom:2px}
.pp-inst{font-size:11px;color:rgba(255,255,255,.5);margin-bottom:9px}
.pp-tag{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;
        font-weight:800;letter-spacing:.5px;text-transform:uppercase}
.pp-imp{background:rgba(224,138,30,.25);border:1px solid rgba(224,138,30,.5);color:#f4c786}
.pp-wr{background:rgba(47,110,143,.3);border:1px solid rgba(47,110,143,.55);color:#8fbcd4}
.pp-area{font-size:11px;color:rgba(255,255,255,.45);margin-top:8px}
#plothint{
  position:absolute;bottom:16px;left:50%;transform:translateX(-50%) translateY(8px);
  z-index:9300;background:rgba(10,20,36,.86);color:rgba(255,255,255,.82);
  border:1px solid rgba(219,168,0,.25);border-radius:24px;padding:7px 16px;
  font:600 11.5px 'Inter',sans-serif;letter-spacing:.2px;
  box-shadow:0 8px 30px rgba(0,0,0,.5);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
  opacity:0;pointer-events:none;transition:opacity .4s ease,transform .4s ease;display:none;
}
#plothint.on{opacity:1;transform:translateX(-50%) translateY(0)}
#plothint b{color:#DBA800;font-weight:800}
.lg-toggle{display:flex;align-items:center;gap:7px;margin-top:9px;
  padding-top:8px;border-top:1px solid rgba(255,255,255,.07);cursor:pointer;
  color:rgba(255,255,255,.7);font-weight:600;font-size:10.5px;user-select:none;}
.lg-toggle:hover{color:#fff}
.lg-sw{position:relative;width:30px;height:16px;border-radius:10px;flex-shrink:0;
  background:rgba(255,255,255,.16);transition:background .2s;}
.lg-sw::after{content:'';position:absolute;top:2px;left:2px;width:12px;height:12px;
  border-radius:50%;background:#fff;transition:transform .2s;}
.lg-toggle.on .lg-sw{background:#1a5499}
.lg-toggle.on .lg-sw::after{transform:translateX(14px)}
.lg-swatch{display:inline-block;width:10px;height:10px;border-radius:3px;flex-shrink:0}
.zoom-btn{
  display:block;width:100%;margin-top:10px;padding:11px;
  background:rgba(255,255,255,.05);color:#eaf2fb;border:1px solid rgba(219,168,0,.3);
  border-radius:12px;cursor:pointer;font-size:13px;font-weight:700;letter-spacing:.3px;
  transition:all .2s;
}
.zoom-btn:hover{background:rgba(219,168,0,.14);border-color:#DBA800;color:#fff}


/* Imagery time slider (bottom-centre) — slim & translucent, brightens on hover */
#timebar{
  position:absolute;left:50%;bottom:12px;transform:translateX(-50%);
  z-index:9300;width:min(560px,calc(100vw - 360px));min-width:290px;
  background:rgba(10,20,36,.42);border:1px solid rgba(255,255,255,.10);
  border-radius:11px;padding:5px 14px 6px;color:#fff;opacity:.72;
  box-shadow:0 6px 20px rgba(0,0,0,.32);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  transition:opacity .2s ease, background .2s ease;
}
#timebar:hover{opacity:1;background:rgba(10,20,36,.8)}
#timebar .tb-head{display:flex;align-items:center;gap:8px;margin-bottom:0}
#timebar .tb-lbl{font:800 9px 'Inter',sans-serif;text-transform:uppercase;letter-spacing:.6px;color:rgba(255,255,255,.42)}
#timebar .tb-val{font:800 12px 'Inter',sans-serif;color:#DBA800}
#timebar .tb-meta{font:600 10px 'Inter',sans-serif;color:rgba(159,230,192,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
#timebar .tb-chk{margin-left:auto;display:flex;align-items:center;gap:5px;font:600 10px 'Inter',sans-serif;color:rgba(255,255,255,.6);cursor:pointer;flex-shrink:0}
#timebar .tb-chk input{accent-color:#DBA800;margin:0}
#timebar input[type=range]{width:100%;-webkit-appearance:none;appearance:none;height:3px;border-radius:3px;
  background:rgba(255,255,255,.16);outline:none;margin:2px 0 1px}
#timebar input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:13px;height:13px;
  border-radius:50%;background:#DBA800;border:2px solid #fff;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.5)}
#timebar input[type=range]::-moz-range-thumb{width:13px;height:13px;border-radius:50%;background:#DBA800;
  border:2px solid #fff;cursor:pointer}
#timebar .tb-ticks{display:flex;justify-content:space-between;margin-top:0}
#timebar .tb-ticks span{font:600 8px 'Inter',sans-serif;color:rgba(255,255,255,.38)}

/* "Imagery" control (custom) — dark glass, top-left under the zoom buttons */
.rgt-imgctl{
  background:rgba(10,20,36,.92)!important;color:#fff!important;
  border:1px solid rgba(219,168,0,.25)!important;border-radius:12px!important;
  box-shadow:0 8px 30px rgba(0,0,0,.5)!important;padding:8px 10px!important;
  -webkit-backdrop-filter:blur(14px)!important;backdrop-filter:blur(14px)!important;
  min-width:158px;
}
.rgt-imgctl .ic-row{display:flex;align-items:center;gap:8px}
.rgt-imgctl .ic-lbl{font:800 10px 'Inter',sans-serif;text-transform:uppercase;letter-spacing:.6px;color:rgba(255,255,255,.55)}
.rgt-imgctl select{
  flex:1;background:rgba(255,255,255,.07);color:#fff;
  border:1px solid rgba(255,255,255,.18);border-radius:7px;
  font:600 12px 'Inter',sans-serif;padding:3px 6px;cursor:pointer;
}
.rgt-imgctl select option{background:#0d1b2a;color:#fff}
.rgt-imgctl .ic-chk{display:flex;align-items:center;gap:6px;margin-top:7px;
  font:600 11px 'Inter',sans-serif;color:rgba(255,255,255,.75);cursor:pointer}
.rgt-imgctl .ic-chk input{accent-color:#DBA800;margin:0}

/* Leaflet overrides */
.leaflet-control-attribution{font-size:10px!important;background:rgba(0,0,0,.45)!important;color:rgba(255,255,255,.5)!important}
.leaflet-control-attribution a{color:rgba(255,255,255,.6)!important}
.leaflet-bar{border:none!important;box-shadow:0 2px 12px rgba(0,0,0,.5)!important}
.leaflet-bar a{background:rgba(10,20,36,.92)!important;color:#fff!important;
               border:1px solid rgba(255,255,255,.1)!important;
               backdrop-filter:blur(8px)!important}
.leaflet-bar a:hover{background:rgba(22,70,122,.8)!important}
</style>
</head>
<body>

<!-- Map container -->
<div id="map"></div>

<!-- Region chips -->
<div id="chips">
  <div class="chip chip-all active" onclick="filterRegion('ALL')">All Regions</div>
  <div class="chip chip-inw" onclick="filterRegion('INW')">INW</div>
  <div class="chip chip-ks"  onclick="filterRegion('K-S')">K-S</div>
</div>

<!-- Gain legend -->
<div id="legend">
  <div class="lg-title">Volume gain &middot; latest yr</div>
  <div class="lg-scale">
    <i style="background:#b71c1c"></i><i style="background:#e53935"></i><i style="background:#ef9a9a"></i><i style="background:#66bb6a"></i><i style="background:#388e3c"></i><i style="background:#2e7d32"></i><i style="background:#1b5e20"></i>
  </div>
  <div class="lg-ends"><span>&minus;10%</span><span>0</span><span>+20%</span></div>
  <div class="lg-toggle on" id="plotToggle" onclick="togglePlots()">
    <span class="lg-sw"></span>
    <span>Show plot grids</span>
  </div>
  <div class="lg-row" style="margin-top:8px">
    <span class="lg-swatch" style="background:transparent;border:2px solid #FFB74D"></span>Improved (IMP&nbsp;4–6)
  </div>
  <div class="lg-row">
    <span class="lg-swatch" style="background:transparent;border:2px solid #4FC3F7"></span>Woods&nbsp;Run (WR&nbsp;1–3)
  </div>
</div>

<!-- Imagery time slider (built live from the Esri Wayback index) -->
<div id="timebar"></div>

<!-- Info panel -->
<div id="panel">
  <div class="ph" id="ph"></div>
  <div class="pb-body" id="pb-body"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ── Data ────────────────────────────────────────────────────────────────────
const RGT = /*__RGT_DATA__*/[];
const PLOT_GRIDS = /*__RGT_PLOTS__*/{};

// ── Colour helpers ───────────────────────────────────────────────────────────
function gainHex(g) {
  if (g === null || g === undefined) return '#546e7a';
  if (g >= 20)  return '#1b5e20';
  if (g >= 10)  return '#2e7d32';
  if (g >=  5)  return '#388e3c';
  if (g >=  0)  return '#66bb6a';
  if (g >= -5)  return '#ef9a9a';
  if (g >= -10) return '#e53935';
  return '#b71c1c';
}
function gainBg(g) {
  if (g === null) return 'rgba(255,255,255,.05)';
  if (g >= 20)  return 'rgba(27,94,32,.85)';
  if (g >= 10)  return 'rgba(46,125,50,.75)';
  if (g >=  5)  return 'rgba(56,142,60,.65)';
  if (g >=  0)  return 'rgba(102,187,106,.35)';
  if (g >= -5)  return 'rgba(239,154,154,.4)';
  if (g >= -10) return 'rgba(229,57,53,.7)';
  return 'rgba(183,28,28,.85)';
}
function gainCls(g, stars) {
  if (g === null) return 'gns';
  if (!stars) return 'gns';
  return g >= 0 ? 'gpos' : 'gneg';
}
function fmtG(g, stars) {
  if (g === null || g === undefined) return '—';
  return (g >= 0 ? '+' : '') + g.toFixed(1) + '%' + (stars || '');
}

// ── Custom teardrop pin ───────────────────────────────────────────────────────
function makePin(color, label, glow, idx, standout, name) {
  const gid = 'pg' + Math.random().toString(36).slice(2);
  const glowStyle = glow ? `filter:drop-shadow(0 1px 2px rgba(0,0,0,.55))` : '';
  const ring = standout ? `<span class="pin-pulse" style="--c:${color}"></span>` : '';
  const svg = `<svg width="28" height="36" viewBox="0 0 28 36" xmlns="http://www.w3.org/2000/svg" style="${glowStyle}">
    <defs>
      <radialGradient id="${gid}" cx="38%" cy="30%" r="70%">
        <stop offset="0%" stop-color="${lighten(color)}"/>
        <stop offset="100%" stop-color="${color}"/>
      </radialGradient>
    </defs>
    <path d="M14 1C7.4 1 2 6.4 2 13C2 22 14 35 14 35C14 35 26 22 26 13C26 6.4 20.6 1 14 1Z"
          fill="url(#${gid})" stroke="rgba(255,255,255,.65)" stroke-width="1.2"/>
    <circle cx="14" cy="13" r="7.4" fill="rgba(255,255,255,.16)"/>
    <text x="14" y="16" text-anchor="middle" fill="white"
          font-size="7" font-weight="800" font-family="Inter,sans-serif"
          style="text-shadow:0 1px 2px rgba(0,0,0,.55)">${label}</text>
  </svg>`;
  const tag = name ? `<span class="pin-label">${name}</span>` : '';
  const html = `<div class="rgt-pin staggered" style="--i:${idx || 0}">${ring}${svg}${tag}</div>`;
  return L.divIcon({
    className: '', html: html,
    iconSize: [28, 36], iconAnchor: [14, 35], popupAnchor: [0, -38],
  });
}
function lighten(hex) {
  // lighten hex colour slightly for gradient top
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, ((n >> 16) & 0xff) + 50);
  const g = Math.min(255, ((n >>  8) & 0xff) + 50);
  const b = Math.min(255, ( n        & 0xff) + 50);
  return '#' + [r,g,b].map(x=>x.toString(16).padStart(2,'0')).join('');
}
function pinLabel(g) {
  if (g === null) return '?';
  return (g >= 0 ? '+' : '') + Math.round(g) + '%';
}

// ── Map ──────────────────────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: false, attributionControl: false,
                           maxZoom: 21, minZoom: 2 });

// Imagery basemaps (free, no API key). Default = Esri World Imagery — always the
// latest available, sub-metre. The "Imagery" control (top-left) also offers Esri
// Wayback: immutable, exactly-dated archive snapshots, so you can compare a site
// before vs after harvest with a date you can trust.
const ESRI_IMAGERY = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const ESRI_META    = 'https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer';
const WAYBACK_TILE = 'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{rel}/{z}/{y}/{x}';

// Embedded FALLBACK list (used only if the live Wayback index can't be fetched).
// The live fetch (loadWaybackIndex) is the normal path and auto-discovers new
// Esri releases. meta = that version's metadata service.
const WAYBACK_FALLBACK = [
  {date:'2026-05-28',rel:'10842',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2026_r05/MapServer'},
  {date:'2025-12-18',rel:'13192',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2025_r12/MapServer'},
  {date:'2024-12-12',rel:'16453',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2024_r13/MapServer'},
  {date:'2023-12-07',rel:'56102',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2023_r11/MapServer'},
  {date:'2022-12-14',rel:'45134',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2022_r15/MapServer'},
  {date:'2021-12-21',rel:'26120',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2021_r17/MapServer'},
  {date:'2020-12-16',rel:'29260',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2020_r16/MapServer'},
  {date:'2019-12-12',rel:'4756',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2019_r16/MapServer'},
  {date:'2018-11-29',rel:'239',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2018_r16/MapServer'},
  {date:'2017-07-14',rel:'3319',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2017_r13/MapServer'},
  {date:'2016-12-07',rel:'6678',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2016_r21/MapServer'},
  {date:'2015-09-30',rel:'3630',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2015_r16/MapServer'},
  {date:'2014-12-30',rel:'5844',meta:'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2014_r21/MapServer'},
];

const baseEsri = L.tileLayer(ESRI_IMAGERY, { maxZoom: 21, maxNativeZoom: 19 });
baseEsri.setZIndex(0);
baseEsri.addTo(map);

// Place / boundary labels, kept above the imagery and toggleable.
const labels = L.tileLayer(
  'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 21, maxNativeZoom: 19, opacity: 0.75 });
labels.setZIndex(10);
labels.addTo(map);

// Active-base bookkeeping (drives the footnote's live date lookup).
var currentBase    = baseEsri;
var currentMetaUrl = ESRI_META;
var currentLabel   = 'Esri World Imagery';
var currentSub     = 'latest · ≤ 1 m';

function setBasemap(kind, rel, meta, dateLabel) {
  if (currentBase) map.removeLayer(currentBase);
  if (kind === 'wayback') {
    currentBase    = L.tileLayer(WAYBACK_TILE.replace('{rel}', rel), { maxZoom: 21, maxNativeZoom: 19 });
    currentMetaUrl = meta;
    currentLabel   = 'Esri Wayback';
    currentSub     = 'snapshot ' + dateLabel + ' · ≤ 1 m';
  } else {
    currentBase    = baseEsri;
    currentMetaUrl = ESRI_META;
    currentLabel   = 'Esri World Imagery';
    currentSub     = 'latest · ≤ 1 m';
  }
  currentBase.setZIndex(0);
  currentBase.addTo(map);
  renderBaseInfo('');
  fetchMeta();
}


L.control.zoom({ position: 'topleft' }).addTo(map);
L.control.attribution({ position: 'bottomleft',
  prefix: 'Leaflet &nbsp;·&nbsp; IFC RGT' }).addTo(map);

// ── Info panel ────────────────────────────────────────────────────────────────
function closePanel() {
  document.getElementById('panel').classList.remove('open');
}

// small inline 2-line plot: year on x, Improved vs Woods Run means.
// Has a labelled y-axis (min/max + gridlines) and every point carries a native
// hover/touch tooltip ("Improved · Y2: 23.0 cm") so values are always readable.
function miniPlot(title, unit, years, woods, imp) {
  const W = 212, H = 92, padL = 30, padR = 8, padT = 16, padB = 18;
  const all = woods.concat(imp).filter(v => v !== null && v !== undefined && !isNaN(v));
  if (!all.length) return '';
  let mn = Math.min.apply(null, all), mx = Math.max.apply(null, all);
  if (mn === mx) { mn -= 1; mx += 1; }
  const pad = (mx - mn) * 0.12;
  const allNonNeg = all.every(v => v >= 0);
  mn = allNonNeg ? Math.max(0, mn - pad) : mn - pad;        // never dip below 0 for positive data
  mx += pad;                                                // headroom on top
  const n = years.length;
  const xx = i => padL + (n <= 1 ? (W - padL - padR) / 2 : i * (W - padL - padR) / (n - 1));
  const yy = v => padT + (H - padT - padB) * (1 - (v - mn) / (mx - mn));
  const fmt = v => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));
  // y-axis: min / mid / max gridlines + labels
  let axis = '';
  [mn, (mn + mx) / 2, mx].forEach(function (v) {
    const y = yy(v).toFixed(1);
    axis += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y +
            '" stroke="rgba(255,255,255,.10)" stroke-width="1"/>' +
            '<text x="' + (padL - 4) + '" y="' + (parseFloat(y) + 3) +
            '" text-anchor="end" font-size="8" fill="rgba(255,255,255,.55)">' + fmt(v) + '</text>';
  });
  function line(arr, color, name) {
    let d = '', dots = '';
    for (let i = 0; i < n; i++) {
      const v = arr[i];
      if (v === null || v === undefined || isNaN(v)) continue;
      const cx = xx(i).toFixed(1), cy = yy(v).toFixed(1);
      d += (d ? ' L' : 'M') + cx + ',' + cy;
      const yl = String(years[i]).replace('Year', 'Y');
      // visible dot + a larger transparent hit-area carrying the tooltip
      dots += '<circle cx="' + cx + '" cy="' + cy + '" r="2.6" fill="' + color + '"/>' +
              '<circle cx="' + cx + '" cy="' + cy + '" r="9" fill="transparent" style="cursor:pointer">' +
              '<title>' + name + ' · ' + yl + ': ' + fmt(v) + (unit ? ' ' + unit : '') + '</title></circle>';
    }
    return (d ? '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' : '') + dots;
  }
  let xlab = '';
  for (let i = 0; i < n; i++) {
    xlab += '<text x="' + xx(i).toFixed(1) + '" y="' + (H - 4) + '" text-anchor="middle" font-size="8" fill="rgba(255,255,255,.45)">' + String(years[i]).replace('Year', 'Y') + '</text>';
  }
  return '<div class="mini"><div class="mini-h">' + title + (unit ? ' <span>(' + unit + ')</span>' : '') + '</div>' +
         '<svg viewBox="0 0 ' + W + ' ' + H + '" class="mini-svg">' + axis +
         line(woods, '#6fb5d8', 'Woods Run') + line(imp, '#f0a93a', 'Improved') + xlab + '</svg></div>';
}

function openPanel(loc) {
  const csv   = loc.csv || [];
  const isInW = loc.region === 'INW';
  // Headline = latest-year VOLUME realized gain (the standard gain metric),
  // not an average across metrics.
  let volG = null, volYr = null, volStars = '';
  (csv || []).forEach(function (cn) {
    const cg = (loc.gains || {})[cn] || {};
    Object.keys(cg).sort().forEach(function (yr) {
      const d = (cg[yr] || {})['Volume'];
      if (d && d.gain_pct !== null && d.gain_pct !== undefined) {
        volG = d.gain_pct; volYr = yr; volStars = (d.stars && d.stars !== 'ns') ? d.stars : '';
      }
    });
  });
  const g     = (volG !== null) ? volG : loc.avg_gain;
  const gCls  = g === null ? 'gns' : (g >= 0 ? 'gpos' : 'gneg');
  const gTxt  = g === null ? 'No data'
              : ((g >= 0 ? '+' : '') + g.toFixed(1) + '%' + (volG !== null ? volStars : ''));
  const gLbl  = (volG !== null) ? ('Volume gain \u00b7 ' + String(volYr).replace('Year', 'Yr '))
                                : 'Avg. realized gain';

  // Site type badges
  const hasCore = csv.some(n => !n.includes('TRANSFER') && !n.includes('TRAN'));
  const hasXfer = csv.some(n =>  n.includes('TRANSFER') ||  n.includes('TRAN'));
  let badges = isInW
    ? '<span class="pb pb-inw">INW</span>'
    : '<span class="pb pb-ks">K-S</span>';
  if (csv.length === 0) badges += '<span class="pb pb-nd">No trial data</span>';
  if (hasCore) badges += '<span class="pb pb-core">Core</span>';
  if (hasXfer) badges += '<span class="pb pb-xfer">Transfer</span>';

  // Count measurement years
  let nYears = loc.n_years || 0;
  if (!nYears && csv.length > 0) {
    const firstCsv = loc.gains[csv[0]] || {};
    nYears = Object.values(firstCsv).filter(yr => Object.keys(yr).length > 0).length;
  }

  // Header
  document.getElementById('ph').innerHTML = `
    <div class="ph-top">
      <div class="ph-name">${loc.name}</div>
      <button class="ph-close" onclick="closePanel()">&#x2715;</button>
    </div>
    <div class="ph-badges">${badges}</div>
    <div class="ph-gain">
      <div>
        <div class="ph-gain-lbl">${gLbl}</div>
      </div>
      <div class="ph-gain-val ${gCls}">${gTxt}</div>
    </div>
    <div class="ph-meta">
      <div class="ph-meta-item">
        <div class="ph-meta-val">${nYears || '—'}</div>
        <div class="ph-meta-lbl">Meas. Years</div>
      </div>
      <div class="ph-meta-item">
        <div class="ph-meta-val">${csv.length || '—'}</div>
        <div class="ph-meta-lbl">Trial Sites</div>
      </div>
      <div class="ph-meta-item">
        <div class="ph-meta-val">${loc.region}</div>
        <div class="ph-meta-lbl">Region</div>
      </div>
    </div>`;

  // Body
  let body = '';

  if (csv.length === 0) {
    body = '<div class="nodata">This location is not yet in the trial dataset.</div>';
  } else {
    for (const cn of csv) {
      const cg = loc.gains[cn] || {};
      const years = Object.keys(cg).sort();
      if (!years.length) continue;
      const isXfer = cn.includes('TRANSFER') || cn.includes('TRAN');
      body += `<div class="sec">${isXfer ? 'Transfer' : 'Core'} site — ${cn}</div>`;

      // Collect metrics present
      const allM = new Set();
      years.forEach(yr => Object.keys(cg[yr] || {}).forEach(m => allM.add(m)));
      const mList = ['Caliper','Height','Volume'].filter(m => allM.has(m));
      if (!mList.length) continue;

      // legend: Woods Run vs Improved (means by year)
      body += '<div class="mini-legend">' +
              '<span><i style="background:#6fb5d8"></i>Woods Run</span>' +
              '<span><i style="background:#f0a93a"></i>Improved</span>' +
              '<span class="ml-x">mean by year</span></div>';

      // one small 2-line plot per metric (year on x; Improved vs Woods Run mean)
      let lastYrMort = null, lastYrMortYear = null;
      body += '<div class="minis">';
      mList.forEach(function (m) {
        const woodsArr = [], impArr = []; let unit = '', has = false;
        years.forEach(function (yr) {
          const d = (cg[yr] || {})[m];
          if (d) {
            woodsArr.push(d.woods_mean); impArr.push(d.imp_mean);
            if (d.unit) unit = d.unit;
            if (d.woods_mean != null || d.imp_mean != null) has = true;
            lastYrMort = d; lastYrMortYear = yr;   // latest year that actually has data
          } else { woodsArr.push(null); impArr.push(null); }
        });
        if (has) body += miniPlot(m, unit, years, woodsArr, impArr);
      });
      body += '</div>';

      // Mortality
      if (lastYrMort && (lastYrMort.imp_mort !== null || lastYrMort.woods_mort !== null)) {
        const lastYr = lastYrMortYear || years[years.length - 1];
        const wm = lastYrMort.woods_mort !== null ? lastYrMort.woods_mort.toFixed(1)+'%' : '—';
        const im = lastYrMort.imp_mort   !== null ? lastYrMort.imp_mort.toFixed(1)+'%'   : '—';
        body += `<div class="mort">Mortality (${lastYr}) &nbsp;·&nbsp;
          <strong>Woods Run:</strong> ${wm} &nbsp;
          <strong>Improved:</strong> ${im}</div>`;
      }

      // Explore button
      if (csv.length > 0) {
        const primary = csv[0];
        const region  = loc.region;
        body += `<button class="explore-btn" onclick="selectInst('${primary}','${region}')">
                   Explore in Dashboard &rarr;
                 </button>`;
      }
    }
  }

  document.getElementById('pb-body').innerHTML = body;
  document.getElementById('panel').classList.add('open');
}

// ── Markers ───────────────────────────────────────────────────────────────────
let allLayers = [];

function addMarkers() {
  RGT.forEach(function(loc, i) {
    const gv = (loc.vol_gain !== undefined && loc.vol_gain !== null) ? loc.vol_gain : loc.avg_gain;
    const color = gainHex(gv);
    const label = pinLabel(gv);
    const standout = (gv !== null && gv !== undefined && gv >= 15);
    const icon  = makePin(color, label, true, i, standout, loc.name);
    const m = L.marker([loc.lat, loc.lon], { icon });
    m.on('click', function() {
      openPanel(loc);
      // Auto-fly to the installation so its 6 plots come into view (Google-Earth feel).
      map.flyTo([loc.lat, loc.lon], 16.5, { duration: 1.6, easeLinearity: 0.2 });
    });
    m.addTo(map);
    allLayers.push({ marker: m, region: loc.region });
  });
}

// ── Region filter ──────────────────────────────────────────────────────────────
// ── Plot-grid overlay (6 plots per installation) ────────────────────
let plotLayer = null;
let plotsEnabled = true;
let currentRegion = 'ALL';
const PLOT_MIN_ZOOM  = 12;   // polygons appear at/above this zoom
const LABEL_MIN_ZOOM = 15;   // IMP/WR labels appear at/above this zoom

// Outline-only plots: NO fill, so the satellite imagery shows through and people
// can actually see the trees. Bright orange (Improved) / cyan-blue (Woods Run)
// borders read clearly on top of dark canopy.
function plotStyle(f) {
  const imp = f.properties.type === 'IMP';
  const c = imp ? '#FFB74D' : '#4FC3F7';
  return {
    color:       c,
    weight:      2.4,
    opacity:     1,
    fill:        true,        // keep a fill target for easy clicking/hover…
    fillColor:   c,
    fillOpacity: 0,           // …but invisible until hovered
  };
}

function initPlots() {
  if (!PLOT_GRIDS || !PLOT_GRIDS.features || !PLOT_GRIDS.features.length) return;
  plotLayer = L.geoJSON(PLOT_GRIDS, {
    style: plotStyle,
    onEachFeature: function(f, layer) {
      const p   = f.properties;
      const imp = p.type === 'IMP';
      const src = imp ? 'Improved' : 'Woods Run';
      layer._region = p.region;
      layer.bindTooltip(p.plot, {
        permanent: true, direction: 'center', className: 'plot-label', opacity: 1,
      });
      const area = (p.area_m2 != null) ? Math.round(p.area_m2).toLocaleString() : '—';
      layer.bindPopup(
        '<div class="pp-name">' + p.plot + '</div>' +
        '<div class="pp-inst">' + p.inst + '</div>' +
        '<span class="pp-tag ' + (imp ? 'pp-imp' : 'pp-wr') + '">' + src + '</span>' +
        '<div class="pp-area">Plot area &asymp; ' + area + ' m&sup2;</div>',
        { closeButton: true, autoPan: false }
      );
      layer.on('mouseover', function() { this.setStyle({ weight: 3.4, fillOpacity: 0.18 }); });
      layer.on('mouseout',  function() { this.setStyle(plotStyle(f)); });
    },
  });
  map.on('zoomend', updatePlots);
  updatePlots();
}

function updatePlots() {
  if (!plotLayer) return;
  const z    = map.getZoom();
  const show = plotsEnabled && z >= PLOT_MIN_ZOOM;
  var mapEl = document.getElementById('map');
  if (mapEl) mapEl.classList.toggle('zoomed-in', z >= LABEL_MIN_ZOOM);

  if (show && !map.hasLayer(plotLayer))  plotLayer.addTo(map);
  if (!show && map.hasLayer(plotLayer))  map.removeLayer(plotLayer);

  if (show) {
    plotLayer.eachLayer(function(l) {
      const visible = (currentRegion === 'ALL' || l._region === currentRegion);
      const el = l.getElement && l.getElement();
      if (el) el.style.display = visible ? '' : 'none';
      if (visible && z >= LABEL_MIN_ZOOM) l.openTooltip();
      else l.closeTooltip();
    });
  }

}

function togglePlots() {
  plotsEnabled = !plotsEnabled;
  document.getElementById('plotToggle').classList.toggle('on', plotsEnabled);
  updatePlots();
}

// ── Region filter ───────────────────────────────────────────
function filterRegion(r) {
  currentRegion = r;
  document.querySelectorAll('.chip').forEach(el => el.classList.remove('active'));
  const sel = r === 'ALL' ? '.chip-all' : (r === 'INW' ? '.chip-inw' : '.chip-ks');
  document.querySelector(sel).classList.add('active');

  allLayers.forEach(function(l) {
    if (r === 'ALL' || l.region === r) map.addLayer(l.marker);
    else map.removeLayer(l.marker);
  });

  closePanel();
  if      (r === 'INW') map.flyTo([46.8, -117.0], 7.5, { duration: 1.2 });
  else if (r === 'K-S') map.flyTo([42.5, -122.5], 8.5, { duration: 1.2 });
  else fitAll();
  updatePlots();
}

// Frame ALL trial sites (both regions) so nothing is off-screen by default.
function fitAll() {
  var pts = allLayers
    .filter(function (l) { return map.hasLayer(l.marker); })
    .map(function (l) { return l.marker.getLatLng(); });
  if (!pts.length) { map.flyTo([45.0, -119.0], 6.2, { duration: 1.0 }); return; }
  var b = L.latLngBounds(pts).pad(0.18);
  if (map.flyToBounds) map.flyToBounds(b, { duration: 1.1, maxZoom: 8, padding: [36, 36] });
  else map.fitBounds(b, { maxZoom: 8, padding: [36, 36] });
}

// Close panel when clicking the map background
map.on('click', function() { closePanel(); });

// ── Dash bridge ───────────────────────────────────────────────────────────────
function selectInst(csvName, region) {
  try { window.parent._rgt_selected = { installation: csvName, region: region, _ts: Date.now() }; }
  catch(e) {}
  closePanel();
}

// ── Boot: reveal + camera + basemap footnote (runs last, all defs ready) ──────
// ── Reveal chrome (chips + legend). No splash overlay — map shows at once. ────
function showChrome() {
  var ch = document.getElementById('chips'); if (ch) ch.classList.add('on');
  var lg = document.getElementById('legend'); if (lg) lg.classList.add('on');
}
function hideIntro() { showChrome(); }            // kept for error/failsafe hooks
window.onerror = function() { showChrome(); return false; };

// ── Google-Earth style reveal — visible from frame 1, then glides into the PNW ─
map.setView([39.5, -109.0], 4, { animate: false });   // western-US overview, instant
addMarkers();
initPlots();
showChrome();
setTimeout(function () { map.flyTo([45.2, -119.5], 6.2, { duration: 2.2, easeLinearity: 0.2 }); }, 450);
setTimeout(function () { fitAll(); }, 2900);          // settle framing BOTH regions (PNW)

// ── Basemap source footnote ──────────────────────────────────────────────────
// Shows the active source and — best-effort — the TRUE per-location capture date
// from that exact layer's metadata service (the same data Esri's own viewer uses).
// For Wayback this queries the chosen version's metadata, so the date is honest
// even when an older snapshot is selected.
function renderBaseInfo(extra) {
  // Source/date now lives compactly inside the slider (tb-meta), not a separate
  // footnote. Shows the live capture info when available, else the static sub.
  var el = document.getElementById('tb-meta');
  if (!el) return;
  el.textContent = extra ? extra : currentSub;
}
var _bmReq = 0;
function fetchMeta() {
  var myReq = ++_bmReq;
  try {
    var c = map.getCenter();
    var b = map.getBounds();
    var ext = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(',');
    var params = new URLSearchParams({
      f: 'json',
      geometry: JSON.stringify({ x: c.lng, y: c.lat }),
      geometryType: 'esriGeometryPoint', sr: '4326', layers: 'all',
      tolerance: '1', mapExtent: ext, imageDisplay: '800,600,96',
      returnGeometry: 'false',
    });
    var url = currentMetaUrl + '/identify?' + params.toString();
    var ctl = new AbortController();
    var to = setTimeout(function () { ctl.abort(); }, 5000);
    fetch(url, { signal: ctl.signal })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        clearTimeout(to);
        if (myReq !== _bmReq) return;          // a newer request superseded this
        var out = parseEsriMeta(j);
        if (out) renderBaseInfo(out);
      })
      .catch(function () { clearTimeout(to); });
  } catch (e) {}
}
function parseEsriMeta(j) {
  if (!j || !j.results || !j.results.length) return '';
  for (var i = 0; i < j.results.length; i++) {
    var a = j.results[i].attributes || {};
    var date = '', res = '', src = '';
    for (var k in a) {
      var v = a[k]; var kl = k.toLowerCase();
      var vs = (v === null || v === undefined) ? '' : String(v);
      if (!vs || vs.toLowerCase() === 'null') continue;
      if (!date && /date/.test(kl)) date = vs;
      if (!res  && /(^|_)res/.test(kl) && parseFloat(vs) > 0) res = vs;
      if (!src  && /desc/.test(kl)) src = vs;
    }
    if (date || res) {
      var s = src ? src.split(',')[0] : 'imagery';
      if (date) s += ' · ' + fmtDate(date);
      if (res)  s += ' · ' + res + (/\d$/.test(res) ? ' m' : '');
      return s;
    }
  }
  return '';
}
function fmtDate(d) {
  var n = Number(d);
  if (!isNaN(n)) {
    if (n > 1e11) { try { return new Date(n).toISOString().slice(0, 10); } catch (e) {} }
    var s = String(d);
    if (s.length === 8) return s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8);
    if (s.length === 4) return s;
  }
  return String(d);
}
var _bmMove = null;
map.on('moveend', function () {
  clearTimeout(_bmMove);
  _bmMove = setTimeout(fetchMeta, 650);
});

// ── Imagery time slider (bottom) ─────────────────────────────────────────────
// Built LIVE from Esri's official Wayback release index, so when Esri publishes
// new imagery the slider gains it automatically — nothing to hand-edit. Falls
// back to the embedded list only if the index can't be fetched (offline/blocked).
var WAYBACK_CONFIG_URL = 'https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json';
var STOPS = [];

// From a flat [{date,rel,meta}] list, keep >= 2020 and take the newest release
// per year; the most-recent year becomes "Latest" (always-current live imagery).
function buildStops(list) {
  var byYear = {};
  list.forEach(function (w) {
    if (!w.date || w.date < '2020-01-01') return;
    var y = w.date.slice(0, 4);
    if (!byYear[y] || w.date > byYear[y].date) byYear[y] = w;
  });
  var years = Object.keys(byYear).sort();
  if (!years.length) return [];
  var maxYear = years[years.length - 1];
  var stops = [];
  years.forEach(function (y) {
    if (y === maxYear) {
      stops.push({ label: 'Latest', kind: 'latest', date: '' });
    } else {
      var w = byYear[y];
      stops.push({ label: y, kind: 'wayback', rel: w.rel, meta: w.meta, date: w.date });
    }
  });
  return stops;
}

function applyStop(idx) {
  var s = STOPS[idx];
  if (!s) return;
  var v = document.getElementById('tb-val');
  if (v) v.textContent = s.kind === 'latest' ? 'Latest' : s.date;
  if (s.kind === 'latest') setBasemap('latest');
  else setBasemap('wayback', s.rel, s.meta, s.date);
}

function initTimebar(stops) {
  STOPS = stops;
  var wrap = document.getElementById('timebar');
  if (!wrap) return;
  if (!stops.length) { wrap.style.display = 'none'; return; }
  var maxIdx = stops.length - 1;
  var ticks = stops.map(function (s) { return '<span>' + s.label + '</span>'; }).join('');
  wrap.innerHTML =
    '<div class="tb-head"><span class="tb-lbl">Imagery</span>' +
    '<span class="tb-val" id="tb-val">Latest</span>' +
    '<span class="tb-meta" id="tb-meta"></span>' +
    '<label class="tb-chk"><input type="checkbox" id="tb-labels" checked> Labels</label></div>' +
    '<input type="range" id="tb-range" min="0" max="' + maxIdx + '" step="1" value="' + maxIdx + '" ' +
    'aria-label="Imagery date">' +
    '<div class="tb-ticks">' + ticks + '</div>';
  var range = document.getElementById('tb-range');
  range.addEventListener('input', function () { applyStop(+this.value); });
  var lc = document.getElementById('tb-labels');
  if (lc) lc.addEventListener('change', function () {
    if (this.checked) { labels.addTo(map); labels.setZIndex(10); } else { map.removeLayer(labels); }
  });
  applyStop(maxIdx);   // default = Latest (rightmost)
}

function loadWaybackIndex() {
  var ctl = new AbortController();
  var to = setTimeout(function () { ctl.abort(); }, 6000);
  fetch(WAYBACK_CONFIG_URL, { signal: ctl.signal })
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      clearTimeout(to);
      var list = [];
      for (var rel in cfg) {
        var it = cfg[rel];
        if (!it) continue;
        var m = /(\d{4}-\d{2}-\d{2})/.exec(it.itemTitle || '');
        if (!m) continue;
        list.push({ date: m[1], rel: rel, meta: it.metadataLayerUrl || '' });
      }
      var stops = buildStops(list);
      initTimebar(stops.length ? stops : buildStops(WAYBACK_FALLBACK));
    })
    .catch(function () {
      clearTimeout(to);
      initTimebar(buildStops(WAYBACK_FALLBACK));   // offline / blocked -> embedded
    });
}

// Initialise the footnote + the live imagery time slider.
renderBaseInfo('');
fetchMeta();
loadWaybackIndex();
</script>
</body>
</html>"""
