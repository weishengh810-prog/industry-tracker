#!/usr/bin/env bash
set -e

cd /home/admin/industry-tracker

source .venv/bin/activate

python scripts/run_pipeline.py
python scripts/store_to_db.py
python scripts/export_static.py

TODAY=$(date +%F)
ARCHIVE_DIR="archives/${TODAY}"

mkdir -p "${ARCHIVE_DIR}/raw"
mkdir -p "${ARCHIVE_DIR}/processed"
mkdir -p "${ARCHIVE_DIR}/reports"
mkdir -p "${ARCHIVE_DIR}/charts"
mkdir -p logs

cp data/raw/news_daily.csv "${ARCHIVE_DIR}/raw/news_daily.csv"
cp data/raw/policy_daily.csv "${ARCHIVE_DIR}/raw/policy_daily.csv"
cp data/raw/market_daily.csv "${ARCHIVE_DIR}/raw/market_daily.csv"

cp data/processed/industry_metrics_long.csv "${ARCHIVE_DIR}/processed/industry_metrics_long.csv"

cp reports/industry_report.md "${ARCHIVE_DIR}/reports/industry_report.md"
cp reports/industry_score.csv "${ARCHIVE_DIR}/reports/industry_score.csv"

cp charts/industry_score_bar.png "${ARCHIVE_DIR}/charts/industry_score_bar.png"

git add -f reports/industry_report.md \
  reports/industry_score.csv \
  charts/industry_score_bar.png \
  data/processed/industry_metrics_long.csv \
  data/raw/news_daily.csv \
  data/raw/policy_daily.csv \
  data/raw/market_daily.csv \
  "${ARCHIVE_DIR}" \
  scripts/daily_update.sh

git add docs/

if git diff --cached --quiet; then
  echo "No changes to commit"
else
  git commit -m "Daily update industry tracker report ${TODAY}"
  git push
fi
