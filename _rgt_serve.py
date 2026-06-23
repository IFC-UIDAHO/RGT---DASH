# -*- coding: utf-8 -*-
"""
Shared-server entry point for the RGT dashboard on Windows / Remote Desktop.

Launched by "RGT Dashboard.bat":
  * option [2]  Start / Restart the SHARED server (runs in that console window)
  * option [4]  always-on boot task (SERVE_HEADLESS, runs as the SYSTEM account)

It serves the Dash app's WSGI object (app.server) with waitress so everyone on
this PC can reach http://localhost:8050. Production on Linux uses gunicorn
'app:server' instead -- see docs/README_HOST.md.
"""
import os

from waitress import serve

from app import server  # importing app.py builds the dashboard and exposes .server

HOST = os.environ.get("RGT_HOST", "0.0.0.0")  # 0.0.0.0 = reachable as localhost for every user on this PC
PORT = int(os.environ.get("PORT", "8050"))
THREADS = int(os.environ.get("RGT_THREADS", "8"))

if __name__ == "__main__":
    print("RGT shared server running on http://localhost:" + str(PORT))
    print("Keep this window open; close it or press Ctrl+C to stop.")
    serve(server, host=HOST, port=PORT, threads=THREADS)
