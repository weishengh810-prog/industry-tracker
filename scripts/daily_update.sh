#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

mkdir -p logs
LOG_FILE="${PROJECT_ROOT}/logs/daily_update.log"
LOCK_FILE="${PROJECT_ROOT}/logs/daily_update.lock"
exec >>"${LOG_FILE}" 2>&1

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    log "Another daily update is already running; exiting."
    exit 0
  fi
else
  LOCK_DIR="${LOCK_FILE}.d"
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    log "Another daily update may be running; fallback lock exists at ${LOCK_DIR}."
    exit 0
  fi
  trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT
fi

source .venv/bin/activate

log "Starting daily industry tracker update."
python scripts/run_pipeline.py
python scripts/store_to_db.py
python scripts/export_static.py

TODAY=$(date +%F)
ARCHIVE_DIR="archives/${TODAY}"

mkdir -p "${ARCHIVE_DIR}/raw"
mkdir -p "${ARCHIVE_DIR}/processed"
mkdir -p "${ARCHIVE_DIR}/reports"
mkdir -p "${ARCHIVE_DIR}/charts"

cp data/raw/news_daily.csv "${ARCHIVE_DIR}/raw/news_daily.csv"
cp data/raw/policy_daily.csv "${ARCHIVE_DIR}/raw/policy_daily.csv"
cp data/raw/market_daily.csv "${ARCHIVE_DIR}/raw/market_daily.csv"

cp data/processed/industry_metrics_long.csv "${ARCHIVE_DIR}/processed/industry_metrics_long.csv"

cp reports/industry_report.md "${ARCHIVE_DIR}/reports/industry_report.md"
cp reports/industry_score.csv "${ARCHIVE_DIR}/reports/industry_score.csv"

cp charts/industry_score_bar.png "${ARCHIVE_DIR}/charts/industry_score_bar.png"

git add -f docs/ reports/ charts/ data/ archives/

if git diff --cached --quiet; then
  echo "No changes to commit"
else
  git commit -m "Daily update industry tracker report ${TODAY}"
  if ! git push; then
    log "ERROR: git push failed; static publishing did not complete."
    exit 1
  fi
  log "Daily update committed and pushed successfully."
fi
