# Deploying RGT‑DASH & keeping the live site always up to date

This folder (`RGT_APP/`) **is** the deployable app. Push it to
`https://github.com/IFC-UIDAHO/RGT---DASH`, then set up **one** auto‑deploy option
so every future `git push` updates the live site automatically.

---

## ⭐ Your setup — ifc.nkn.uidaho.edu (NKN / U‑Idaho Linux server)
Ready‑made files are included for exactly this. **One‑time**, on the server (your IT / NKN):
1. Clone the repo to `/srv/rgt-dash`, create a venv, `pip install -r requirements.txt`.
2. Service: copy `deploy/rgt-dash.service` → `/etc/systemd/system/`, set `MINDROUTER_API_KEY`
   (and `RGT_URL_PREFIX=/rgt/` if it's a subpath), then `sudo systemctl enable --now rgt-dash`.
3. Reverse proxy: use `deploy/nginx-rgt-dash.conf` (a **subpath** block to drop into the
   existing `ifc.nkn.uidaho.edu` site, or a **subdomain** server block).
4. Auto‑deploy on push: add repo secrets `DEPLOY_HOST / DEPLOY_USER / DEPLOY_SSH_KEY`
   — then `.github/workflows/deploy.yml` runs `deploy/deploy.sh`
   (git pull → pip install → restart) on **every push to `main`**.

After that, your whole loop is: **edit → `git push` → live.**

> ⚠️ Subpath gotcha: if the URL is `ifc.nkn.uidaho.edu/rgt/`, set `RGT_URL_PREFIX=/rgt/`
> (app.py now reads it) **and** match it in nginx, or Dash's assets/callbacks will 404.

---

## 0) One‑time — get it onto GitHub
Run these **inside `RGT_APP/`**:
```bash
git init
git add .
git status            # ⚠️ CONFIRM ".env" is NOT listed — it must stay private
git commit -m "RGT dashboard — initial commit"
git branch -M main
git remote add origin https://github.com/IFC-UIDAHO/RGT---DASH.git
git push -u origin main
```
> If `git push` asks for a password, use a GitHub **Personal Access Token**
> (GitHub → Settings → Developer settings → Personal access tokens), not your password.
>
> Note: there is an old `.git` folder one level up in `RGT_2026/`. Running `git init`
> **inside `RGT_APP/`** (as above) makes this folder its own clean repo — ignore the parent one.

### 🔐 The secret (read this)
`.env` holds `MINDROUTER_API_KEY` and is **git‑ignored on purpose — never commit it.**
On the host, supply the key as an **environment variable** instead (each option below
shows where). Without it the app still runs; only the ForestAsk assistant shows "offline."

---

## How "always latest" actually works
Git only **stores** your code. The live site changes only when a **deploy pipeline**
sees a new push and redeploys. Pick ONE of these:

### Option A — PaaS auto‑deploy (simplest)
Render / Railway / Heroku / Azure App Service connect to a GitHub repo and
**rebuild + restart on every push.** Example (Render):
1. New **Web Service** → connect this repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:server --workers 2 --timeout 300`
4. Environment → add `MINDROUTER_API_KEY = mr2_…`
5. **Auto‑Deploy: On**

Push to `main` → live in ~1 minute. (A `Procfile` is already included for this.)

### Option B — University / own Linux server (systemd + GitHub webhook)
Run it as a service behind nginx; a webhook pulls on push.

`/etc/systemd/system/rgt-dash.service`:
```ini
[Unit]
Description=RGT Dashboard
After=network.target
[Service]
WorkingDirectory=/srv/rgt-dash
Environment=MINDROUTER_API_KEY=mr2_xxxxx
ExecStart=/srv/rgt-dash/venv/bin/gunicorn app:server --workers 2 --timeout 300 --bind 127.0.0.1:8050
Restart=always
[Install]
WantedBy=multi-user.target
```
Update script `update.sh`:
```bash
cd /srv/rgt-dash && git pull && venv/bin/pip install -r requirements.txt && sudo systemctl restart rgt-dash
```
Add a **GitHub webhook** (repo → Settings → Webhooks) that triggers `update.sh` on push
(or run `update.sh` via cron / on demand). Every push → live update.

### Option C — GitHub Actions → SSH deploy (fully automated, lives in the repo)
`.github/workflows/deploy.yml`:
```yaml
name: deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USER }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /srv/rgt-dash
            git pull
            venv/bin/pip install -r requirements.txt
            sudo systemctl restart rgt-dash
```
Add `HOST`, `USER`, `SSH_KEY` under repo → Settings → Secrets → Actions.

---

## Your daily workflow (after the one‑time setup)
```bash
# …edit the dashboard…
git add .
git commit -m "what changed"
git push
```
That's the whole loop — the chosen pipeline redeploys the live site automatically.

## ⏱ Don't forget the timeout
Reports take **20–60 s**. Gunicorn's **default 30 s timeout would kill them mid‑build**,
so always run gunicorn with `--timeout 300` (already in the `Procfile` and every snippet above).
