@echo off
REM ================================================================
REM   IFC RGT Dashboard - ALL-IN-ONE control panel.
REM   Double-click and pick a number. This single file replaces all
REM   the other .bat files (open / serve / restart / install / icon /
REM   push). Run "RGT Dashboard.bat serve" for the headless server
REM   (used by the always-on task).
REM ================================================================
title RGT Dashboard
cd /d "%~dp0"
setlocal EnableExtensions

REM Headless mode for the always-on scheduled task.
if /i "%~1"=="serve" goto SERVE_HEADLESS
if /i "%~1"=="watch" goto WATCH_HEADLESS

:MENU
cls
echo  ================================================================
echo       IFC   RGT   DASHBOARD       Control Panel
echo  ================================================================
echo       Folder: %CD%
echo.
echo       [1]  Open the dashboard on THIS computer (just me)
echo       [2]  Start / Restart the SHARED server (everyone on this PC)
echo       [3]  Stop the SHARED server
echo       [4]  Make the shared server start automatically at boot (admin)
echo       [5]  Put a "RGT Dashboard" icon on the Desktop
echo       [6]  Save my changes to GitHub
echo       [7]  Update data from a new Excel (auto-watch the inbox)
echo       [0]  Exit
echo.
set "CH="
set /p "CH=  Type a number, then Enter:  "
if "%CH%"=="1" goto LOCAL
if "%CH%"=="2" goto SHARED
if "%CH%"=="3" goto STOP
if "%CH%"=="4" goto INSTALL
if "%CH%"=="5" goto ICON
if "%CH%"=="6" goto PUSH
if "%CH%"=="7" goto DATAUPDATE
if "%CH%"=="0" exit /b 0
goto MENU

REM ----------------------------------------------------------------
:LOCAL
call :ENSURE_ENV
if not defined PY goto NOPY
echo.
echo   Opening the dashboard in your browser (http://127.0.0.1:8050)...
echo   Keep this window open while you use it; close it to stop.
echo.
start "" /b cmd /c "timeout /t 5 >nul & start "" http://127.0.0.1:8050"
"%PY%" app.py
echo.
echo   Stopped.
pause
goto MENU

REM ----------------------------------------------------------------
:SHARED
echo.
echo   Stopping any existing server on port 8050...
schtasks /End /TN "RGT Dashboard" 1>nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8050" ^| findstr LISTENING') do taskkill /F /PID %%P 1>nul 2>nul
call :ENSURE_ENV
if not defined PY goto NOPY
"%PY%" -c "import waitress" 1>nul 2>nul || "%PY%" -m pip install --disable-pip-version-check waitress 1>nul 2>nul
call :WRITE_SERVE_PY
echo.
echo   ============================================================
echo     SHARED dashboard is now running for everyone on this PC:
echo            http://localhost:8050
echo     Keep this window open. Press Ctrl+C or close it to stop.
echo   ============================================================
echo.
"%PY%" "%~dp0_rgt_serve.py"
echo.
echo   Shared server stopped.
pause
goto MENU

REM ----------------------------------------------------------------
:STOP
echo.
schtasks /End /TN "RGT Dashboard" 1>nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8050" ^| findstr LISTENING') do taskkill /F /PID %%P 1>nul 2>nul
echo   Shared server stopped.
echo.
pause
goto MENU

REM ----------------------------------------------------------------
:INSTALL
net session >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [!] For this option, close this window, then RIGHT-CLICK
  echo       "RGT Dashboard.bat" and choose "Run as administrator",
  echo       then pick [4] again.
  echo.
  pause
  goto MENU
)
echo.
echo   Registering the dashboard to start at boot...
schtasks /Create /TN "RGT Dashboard" /TR "cmd /c \"\"%~f0\" serve\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
schtasks /Run /TN "RGT Dashboard" 1>nul 2>nul
echo.
echo   Done. The shared dashboard now starts automatically at boot.
echo   Everyone on this PC can open:  http://localhost:8050
echo.
pause
goto MENU

REM ----------------------------------------------------------------
:ICON
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pub=Join-Path $env:PUBLIC 'Desktop'; $paths=@(); if(Test-Path $pub){$paths+=$pub}; $paths+=[Environment]::GetFolderPath('Desktop'); $done=$false; foreach($d in $paths){ try{ $p=Join-Path $d 'RGT Dashboard.url'; Set-Content -Path $p -Value @('[InternetShortcut]','URL=http://localhost:8050/','IconIndex=18',('IconFile='+$env:SystemRoot+'\System32\SHELL32.dll')) -Encoding ASCII -ErrorAction Stop; Write-Host ('  Icon created on: '+$d); $done=$true; break } catch { Write-Host ('  (skipped '+$d+' - no write access)') } }; if(-not $done){ Write-Host '  Could not create the icon.' }"
echo.
echo   The "RGT Dashboard" Desktop icon opens http://localhost:8050
echo   (the shared server must be running - use option [2]).
echo.
pause
goto MENU

REM ----------------------------------------------------------------
:PUSH
echo.
git config --global --add safe.directory "%CD:\=/%" 1>nul 2>nul
REM Clear a stale lock left behind by a previously interrupted git command.
if exist ".git\index.lock" del /f /q ".git\index.lock" 1>nul 2>nul
git rev-parse --is-inside-work-tree 1>nul 2>nul
if errorlevel 1 (
  echo   [!] This folder is not connected to GitHub yet.
  pause
  goto MENU
)
git add -A
git diff --cached --quiet && (
  echo   Nothing changed - GitHub is already up to date.
  pause
  goto MENU
)
set "MSG="
set /p "MSG=  Briefly describe what changed (or press Enter):  "
if "%MSG%"=="" set "MSG=Update %date% %time%"
git commit -m "%MSG%"
echo.
echo   Syncing with GitHub (pulling any online changes first)...
git pull --rebase 1>nul 2>nul
if errorlevel 1 (
  git rebase --abort 1>nul 2>nul
  echo   [!] Could not auto-sync with GitHub. It may have online changes that
  echo       clash with yours, or there is no connection. Ask for help, or in a
  echo       terminal run:  git pull   ^(resolve any conflicts^)  then option 6.
  pause
  goto MENU
)
echo   Pushing to GitHub...
git push
echo.
pause
goto MENU

REM ----------------------------------------------------------------
:DATAUPDATE
echo.
if not exist "data_inbox" md "data_inbox" 1>nul 2>nul
call :ENSURE_ENV
if not defined PY goto NOPY
"%PY%" -c "import openpyxl" 1>nul 2>nul || "%PY%" -m pip install --disable-pip-version-check openpyxl 1>nul 2>nul
echo   Checking the data_inbox folder for a new Excel file...
"%PY%" "%~dp0tools\auto_update.py" --once
echo.
net session >nul 2>nul
if errorlevel 1 (
  echo   Done. To make this FULLY automatic ^(watch the folder all the time^),
  echo   close this window, RIGHT-CLICK "RGT Dashboard.bat" -^> Run as administrator,
  echo   then pick [7] again. ^(Also turn on the server with [4].^)
  echo.
  pause
  goto MENU
)
schtasks /Create /TN "RGT Data Watcher" /TR "cmd /c \"\"%~f0\" watch\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F 1>nul 2>nul
schtasks /Run /TN "RGT Data Watcher" 1>nul 2>nul
echo   Automatic data updates are ON. Just drop new Excel files into the
echo   "data_inbox" folder and the dashboard refreshes by itself.
echo   (Make sure the shared server is always-on too: option [4].)
echo.
pause
goto MENU

REM ----------------------------------------------------------------
:NOPY
echo.
echo   [!] Python is not installed on this account.
echo       Ask IT to install "Python 3.11" for all users
echo       (tick "Add python.exe to PATH"), then try again.
echo.
pause
goto MENU

REM ================================================================
REM  Headless server entry point (scheduled task calls this).
REM ================================================================
:SERVE_HEADLESS
call :ENSURE_ENV
if not defined PY exit /b 1
"%PY%" -c "import waitress" 1>nul 2>nul || "%PY%" -m pip install --disable-pip-version-check waitress 1>nul 2>nul
call :WRITE_SERVE_PY
"%PY%" "%~dp0_rgt_serve.py"
exit /b 0

REM ================================================================
REM  Headless data-watcher entry point (scheduled task calls this).
REM ================================================================
:WATCH_HEADLESS
call :ENSURE_ENV
if not defined PY exit /b 1
"%PY%" -c "import openpyxl" 1>nul 2>nul || "%PY%" -m pip install --disable-pip-version-check openpyxl 1>nul 2>nul
"%PY%" "%~dp0tools\auto_update.py" --watch
exit /b 0

REM ================================================================
REM  Subroutines
REM ================================================================
:ENSURE_ENV
REM Find a working Python env; build a private one for this account if needed.
set "PY="
set "UV=venv_%USERNAME%"
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" -c "import dash" 1>nul 2>nul && set "PY=venv\Scripts\python.exe"
)
if not defined PY if exist "%UV%\Scripts\python.exe" (
  "%UV%\Scripts\python.exe" -c "import dash" 1>nul 2>nul && set "PY=%UV%\Scripts\python.exe"
)
if defined PY goto :eof
echo   First-time setup for this account, please wait about a minute...
set "BASE="
py -3 -c "import sys" 1>nul 2>nul && set "BASE=py -3"
if not defined BASE (
  python -c "import sys" 1>nul 2>nul && set "BASE=python"
)
if not defined BASE goto :eof
%BASE% -m venv "%UV%" 1>nul 2>nul
"%UV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt 1>"setup_%USERNAME%.log" 2>&1
if not errorlevel 1 set "PY=%UV%\Scripts\python.exe"
goto :eof

:WRITE_SERVE_PY
REM Ensure the shared-server entry script exists. _rgt_serve.py is normally part of
REM the repo (a tracked file); regenerate a minimal copy only if it is missing, e.g.
REM on an older checkout. Python adds the script's own folder to sys.path so the
REM "from app import server" below resolves to this app.
if exist "%~dp0_rgt_serve.py" goto :eof
>  "%~dp0_rgt_serve.py" echo import os
>> "%~dp0_rgt_serve.py" echo from waitress import serve
>> "%~dp0_rgt_serve.py" echo from app import server
>> "%~dp0_rgt_serve.py" echo HOST = os.environ.get("RGT_HOST", "0.0.0.0")
>> "%~dp0_rgt_serve.py" echo PORT = int(os.environ.get("PORT", "8050"))
>> "%~dp0_rgt_serve.py" echo serve(server, host=HOST, port=PORT, threads=8)
goto :eof
