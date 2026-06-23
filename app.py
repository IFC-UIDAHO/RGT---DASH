# -*- coding: utf-8 -*-
"""
IFC Realized Genetic Gain Trials -- dashboard entry point.

    python app.py            # dev server on http://127.0.0.1:8050
    gunicorn app:server      # production (server = the Flask WSGI app)

Environment (optional; .env is auto-loaded):
    RGT_DATA_FILE         alternative CSV (default data/rgt_data.csv)
    MINDROUTER_API_KEY    mr2_... key to enable the ForestAsk assistant
"""
from __future__ import annotations

import logging
import os

# --- Python 3.14 compatibility shim -------------------------------------------
# Dash 2.18.x (pinned <3) calls pkgutil.find_loader() in its dev/hot-reload code
# path. That function was deprecated in Python 3.12 and REMOVED in Python 3.14,
# so launching with debug=True raises:
#   AttributeError: module 'pkgutil' has no attribute 'find_loader'
# Restore it using the modern importlib equivalent. This mirrors exactly what the
# stdlib used to do (return the module's loader, or None) and is a no-op on
# Python <= 3.13 where find_loader still exists.
import pkgutil as _pkgutil

if not hasattr(_pkgutil, "find_loader"):
    import importlib.util as _importlib_util

    def _find_loader(name):  # faithful stand-in for the removed pkgutil.find_loader
        try:
            spec = _importlib_util.find_spec(name)
        except (ImportError, AttributeError, ValueError):
            return None
        return spec.loader if spec is not None else None

    _pkgutil.find_loader = _find_loader
# -----------------------------------------------------------------------------

import dash
import dash_bootstrap_components as dbc

from rgt_dashboard import config
from rgt_dashboard.callbacks import register
from rgt_dashboard.data import get_store
from rgt_dashboard.layout import build_layout
from rgt_dashboard import map_builder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

store = get_store()
try:
    map_builder.generate_map_html(store)
except Exception as _map_err:
    logging.warning("map_builder failed (non-fatal): %s", _map_err)

# Optional URL prefix for serving under a subpath, e.g. ifc.nkn.uidaho.edu/dashapp/
# Set RGT_URL_PREFIX="/dashapp/" on the host (must match the nginx location + proxy_pass).
# Leave unset to serve at the domain root.
_prefix = os.environ.get("RGT_URL_PREFIX", "").strip()
_dash_kwargs = {}
if _prefix:
    if not _prefix.startswith("/"):
        _prefix = "/" + _prefix
    if not _prefix.endswith("/"):
        _prefix = _prefix + "/"
    _dash_kwargs["url_base_pathname"] = _prefix

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title=config.APP_TITLE,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    **_dash_kwargs,
)
server = app.server  # for gunicorn

app.layout = build_layout(store)
register(app, store)

if __name__ == "__main__":
    # debug=True keeps hot-reload; dev_tools_ui=False hides the floating blue
    # debug/callback-graph button so it does not clash with the ForestAsk widget.
    app.run(host="127.0.0.1", port=8050, debug=True,
            dev_tools_ui=False, dev_tools_props_check=False)
