# Putting RGT_APP on GitHub & keeping it updated

**The repo IS this `RGT_APP` folder.** Everything the live site needs is here, and the
auto-deploy workflow (`.github/workflows/deploy.yml`) only runs when it sits at the repo
root — so `RGT_APP` must be the repository, not its parent folder.

Repo: **https://github.com/IFC-UIDAHO/RGT---DASH**

> The one-click control panel **`RGT Dashboard.bat`** does the git steps for you
> (menu **option [6]**). The commands below are the manual equivalent / first-time setup.

---

## 1. One-time setup (do this once)

Open a terminal **inside `RGT_APP`** (Shift-right-click the `RGT_APP` folder →
"Open in Terminal"), then run:

```bat
cd /d "%~dp0"
git init

REM Some drives don't record ownership, so git blocks with "dubious ownership".
REM Trust this folder once (and set your name/email if git ever asks who you are):
git config --global --add safe.directory "%CD:\=/%"
git config --global user.email "mjaslam@uidaho.edu"
git config --global user.name  "pkjaslam"

git branch -M main
git add -A
git status
```

**STOP and check the `git status` output: `.env` must NOT be listed.** It holds the
MindRouter API key and is already in `.gitignore`. If you ever see it listed, do not commit.

Then create the first commit and push (this needs your GitHub sign-in — a browser window
pops up the first time):

```bat
git commit -m "RGT dashboard - initial commit"
git remote add origin https://github.com/IFC-UIDAHO/RGT---DASH.git
git push -u origin main
```

That's it — the code is now on GitHub.

---

## 2. Every time you change something — the easy way

After you edit anything (code, data, assets), open **`RGT Dashboard.bat`** and choose:

```
[6]  Save my changes to GitHub
```

It clears any stale git lock, commits with a one-line note you type, **pulls any online
changes automatically**, and pushes. If the server auto-deploy is configured, the live
site updates within about a minute.

Prefer typing? The same thing by hand:

```bat
git add -A
git commit -m "what I changed"
git pull --rebase
git push
```

---

## 3. Updating the DATA (new field measurements)

You don't hand-edit the dataset. Drop the new Excel workbook into the **`data_inbox/`**
folder, then **`RGT Dashboard.bat` → option [7]**. It rebuilds `data/rgt_data.csv`
(keeping every site not in the new file) and archives the workbook. Then run **option [6]**
to push — the live site gets the new data on the next auto-deploy. See the main
`README.md` ("Updating the data") for details.

---

## 4. How "always latest on the website" works

Git stores the code **and** the data CSV. The live site stays current via the deploy pipeline:

```
you edit / update data in RGT_APP  →  option [6] (git push)  →  GitHub Action SSHes into the server
                                    →  deploy.sh: git pull + pip install + restart gunicorn
                                    →  https://ifc.nkn.uidaho.edu/dashapp/ shows the new version
```

The server side is set up **once** by the NKN/IT team — see `README_HOST.md`.

---

## Safety reminders

- 🔐 **Never commit `.env`** (the API key). It's git-ignored; the server gets the key from
  the systemd service instead (`README_HOST.md`).
- 🔑 If the key was ever exposed, rotate it in MindRouter and update the server's service file.
- ⛔ `venv/`, `__pycache__/`, logs and raw inbox workbooks are git-ignored — never commit them.
