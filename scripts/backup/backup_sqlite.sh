#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Environment variable BACKUP_PASSPHRASE must be set}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DB_PATH="${DB_PATH:-${PROJECT_ROOT}/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/sqlite-${TIMESTAMP}.tar.gz.enc"

mkdir -p "${BACKUP_DIR}"

echo "Creating encrypted SQLite backup at ${OUTPUT_FILE}"
tar -C "$(dirname "${DB_PATH}")" -czf - "$(basename "${DB_PATH}")" \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "${OUTPUT_FILE}"

echo "Backup complete"
