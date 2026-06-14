# Putting RGT_APP on GitHub & keeping it updated

**The repo IS this `RGT_APP` folder.** Everything the live site needs is here, and the
auto-deploy workflow (`.github/workflows/deploy.yml`) only runs when it sits at the repo
root — so `RGT_APP` must be the repository, not `D:\RGT_2026`.

Repo: **https://github.com/IFC-UIDAHO/RGT---DASH**

---

## 1. One-time setup (do this once)

Open a terminal **inside `RGT_APP`** (in Explorer, Shift-right-click the `RGT_APP` folder →
"Open in Terminal" / "Open PowerShell window here"), then run:

```bat
cd /d D:\RGT_2026\RGT_APP
git init

REM D: drives don't record ownership, so git blocks with "dubious ownership".
REM Trust this folder once (and set your name/email if git ever asks who you are):
git config --global --add safe.directory D:/RGT_2026/RGT_APP
git config --global user.email "pkjaslamagrico@gmail.com"
git config --global user.name  "Jaslam"

git branch -M main
git add -A
git status
```

**STOP and check the `git status` output: `.env` must NOT be listed.** It holds the
MindRouter API key and is already in `.gitignore`. If you ever see it listed, do not commit —
tell me and I'll fix the ignore rule.

Then create the first commit and push (this is the step that needs your GitHub sign-in —
a browser window will pop up the first time):

```bat
git commit -m "RGT dashboard - initial commit"
git remote add origin https://github.com/IFC-UIDAHO/RGT---DASH.git
git push -u origin main
```

That's it — the code is now on GitHub.

> **Tidy-up (optional):** there's an empty, unused git repo at the parent folder
> `D:\RGT_2026\.git`. You can delete that `.git` folder in Explorer (turn on "show hidden
> items") so there's only one repo — the one in `RGT_APP`. It has no commits, so nothing is lost.

---

## 2. Every time you change something — the easy way

After you edit anything in `RGT_APP` (code, data, assets):

### Just double-click **`push.bat`**

It shows you what changed, asks for a one-line note, commits, and pushes. Done.
If the server auto-deploy is configured, the live site updates within about a minute.

Prefer typing? The same thing by hand:

```bat
git add -A
git commit -m "what I changed"
git push
```

---

## 3. How "always latest on the website" works

Git only stores the code. The live site stays current because of the deploy pipeline:

```
you edit in RGT_APP  →  push.bat (git push)  →  GitHub Action SSHes into the NKN server
                      →  deploy.sh: git pull + pip install + restart gunicorn
                      →  https://ifc.nkn.uidaho.edu/dashapp/ shows the new version
```

The server side is set up **once** by the NKN/IT team — see `README_HOST.md`. After that,
your entire workflow is just **double-click `push.bat`**.

---

## Safety reminders

- 🔐 **Never commit `.env`** (the API key). It's git-ignored; the server gets the key from
  the systemd service instead (`README_HOST.md`).
- 🔑 If the key was ever exposed, rotate it in MindRouter and update the server's service file.
- ⛔ Don't commit `venv/` or `RGT_TEMP` — they're ignored / not in this folder.
