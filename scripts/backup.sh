#!/usr/bin/env bash
# ============================================================
# TimescaleDB daily backup script
# Usage: ./scripts/backup.sh
# Set up as a cron job: 0 3 * * * /opt/bot-auto-trade-ig/scripts/backup.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS=7

# Load .env
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

DB_NAME="${DB_NAME:-trading_db}"
DB_USER="${DB_USER:-trader}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup of ${DB_NAME}..."

# Run pg_dump inside the timescaledb container and compress
docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T timescaledb \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges \
    | gzip > "$BACKUP_FILE"

# Verify backup
if [ -s "$BACKUP_FILE" ]; then
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup completed: ${BACKUP_FILE} (${SIZE})"
else
    echo "[$(date)] ERROR: Backup file is empty!"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Clean up old backups
echo "[$(date)] Removing backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete

REMAINING=$(find "$BACKUP_DIR" -name "*.sql.gz" | wc -l)
echo "[$(date)] Done. ${REMAINING} backup(s) retained."
