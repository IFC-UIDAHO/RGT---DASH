# -*- coding: utf-8 -*-
"""
Central configuration for the RGT dashboard.

Everything that used to be a magic value scattered through ``app.py`` lives here:
paths, the brand palette, metric metadata, the plot->source map, the
CORE/TRANSFER classification and the MindRouter (LLM) settings.

A tiny dependency-free ``.env`` loader runs at import so secrets (the MindRouter
key) live in a git-ignored ``.env`` file rather than in source or the shell.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
DATA_FILE = Path(os.environ.get("RGT_DATA_FILE", DATA_DIR / "rgt24_new.csv"))


# --------------------------------------------------------------------------- #
# .env loader (no external dependency). Real environment variables win.
# --------------------------------------------------------------------------- #
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass  # never let a malformed .env break startup


_load_dotenv(PROJECT_ROOT / ".env")

# --------------------------------------------------------------------------- #
# Domain knowledge about the trial design
# --------------------------------------------------------------------------- #
SOURCE_WOODS = "Woods run"
SOURCE_IMPROVED = "Improved"
PLOT_SOURCE_MAP = {1: SOURCE_WOODS, 2: SOURCE_WOODS, 3: SOURCE_WOODS,
                   4: SOURCE_IMPROVED, 5: SOURCE_IMPROVED, 6: SOURCE_IMPROVED}

TRANSFER_INSTALLATIONS = ("CARSCALLEN TRANSFER", "SHERRY TRANSFER", "SITKA TRAN")
DEAD_CODES = ("DEAD", "DEAD (REPLACEMENT)")

METRICS = {
    "CALIPER GROWTH (MM)": {"short": "Caliper", "unit": "mm", "axis": "Caliper growth (mm)"},
    "HEIGHT GROWTH (CM)":  {"short": "Height",  "unit": "cm", "axis": "Height growth (cm)"},
    "VOLUME GROWTH (CM3)": {"short": "Volume",  "unit": "cm3", "axis": "Volume growth (cm3)"},
}

DEFAULT_REGION = "INW"
DEFAULT_METRIC = "HEIGHT GROWTH (CM)"
DEFAULT_YEAR = "Year1"
REGION_DEFAULT_INSTALLATION = {"INW": "HOODOO", "K-S": "LODGEPOLE 1"}

# --------------------------------------------------------------------------- #
# Brand palette  (Intermountain Forestry Cooperative / University of Idaho)
# --------------------------------------------------------------------------- #
class Color:
    NAVY = "#16467a"
    NAVY_DARK = "#0f3257"
    GOLD = "#DBA800"
    GOLD_SOFT = "#F2C94C"
    WOODS = "#2F6E8F"
    WOODS_SOFT = "#8FBCD4"
    IMPROVED = "#E08A1E"
    IMPROVED_SOFT = "#F4C786"
    POSITIVE = "#2E8B57"
    NEGATIVE = "#C0392B"
    NEUTRAL = "#8a929c"
    INK = "#1f2933"
    MUTED = "#5b6671"
    GRID = "#e6eaee"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#f4f7fa"
    BORDER = "#dce3ea"

HEATMAP_COLORSCALE = "YlGnBu"
FONT_FAMILY = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# --------------------------------------------------------------------------- #
# MindRouter (University of Idaho LLM gateway) — OpenAI-compatible
# --------------------------------------------------------------------------- #
class MindRouter:
    BASE_URL = os.environ.get("MINDROUTER_BASE_URL", "https://mindrouter.uidaho.edu/v1")
    API_KEY = os.environ.get("MINDROUTER_API_KEY", "").strip()
    # The dashboard exposes ONE branded assistant ("IFC LLM"). Behind it, the best
    # model is auto-selected per request: "default-llm" (fast, general) by default,
    # escalating to "default-llm-large" for in-depth requests. These are MindRouter
    # aliases that always resolve to the best current model on the cluster.
    BRAND_LABEL = "IFC LLM"
    DEFAULT_MODEL = os.environ.get("MINDROUTER_MODEL", "default-llm")
    LARGE_MODEL = os.environ.get("MINDROUTER_LARGE_MODEL", "default-llm-large")
    FALLBACK_MODEL = os.environ.get("MINDROUTER_FALLBACK_MODEL", "default-llm")
    REASONING_EFFORT = os.environ.get("MINDROUTER_REASONING_EFFORT", "high")
    TEMPERATURE = float(os.environ.get("MINDROUTER_TEMPERATURE", "0.3"))
    MAX_TOKENS = int(os.environ.get("MINDROUTER_MAX_TOKENS", "32768"))
    # Chat is short Q&A — give it a small, fast budget; reports pass the big budget above.
    CHAT_MAX_TOKENS = int(os.environ.get("MINDROUTER_CHAT_MAX_TOKENS", "2000"))
    CHAT_REASONING = os.environ.get("MINDROUTER_CHAT_REASONING", "low")
    TIMEOUT = float(os.environ.get("MINDROUTER_TIMEOUT", "300"))

    @classmethod
    def configured(cls) -> bool:
        return bool(cls.API_KEY)


APP_TITLE = "IFC | Realized Genetic Gain Trials"
