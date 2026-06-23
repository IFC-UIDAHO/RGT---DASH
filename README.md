# IFC Realized Genetic Gain Trials — Dashboard

A Plotly **Dash** application for the Intermountain Forestry Cooperative
(University of Idaho) comparing genetically **Improved** vs **Woods Run**
Douglas-fir seedlots across installations in two regions (Inland Northwest · INW,
and Klamath–Siskiyou · K-S), relating realized genetic gain to site growth — with
an LLM **ForestAsk** report assistant powered by MindRouter.

**Live:** https://ifc.nkn.uidaho.edu/dashapp/ · **Repo:** IFC-UIDAHO/RGT---DASH ·
Python 3.10–3.14

> **Hosting/IT team — start here:** [`docs/README_HOST.md`](docs/README_HOST.md)
> is the one-page Linux server setup (clone → venv → systemd → nginx `/dashapp/`).
> Everything below is overview + how data gets updated.

---

## Run it locally (Windows, no setup)

Double-click **`RGT Dashboard.bat`** — a small menu:

```
[1] Open the dashboard on THIS computer (just me)
[2] Start / Restart the SHARED server (everyone on this PC)   ← localhost:8050 for all users
[3] Stop the shared server
[4] Make the shared server start automatically at boot (admin)
[5] Put a "RGT Dashboard" icon on the Desktop
[6] Save my changes to GitHub
[7] Update data from a new Excel (auto-watch the inbox)
```

It finds/builds a Python environment automatically. (Manual equivalent:
`python -m venv venv && venv\Scripts\pip install -r requirements.txt && python app.py`.)

Production server uses gunicorn: `gunicorn app:server -b 0.0.0.0:8050 -w 2 --timeout 300`.

> **Python 3.10–3.14 all work — nothing to configure.** Dash is pinned `<3`, and on
> **Python 3.14** that pinned Dash calls `pkgutil.find_loader()`, which 3.14 removed
> (so `python app.py` would crash with `AttributeError: module 'pkgutil' has no attribute
> 'find_loader'`). `app.py` installs a tiny built-in compatibility shim at startup to
> restore it; the shim is a no-op on 3.10–3.13. The launcher auto-builds each user's venv
> with whatever Python `py -3` finds, so this keeps every account working.

---

## Always-on shared server (Windows / Remote Desktop)

On a shared PC or Remote Desktop (several people, one machine), run the dashboard as an
always-on background server so **anyone can just click the desktop icon**
(`http://localhost:8050`) — no console window to keep open, and it survives logoff/reboot.

**Step 0 — build the shared `venv\` once (do this first).** The boot task runs as the Windows
**SYSTEM** account, and `:ENSURE_ENV` looks for a shared **`venv\`** before any per-user env.
Build it from a working, regular Python (3.10–3.14) so SYSTEM never has to compile anything:

```
cd /d E:\IFC\RGT_2026\RGT_2026\RGT_APP
venv_mjaslam\Scripts\python.exe -m venv venv      REM or any regular python.exe you have
venv\Scripts\python.exe -m pip install -r requirements.txt
```

> **Why this is required:** with no shared `venv\`, SYSTEM falls back to building its own
> `venv_<COMPUTERNAME>$` using whatever `py -3` it finds — which on this PC is a
> **free-threaded Python** that has **no SciPy wheel**, so the install dies trying to compile
> SciPy from source (needs a Fortran compiler that isn't installed). A `venv\` built from a
> regular Python avoids this, and every account (including SYSTEM) then shares it.

**Then, as an administrator:**

1. Right-click **`RGT Dashboard.bat` → Run as administrator** (admin is needed to register a boot task).
2. Press **[4]** *(Make the shared server start automatically at boot)* — registers a scheduled
   task that runs the waitress server as SYSTEM at every boot **and starts it immediately**.
3. Press **[5]** *(Put a "RGT Dashboard" icon on the Desktop)* — run as admin so the icon lands
   on the **Public** Desktop (visible to every user), not just your own.

Then every user double-clicks the icon and gets the dashboard. `localhost:8050` is correct
because every Remote Desktop user is on this same machine.

Check it's registered: `schtasks /Query /TN "RGT Dashboard"`. To stop, use menu **[3]**; to
restart, re-run **[4]** (or **[2]**). Pushing with **[6]** only updates the public web site,
not this local shared server.

---

## Updating the data (new field measurements)

The dashboard reads one file: **`data/rgt_data.csv`**. You never edit it by hand.

1. Drop the new field-data **Excel workbook** (the usual `DATA` sheet) into the
   **`data_inbox/`** folder.
2. Run **`RGT Dashboard.bat` → option [7]** (or, if the watcher service is on, it
   happens by itself).

`tools/build_dataset.py` rebuilds `rgt_data.csv` from the workbook and the dashboard
shows the new numbers after a restart. It is robust:

- **Whatever installations are in the workbook get refreshed; all others are kept.**
  So it handles INW-only, K-S-only, both, a partial file, a corrected re-export, or
  a brand-new site — without losing existing data.
- Number of measurement **years is auto-detected** (a future Year-4 just works).
- A bad/wrong-format file **fails loudly and keeps the old data** (never writes garbage).
- The processed workbook is archived into `data_inbox/processed/` with a timestamp.

**Publishing to the live site:** after updating data (or any change), run **option [6]**
to commit + push. The GitHub Action auto-deploys, so the server picks up the new
`rgt_data.csv` and restarts on its own. (The server does **not** need the Excel or the
watcher — data reaches it as the committed CSV.)

> One manual step only for a **brand-new installation**: it appears in all charts
> automatically, but it gets a **map pin** only after its GPS location + plot shapefile
> are added (`rgt_dashboard/map_builder.py` LOCATIONS + `data/plot_grids.geojson`). The
> build script names any such site so you know.

---

## Project layout

```
RGT_APP/                     ← this folder IS the git repo / deployable unit
├── app.py                   thin launcher (honors RGT_URL_PREFIX for subpath hosting)
├── requirements.txt         lean runtime deps
├── Procfile                 gunicorn start command (--timeout 300)
├── RGT Dashboard.bat        one-click control panel (run / shared server / data / push)
├── .env.example             template for the MindRouter key (.env is git-ignored)
├── rgt_dashboard/           the application package
│   ├── config.py            paths, palette, metric metadata, MindRouter settings
│   ├── data.py              DataStore — loads CSV once, validates, pre-aggregates
│   ├── stats.py             realized gain, Welch tests, CIs, Hedges g, regression
│   ├── figures.py           themed chart factories
│   ├── components.py        styled tables, KPI cards, headers
│   ├── layout.py            page shell, tabs, ForestAsk widget
│   ├── callbacks.py         all callbacks (chat, reports, map, downloads)
│   ├── map_builder.py       builds the Leaflet installations map at startup
│   ├── assistant.py         MindRouter client
│   └── report.py            the ForestAsk report engine
├── tools/                   data pipeline
│   ├── build_dataset.py     raw Excel workbook → data/rgt_data.csv (parameterized)
│   └── auto_update.py       watches data_inbox/, rebuilds + refreshes the dashboard
├── data_inbox/              drop new Excel workbooks here for an update
├── assets/                  styles.css, chat.js, loading animation, plot images, map
├── data/                    plot_grids.geojson + rgt_data.csv (the live dataset)
├── deploy/                  server config (systemd service, nginx, deploy.sh)
└── docs/                    guides ↓
    ├── README_HOST.md       one-page server setup for the NKN / IT team  ← IT START HERE
    ├── DEPLOY.md            deployment options & background
    └── SETUP_GITHUB.md      one-time GitHub setup + auto-deploy
```

The heavy lifting (86k rows → plot/seedlot/installation summaries + mortality) happens
**once** at startup in `DataStore`; callbacks slice cached frames.

---

## What the dashboard does

- **Plot Explorer** — per installation: KPIs, a deterministic **screening signal card**
  (status: *Very positive / Positive / Neutral / Negative* — a screen, not an operational
  call), the six per-plot growth heatmaps (Woods plots 1–3, Improved plots 4–6),
  mean-by-plot tables, Avg/Max/Min chart.
- **Genetic Gain & Summary** — across installations: the Woods→Improved dumbbell with
  95% CI + significance rings (and an FDR-adjust toggle), gain-vs-productivity, the site
  gain & survival table + per-seedlot table (CSV export), seedlot bars/boxplots, and a
  Survival & damage panel.
- **Installations map** (topbar globe) — full-window satellite map; pins are colored by
  latest-year **Volume** gain and sit on each site's real plots. Click a pin to fly in and
  see its 6 plot grids (Improved orange / Woods Run blue); a bottom slider switches the
  imagery date (Esri Wayback) with the true capture date shown.
- **ForestAsk report assistant** — ask for a *report* and it builds a full, downloadable
  document (charts + tables + written analysis) grounded strictly in the computed numbers;
  short questions get quick inline answers.

---

## Statistics methodology

- **Realized gain** = `100 × (Improved − Woods Run) / Woods Run`, per installation × year × metric.
- **Growth cohort** — means/gain use **surviving original trees only**; `DEAD` /
  `DEAD (REPLACEMENT)` rows are excluded (replacements are a younger cohort). Mortality still counts them.
- **Unit of replication** is the **seedlot (genetic-entry) mean** (plots are pseudo-replicates).
  A Welch *t*-test gives a 95% CI on the difference and **Hedges g** effect size.
  Stars: `*` p<0.05, `**` p<0.01, `***` p<0.001.
- **Mortality** = share of records coded `DEAD` / `DEAD (REPLACEMENT)`.
- **Gain vs productivity** uses the site's Woods Run mean (OLS slope, r, p); **Kendall's W**
  measures cross-site ranking concordance (G×E).

A screening tool — for inference-grade conclusions, follow up with a mixed-effects model.

---

## Configuration (environment variables)

- `MINDROUTER_API_KEY` — enables ForestAsk (in `.env` locally, or the systemd service on the
  host). Other MindRouter settings are in `.env.example` / `config.py`. **Never commit `.env`.**
- `RGT_DATA_FILE` — point at a different CSV (same schema) without code changes.
- `RGT_URL_PREFIX` — set to `/dashapp/` when serving under that subpath (must match nginx).
