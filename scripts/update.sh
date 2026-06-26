#!/usr/bin/env bash
# Singer-audience skill — one-click sync (read-only pull).
# Usage:  bash scripts/update.sh     (Git Bash / Linux / macOS)
# Pulls the latest knowledge base only; never pushes.
set -u
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SKILL_DIR" || { echo "[ERROR] cannot enter $SKILL_DIR"; exit 1; }
echo "Repo: $SKILL_DIR"
echo "Pulling latest knowledge base (git pull --ff-only)..."
if git pull --ff-only; then
  echo "[OK] Synced to latest."
else
  echo "[WARN] Pull did not finish: maybe offline, or local uncommitted changes block fast-forward."
  echo "       Maintainer: commit/push your changes first. Others: stash/reset local references edits."
  exit 1
fi