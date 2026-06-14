# IFC Realized Genetic Gain Trials — Dashboard (v2)

A Plotly **Dash** application for the Intermountain Forestry Cooperative
(University of Idaho) that compares genetically **Improved** vs **Woods Run**
Douglas‑fir seedlots and relates realized genetic gain to site growth factors.

This is a ground‑up refactor of the original single‑file `app.py` into a clean,
tested package, with added forest‑biometrics statistics, a faster data layer, a
modern UI, and an LLM **Report Assistant** powered by MindRouter.

---

## Quickstart

```bash
# 1. (recommended) create a virtual environment
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # macOS/Linux

# 2. install dependencies
pip install -r requirements.txt

# 3. run
python app.py
# open http://127.0.0.1:8050
```

Production:

```bash
gunicorn app:server -b 0.0.0.0:8050 -w 4
```

To enable the Report Assistant, copy `.env.example` to `.env`, add your
MindRouter key, and restart (see **Report Assistant** below).

---

## What you get

The dashboard has three tabs, all driven by one shared control bar
(Region · Installation · Year · Metric · Site type):

**1. Plot Explorer** — for a chosen installation: a KPI strip (Woods Run mean,
Improved mean, realized gain %, significance), the six per‑plot growth heatmaps
(Woods Run plots 1–3, Improved plots 4–6) on a shared colour scale, the two
mean‑by‑plot tables, and an Avg/Max/Min seedlot chart.

**2. Genetic Gain & Summary** — aggregated across installations: KPIs, a
**realized‑gain‑by‑site** bar chart (coloured by significance), a **gain vs site
productivity** regression, a sortable/filterable site table (CSV export),
grouped seedlot bars, tree‑level boxplots, and an installation comparison with
standard errors.

**3. Report Assistant** — a chat that drafts and interprets report text, grounded
in the exact numbers currently shown (it will not invent figures).

---

## Architecture

```
app.py                     thin launcher (creates Dash app, wires package)
rgt_dashboard/
├── config.py              paths, palette, metric metadata, MindRouter settings
├── data.py                DataStore — loads CSV once, validates, pre-aggregates
├── stats.py               realized gain, Welch tests, CIs, Hedges g, regression
├── figures.py             one factory per chart (themed, defensive)
├── components.py          styled DataTable, KPI cards, headers, colour maps
├── layout.py              page shell + three tabs
├── callbacks.py           all callbacks (register(app, store))
└── assistant.py           MindRouter client + report grounding
assets/styles.css          single source of visual truth (no inline styles)
data/rgt24_new.csv         trial data (Region,Installation,Source,Seedlot,PLOT,
                           TREE,Replication,Year,Value,Metric,Management,Defect)
preview.html               static UI snapshot (open without running the server)
FINDINGS_RGT_2026.md        what the analytics currently show
MIGRATION.md               what changed from the original app
```

The heavy lifting (86k rows → plot/seedlot/installation summaries + mortality)
happens **once** at startup in `DataStore`; callbacks slice cached frames, and
the cross‑installation gain table is memoised.

---

## Statistics methodology (applied biometrics)

* **Realized gain** = `100 × (Improved − Woods Run) / Woods Run`, per
  installation × year × metric.
* **Unit of replication** for the Improved‑vs‑Woods‑Run contrast is the
  **seedlot (genetic‑entry) mean**. Because *source* is confounded with physical
  plot (1–3 vs 4–6), the plots are pseudo‑replicates of source; the seedlots are
  the genuine independent genetic samples. A Welch (unequal‑variance) *t*‑test is
  used, with a 95 % CI on the difference and **Hedges g** as effect size.
* **Significance stars**: `*` p<0.05, `**` p<0.01, `***` p<0.001, `ns` otherwise.
* **Mortality** = share of tree records coded `DEAD` / `DEAD (REPLACEMENT)`.
* **Gain vs productivity** uses the site's Woods Run mean as a productivity proxy
  and reports an OLS fit (slope, r, p).

These tests are a **screening tool**. For inference‑grade conclusions, follow up
with a mixed‑effects model (installation/replication as random effects).

---

## Report Assistant (MindRouter)

MindRouter is U‑Idaho's OpenAI‑compatible LLM gateway. The assistant calls
`/v1/chat/completions` and lists models from `/v1/models`. Configuration is via
environment variables (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINDROUTER_API_KEY` | — | Your `mr2_…` service key (required to enable chat) |
| `MINDROUTER_BASE_URL` | `https://mindrouter.uidaho.edu/v1` | OpenAI‑compatible base URL |
| `MINDROUTER_MODEL` | `llama3.3:70b` | Default model |

Each message sends a compact JSON snapshot of the current Summary & Gain view as
grounding context, with a system prompt that forbids inventing numbers. If the
key is missing or the gateway is unreachable, the tab degrades gracefully with a
clear message — it never crashes the app.

**Security:** the key is read from the environment only; never commit `.env`.

---

## Configuration & data swaps

Set `RGT_DATA_FILE` to run the app against a different CSV with the same schema
(e.g. a future `rgt25.csv`) without editing code. Brand colours, default
selections, and the plot→source map live in `rgt_dashboard/config.py`.

---

## Tests

The build was verified end‑to‑end: every callback was exercised through Dash's
real HTTP endpoint (validating JSON serialization of all figures/tables), and the
statistics were checked against an independent SciPy computation. See
`MIGRATION.md` for the full before/after.
