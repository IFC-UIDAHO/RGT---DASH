# RGT Dashboard — Host Setup (NKN / U-Idaho)

A Python **Dash** app (gunicorn + systemd, reverse-proxied by nginx). Public URL:
**https://ifc.nkn.uidaho.edu/dashapp/** — this replaces the older dashboard at the same path.

Repo: **https://github.com/IFC-UIDAHO/RGT---DASH** · Python 3.10+ · ~60 MB.

All config files referenced below are in this repo under `deploy/`.

---

## One-time server setup

```bash
# 1. Clone to /srv/rgt-dash
sudo mkdir -p /srv/rgt-dash && sudo chown $USER /srv/rgt-dash
git clone https://github.com/IFC-UIDAHO/RGT---DASH.git /srv/rgt-dash
cd /srv/rgt-dash

# 2. Virtualenv + dependencies (lean: dash, pandas, numpy, scipy, plotly, gunicorn…)
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. Service (gunicorn via systemd)
sudo cp deploy/rgt-dash.service /etc/systemd/system/rgt-dash.service
sudo nano /etc/systemd/system/rgt-dash.service      # set User, and the real MINDROUTER_API_KEY
sudo systemctl daemon-reload
sudo systemctl enable --now rgt-dash
systemctl status rgt-dash                            # should be "active (running)"
```

The service already sets `RGT_URL_PREFIX=/dashapp/` and `--timeout 300`. **The 300 s
timeout is required** — report builds take 20–60 s and would be killed by gunicorn's 30 s default.

```bash
# 4. nginx — add the /dashapp/ location to the existing ifc.nkn.uidaho.edu server block
sudo nano /etc/nginx/sites-available/ifc...          # paste block (A) from deploy/nginx-rgt-dash.conf
sudo nginx -t && sudo systemctl reload nginx
```

Visit **https://ifc.nkn.uidaho.edu/dashapp/** — the dashboard should load.

> **Key config invariant:** the nginx `location /dashapp/` **and** the service's
> `RGT_URL_PREFIX=/dashapp/` must match. If they ever differ, Dash 404s its assets/callbacks.

---

## Auto-deploy on every push (GitHub Action — already in the repo)

`.github/workflows/deploy.yml` SSHes into this server on each push to `main` and runs
`deploy/deploy.sh` (git pull → pip install → `systemctl restart rgt-dash`).

Enable it once: in **GitHub → repo → Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | `ifc.nkn.uidaho.edu` (or the server IP) |
| `DEPLOY_USER` | the SSH user that owns `/srv/rgt-dash` |
| `DEPLOY_SSH_KEY` | a private SSH key whose public half is in that user's `~/.ssh/authorized_keys` |

Also ensure that user may restart the service without a password prompt, e.g. in `sudoers`:

```
<deploy_user> ALL=(ALL) NOPASSWD: /bin/systemctl restart rgt-dash
```

After that, a push from the maintainer → live update in under a minute. Manual deploy anytime:
`bash /srv/rgt-dash/deploy/deploy.sh`, or the **Run workflow** button on the Actions tab.

---

## Notes

- **Secrets:** `.env` is **not** in the repo. The only secret the host needs is
  `MINDROUTER_API_KEY`, set in the systemd service (step 3). Rotate it in MindRouter if exposed.
- **Data:** the trial CSVs ship in `data/` (the app loads `data/rgt24_new.csv`).
- **Logs:** `journalctl -u rgt-dash -f`.
- **Path on server:** `deploy.sh` and the service assume `/srv/rgt-dash`; change both if you
  clone elsewhere.
