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
    # INW — Idaho / Washington
    {"name": "Hoodoo Saddle",    "lat": 48.036259, "lon": -116.911796, "region": "INW",
     "csv": ["HOODOO"]},
    {"name": "Lost Fromelt",     "lat": 46.442957, "lon": -115.802066, "region": "INW",
     "csv": ["LOST FROMELT"]},
    {"name": "Silver Spur",      "lat": 46.667659, "lon": -116.312500, "region": "INW",
     "csv": ["SILVER SPUR"]},
    {"name": "Wild Turkey",      "lat": 48.791146, "lon": -117.728751, "region": "INW",
     "csv": ["WILD TURKEY"]},
    {"name": "Sherry Ridge",     "lat": 48.595805, "lon": -117.507050, "region": "INW",
     "csv": ["SHERRY CORE", "SHERRY TRANSFER"]},
    {"name": "Sitka",            "lat": 45.523972, "lon": -118.464741, "region": "INW",
     "csv": ["SITKA CORE", "SITKA TRAN"]},
    {"name": "Casa",             "lat": 45.826292, "lon": -117.725293, "region": "INW",
     "csv": ["CASA"]},
    {"name": "Dawson's Delight", "lat": 48.769104, "lon": -116.248716, "region": "INW",
     "csv": ["DAWSON"]},
    {"name": "Gold View",        "lat": 46.997424, "lon": -116.158962, "region": "INW",
     "csv": ["GOLDVIEW"]},
    {"name": "Carscallen",       "lat": 47.029834, "lon": -116.852607, "region": "INW",
     "csv": ["CARSCALLEN CORE", "CARSCALLEN TRANSFER"]},
    # K-S — Southern Oregon
    {"name": "Boundary North",   "lat": 42.703366, "lon": -122.378000, "region": "K-S",
     "csv": []},
    {"name": "Plan D",           "lat": 42.705716, "lon": -122.489000, "region": "K-S",
     "csv": ["PLAN D #1"]},
    {"name": "Lodgepole 1",      "lat": 42.622810, "lon": -122.434157, "region": "K-S",
     "csv": ["LODGEPOLE 1"]},
    {"name": "Lodgepole 2",      "lat": 42.600529, "lon": -122.427773, "region": "K-S",
     "csv": ["LODGEPOLE 2"]},
    {"name": "Rum Creek",        "lat": 42.599829, "lon": -123.646192, "region": "K-S",
     "csv": []},
    {"name": "Lickity Split",    "lat": 42.141993, "lon": -122.921986, "region": "K-S",
     "csv": []},
    {"name": "Big Butte",        "lat": 42.551133, "lon": -122.539295, "region": "K-S",
     "csv": []},
    {"name": "Fish Hatchery",    "lat": 42.535643, "lon": -122.540495, "region": "K-S",
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
        return [dict(loc, gains={}, avg_gain=None) for loc in LOCATIONS if loc.get("csv")]

    metrics = list(store.metrics())
    years   = list(store.years())

    result = []
    for loc in LOCATIONS:
        if not loc.get("csv"):
            continue  # no trial data at this location -> no pin on the map
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
        result.append(entry)

    return result


def generate_map_html(store) -> None:
    """Build assets/installations_map.html with embedded KPI data."""
    try:
        data = build_map_data(store)
    except Exception:
        traceback.print_exc()
        data = [dict(loc, gains={}, avg_gain=None, n_years=0) for loc in LOCATIONS if loc.get("csv")]

    json_blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html_text = _TEMPLATE.replace("/*__RGT_DATA__*/[]", json_blob)

    out = config.ASSETS_DIR / "installations_map.html"
    out.write_text(html_text, encoding="utf-8")
    print(f"[map_builder] Written {out}  ({len(data)} installations)")


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
#legend{position:absolute;left:14px;bottom:16px;z-index:9400;
  background:rgba(10,20,36,.86);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border:1px solid rgba(219,168,0,.2);border-radius:14px;padding:11px 13px;color:#fff;
  font-size:11px;box-shadow:0 12px 44px rgba(0,0,0,.55);max-width:236px;
  opacity:0;transform:translateY(8px);transition:opacity .5s ease,transform .5s ease;}
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

<!-- Intro splash -->
<div id="intro">
  <div class="i-badge">Intermountain Forestry Cooperative</div>
  <div class="i-title">RGT Installation Map</div>
  <div class="i-sub">Realized Genetic Gain Trials &nbsp;·&nbsp; Pacific Northwest</div>
  <div class="i-dots"><span></span><span></span><span></span></div>
</div>

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
  <div class="lg-title">Avg. realized gain</div>
  <div class="lg-scale">
    <i style="background:#b71c1c"></i><i style="background:#e53935"></i><i style="background:#ef9a9a"></i><i style="background:#66bb6a"></i><i style="background:#388e3c"></i><i style="background:#2e7d32"></i><i style="background:#1b5e20"></i>
  </div>
  <div class="lg-ends"><span>&minus;10%</span><span>0</span><span>+20%</span></div>
  <div class="lg-note">Pulsing pins mark standout sites (avg gain &ge; 15%).</div>
</div>

<!-- Info panel -->
<div id="panel">
  <div class="ph" id="ph"></div>
  <div class="pb-body" id="pb-body"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ── Data ────────────────────────────────────────────────────────────────────
const RGT = /*__RGT_DATA__*/[];

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

// ESRI World Imagery — highest-resolution free satellite basemap (no API key).
// maxNativeZoom 19 = real tiles; the map can over-zoom to 21 for a closer look.
L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 21, maxNativeZoom: 19 }).addTo(map);
L.tileLayer(
  'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 21, maxNativeZoom: 19, opacity: 0.75 }).addTo(map);

L.control.zoom({ position: 'topleft' }).addTo(map);
L.control.attribution({ position: 'bottomleft',
  prefix: 'ESRI World Imagery &nbsp;·&nbsp; Leaflet &nbsp;·&nbsp; IFC RGT' }).addTo(map);

// ── Failsafe ──────────────────────────────────────────────────────────────────
function hideIntro() {
  const el = document.getElementById('intro');
  if (el) { el.classList.add('fade'); setTimeout(function(){ el.style.display='none'; }, 1000); }
  document.getElementById('chips').classList.add('on');
  var lg = document.getElementById('legend'); if (lg) lg.classList.add('on');
}
window.onerror = function() { hideIntro(); return false; };
setTimeout(hideIntro, 12000);

// ── Google-Earth zoom ─────────────────────────────────────────────────────────
map.setView([35, -100], 3, { animate: false });
setTimeout(() => map.flyTo([44.5, -112], 5.0, { duration: 2.0, easeLinearity: 0.18 }), 700);
setTimeout(() => map.flyTo([46.0, -119.5], 7.1, { duration: 1.7, easeLinearity: 0.2 }), 3500);
setTimeout(() => { hideIntro(); addMarkers(); }, 5900);
setTimeout(() => { fitAll(); }, 6400);   // default view frames BOTH regions

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
  const g     = loc.avg_gain;
  const gCls  = g === null ? 'gns' : (g >= 0 ? 'gpos' : 'gneg');
  const gTxt  = g === null ? 'No data' : ((g >= 0 ? '+' : '') + g.toFixed(1) + '%');

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
        <div class="ph-gain-lbl">Avg. Realized Gain</div>
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
      let lastYrMort = null;
      body += '<div class="minis">';
      mList.forEach(function (m) {
        const woodsArr = [], impArr = []; let unit = '', has = false;
        years.forEach(function (yr) {
          const d = (cg[yr] || {})[m];
          if (d) {
            woodsArr.push(d.woods_mean); impArr.push(d.imp_mean);
            if (d.unit) unit = d.unit;
            if (d.woods_mean != null || d.imp_mean != null) has = true;
            lastYrMort = d;   // ends on the latest year with data
          } else { woodsArr.push(null); impArr.push(null); }
        });
        if (has) body += miniPlot(m, unit, years, woodsArr, impArr);
      });
      body += '</div>';

      // Mortality
      if (lastYrMort && (lastYrMort.imp_mort !== null || lastYrMort.woods_mort !== null)) {
        const lastYr = years[years.length - 1];
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
    const color = gainHex(loc.avg_gain);
    const label = pinLabel(loc.avg_gain);
    const standout = (loc.avg_gain !== null && loc.avg_gain !== undefined && loc.avg_gain >= 15);
    const icon  = makePin(color, label, true, i, standout, loc.name);
    const m = L.marker([loc.lat, loc.lon], { icon });
    m.on('click', function() { openPanel(loc); });
    m.addTo(map);
    allLayers.push({ marker: m, region: loc.region });
  });
}

// ── Region filter ──────────────────────────────────────────────────────────────
function filterRegion(r) {
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
</script>
</body>
</html>"""
