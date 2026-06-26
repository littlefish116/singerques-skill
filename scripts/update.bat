@echo off
REM Singer-audience skill - one-click sync (read-only pull). Double-click to run.
cd /d "%~dp0\.."
where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] git not found. Install Git for Windows and ensure it is in PATH, then re-run.
  pause
  exit /b 1
)
echo Pulling latest knowledge base (git pull --ff-only)...
call git pull --ff-only
if errorlevel 1 goto fail
echo.
echo [OK] Synced to latest.
echo.
pause
exit /b 0
:fail
echo.
echo [WARN] Pull did not finish: maybe offline, or local uncommitted changes block fast-forward.
echo        Maintainer: commit/push first. Others: stash/reset local references edits.
echo.
pause
exit /b 1