# -*- coding: utf-8 -*-
"""
auto_update.py — watch data_inbox/ for a new RGT workbook and refresh the dashboard.

Drop a workbook into data_inbox/.  This rebuilds data/rgt_data.csv from it
(replacing the installations it contains, keeping the rest), archives the
workbook into data_inbox/processed/, and restarts the shared dashboard.

    python tools/auto_update.py --once    # process the newest new file, then exit
    python tools/auto_update.py --watch    # loop forever (used by the scheduled task)

A file is only remembered as done once it APPLIES SUCCESSFULLY, so a failure
(e.g. a missing library that later gets installed) is retried automatically.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import build_dataset as bd  # noqa: E402

INBOX = APP_DIR / "data_inbox"
PROCESSED = INBOX / "processed"
OUTPUT = APP_DIR / "data" / "rgt_data.csv"
STATE = HERE / "auto_update.state.json"
LOG = HERE / "auto_update.log"
TASK_NAME = "RGT Dashboard"   # the shared-server scheduled task (menu option 4)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("auto_update")

_logged_failures: set = set()   # (name, mtime) we've already logged this run


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, indent=2))
    except Exception:
        log.exception("could not write state file")


def _mark_applied(name: str, mtime: float) -> None:
    state = _load_state()
    state.setdefault("applied", {})[name] = mtime
    state["last_success"] = dt.datetime.now().isoformat(timespec="seconds")
    _save_state(state)


def _newest_unprocessed() -> Path | None:
    """Newest .xlsx in the inbox that has NOT been successfully applied yet."""
    applied = _load_state().get("applied", {})
    cands = []
    for p in INBOX.glob("*.xlsx"):
        if p.name.startswith("~$"):          # Excel lock file
            continue
        m = p.stat().st_mtime
        if applied.get(p.name) == m:          # already applied this exact version
            continue
        cands.append((m, p))
    if not cands:
        return None
    cands.sort()
    return cands[-1][1]


def _restart_server() -> None:
    """Best-effort restart of the shared-server task so waitress reloads the CSV."""
    try:
        subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], capture_output=True, timeout=30)
        subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, timeout=30)
        log.info("restarted scheduled task %r", TASK_NAME)
    except Exception as e:
        log.warning("could not restart server task (%s) - new data loads on next start", e)


def _log_failure_once(src: Path, msg: str) -> None:
    key = (src.name, src.stat().st_mtime if src.exists() else 0)
    if key not in _logged_failures:
        _logged_failures.add(key)
        log.error(msg)


def process_once() -> bool:
    INBOX.mkdir(exist_ok=True)
    PROCESSED.mkdir(exist_ok=True)
    src = _newest_unprocessed()
    if src is None:
        return False

    mtime = src.stat().st_mtime
    log.info("new workbook detected: %s", src.name)
    try:
        out, notes = bd.build(src, OUTPUT)
        for nt in notes:
            log.info("   %s", nt)
        errors, warns = bd.validate(out, map_installations=bd._map_installations())
        for w in warns:
            log.warning("   NOTE: %s", w)
        if errors:
            # The file is readable but its data is wrong -> remember it as done so we
            # don't loop; the user must fix and re-drop (new mtime retries).
            _mark_applied(src.name, mtime)
            log.error("VALIDATION FAILED for %s -> NOT applied:", src.name)
            for e in errors:
                log.error("   - %s", e)
            return False
    except bd.BuildError as e:
        _mark_applied(src.name, mtime)      # wrong format/sheet -> don't loop
        log.error("could not read %s: %s", src.name, e)
        return False
    except Exception as e:
        # Transient/environment problem (e.g. a library not yet installed).
        # Do NOT remember it, so it retries automatically once fixed.
        _log_failure_once(src, f"build failed for {src.name} (will retry): {e}")
        return False

    if OUTPUT.exists():
        shutil.copy2(OUTPUT, OUTPUT.with_name(OUTPUT.stem + ".prev.csv"))
    out.to_csv(OUTPUT, index=False)
    log.info("wrote %s  (rows=%d, installations=%d)",
             OUTPUT.name, len(out), out["Installation"].nunique())

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.move(str(src), str(PROCESSED / f"{stamp}__{src.name}"))
    except Exception:
        log.warning("could not move %s into processed/", src.name)
    _mark_applied(src.name, mtime)
    _restart_server()
    log.info("update complete for %s", src.name)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Watch data_inbox and refresh the dashboard.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="process newest file then exit")
    g.add_argument("--watch", action="store_true", help="loop forever")
    ap.add_argument("--interval", type=int, default=60, help="poll seconds in --watch")
    args = ap.parse_args(argv)

    if args.watch:
        log.info("auto-update watching %s every %ss", INBOX, args.interval)
        while True:
            try:
                process_once()
            except Exception:
                log.exception("unexpected error in watch loop")
            time.sleep(args.interval)
    else:
        print("updated" if process_once() else "no new workbook applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
