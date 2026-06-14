# IFC Realized Genetic Gain Trials — Dashboard

A Plotly **Dash** application for the Intermountain Forestry Cooperative
(University of Idaho) that compares genetically **Improved** vs **Woods Run**
Douglas-fir seedlots across installations in two regions (Inland Northwest · INW,
and Klamath–Siskiyou · K-S) and relates realized genetic gain to site growth
factors — with an LLM **ForestTask** report assistant powered by MindRouter.

**Live:** https://ifc.nkn.uidaho.edu/dashapp/ · **Repo:** IFC-UIDAHO/RGT---DASH

---

## Quickstart (run locally)

```bat
python -m venv venv
venv\Scripts\activate            REM  Windows  (use: source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python app.py                    REM  then open http://127.0.0.1:8050
```

To enable the report assistant, copy `.env.example` → `.env` and add your
MindRouter key. Production: `gunicorn app:server -b 0.0.0.0:8050 -w 2 --timeout 300`.

---

## Project layout

```
RGT_APP/                     ← this folder IS the git repo / deployable unit
├── app.py                   thin launcher (honors RGT_URL_PREFIX for subpath hosting)
├── requirements.txt         lean runtime deps
├── Procfile                 gunicorn start command (--timeout 300)
├── push.bat                 ← one-click: commit + push your changes to GitHub
├── .env.example             template for the MindRouter key (.env is git-ignored)
├── rgt_dashboard/           the application package
│   ├── config.py            paths, palette, metric metadata, MindRouter settings
│   ├── data.py              DataStore — loads CSV once, validates, pre-aggregates
│   ├── stats.py             realized gain, Welch tests, CIs, Hedges g, regression
│   ├── figures.py           themed chart factories
│   ├── components.py        styled tables, KPI cards, headers
│   ├── layout.py            page shell, tabs, ForestTask widget
│   ├── callbacks.py         all callbacks (chat, reports, map, downloads)
│   ├── map_builder.py       builds the Leaflet installations map at startup
│   ├── assistant.py         MindRouter client
│   └── report.py            the ForestTask report engine
├── assets/                  styles.css, chat.js, loading animation, map
├── data/                    trial CSVs (the app loads data/rgt24_new.csv)
├── deploy/                  server config (systemd service, nginx, deploy.sh)
└── docs/                    guides ↓
    ├── SETUP_GITHUB.md      one-time GitHub setup + the daily update workflow
    ├── README_HOST.md       one-page server setup for the NKN / IT team
    └── DEPLOY.md            deployment options & background
```

Heavy lifting (86k rows → plot/seedlot/installation summaries + mortality) happens
**once** at startup in `DataStore`; callbacks slice cached frames.

---

## Updating the live site & hosting

- **Make a change → publish it:** double-click **`push.bat`** (commit + push). See
  **[docs/SETUP_GITHUB.md](docs/SETUP_GITHUB.md)** for the one-time setup and how
  auto-deploy makes the live site refresh on every push.
- **Server setup (NKN / IT team):** **[docs/README_HOST.md](docs/README_HOST.md)** —
  clone → venv → systemd service → nginx `/dashapp/` → GitHub SSH secrets.
- **Background & alternatives:** **[docs/DEPLOY.md](docs/DEPLOY.md)**.

---

## What the dashboard does

- **Plot Explorer** — per installation: KPIs, the six per-plot growth heatmaps
  (Woods plots 1–3, Improved plots 4–6), mean-by-plot tables, Avg/Max/Min chart.
- **Genetic Gain & Summary** — across installations: realized-gain-by-site bars
  (coloured by significance), gain-vs-site-productivity regression, sortable site
  table (CSV export), seedlot bars, boxplots, installation comparison.
- **Installations map** — satellite map; each pin opens year-by-year growth
  mini-plots (Improved vs Woods) with values on hover.
- **ForestTask report assistant** — ask for a *report* and it builds a full,
  downloadable document (charts + tables + written analysis), grounded strictly in
  the computed numbers. It understands any combination of region / installation /
  seedlot / year / metric, side-by-side comparisons, a deployment decision summary,
  seedlot stability (G×E), and damage/risk — then self-reviews against an expert
  rubric before finishing. Short questions get quick inline answers instead.

---

## Statistics methodology

- **Realized gain** = `100 × (Improved − Woods Run) / Woods Run`, per
  installation × year × metric.
- **Unit of replication** is the **seedlot (genetic-entry) mean** — because source
  is confounded with physical plot, plots are pseudo-replicates; seedlots are the
  genuine genetic samples. A Welch *t*-test gives a 95 % CI on the difference and
  **Hedges g** as effect size. Stars: `*` p<0.05, `**` p<0.01, `***` p<0.001.
- **Mortality** = share of records coded `DEAD` / `DEAD (REPLACEMENT)`.
- **Gain vs productivity** uses the site's Woods Run mean as a productivity proxy
  (OLS slope, r, p). **Kendall's W** measures cross-site ranking concordance (G×E).

A screening tool — for inference-grade conclusions, follow up with a mixed-effects model.

---

## Configuration

- `MINDROUTER_API_KEY` (in `.env` locally, or the systemd service on the host) —
  enables ForestTask. Other MindRouter settings are in `.env.example` / `config.py`.
- `RGT_DATA_FILE` — point at a different CSV (same schema) without code changes.
- `RGT_URL_PREFIX` — set to `/dashapp/` when serving under that subpath (matches nginx).

**Security:** the API key is read from the environment only — never commit `.env`.
