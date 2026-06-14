#!/usr/bin/env bash
# Pull the latest code and restart the dashboard.
# Run on the server manually, from a GitHub webhook, or from the GitHub Action.
set -euo pipefail

APP_DIR="/srv/rgt-dash"          # <-- adjust to the repo path on the server
cd "$APP_DIR"

git pull --ff-only
./venv/bin/pip install -q -r requirements.txt
sudo systemctl restart rgt-dash

echo "[deploy] RGT dashboard updated $(date -u +%FT%TZ)"
