@echo off
REM ============================================================
REM   RGT Dashboard - one-click update to GitHub
REM   Double-click this AFTER you change anything in RGT_APP.
REM   It commits your changes and pushes them to GitHub; if the
REM   server auto-deploy is set up, the live site updates in ~1 min.
REM ============================================================
cd /d "%~dp0"

REM D: drives don't record ownership, which git blocks ("dubious ownership").
REM Mark this folder as trusted (forward-slash path is what git expects).
git config --global --add safe.directory "%CD:\=/%" >nul 2>&1

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [!] This folder is not connected to GitHub yet.
  echo      Do the one-time setup in SETUP_GITHUB.md first.
  echo.
  pause
  exit /b 1
)

echo.
echo  Looking for changes in RGT_APP ...
git add -A
git diff --cached --quiet
if not errorlevel 1 (
  echo  Nothing changed - GitHub is already up to date.
  echo.
  pause
  exit /b 0
)

echo.
echo  ---- files about to be updated ----
git --no-pager diff --cached --stat
echo  -----------------------------------
echo.

set "msg=%~1"
if "%msg%"=="" set /p "msg=  Briefly describe what changed (or press Enter): "
if "%msg%"=="" set "msg=Update %date% %time%"

git commit -m "%msg%"
echo.
echo  Pushing to GitHub ...
git push
if errorlevel 1 (
  echo.
  echo  [!] Push failed. Most likely you are not signed in to GitHub,
  echo      or the remote is not set. See SETUP_GITHUB.md.
) else (
  echo.
  echo  DONE - GitHub is updated.
  echo  If auto-deploy is on, https://ifc.nkn.uidaho.edu/dashapp/ refreshes shortly.
)
echo.
pause
