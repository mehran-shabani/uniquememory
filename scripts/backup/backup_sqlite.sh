#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Environment variable BACKUP_PASSPHRASE must be set}"

umask "${BACKUP_UMASK:-077}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DB_PATH="${DB_PATH:-${PROJECT_ROOT}/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
SQLITE3_BIN="${SQLITE3_BIN:-sqlite3}"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/sqlite-${TIMESTAMP}.tar.gz.enc"

if ! command -v "${SQLITE3_BIN}" >/dev/null 2>&1; then
    echo "sqlite3 binary ${SQLITE3_BIN} not found in PATH" >&2
    exit 1
fi

if [[ ! -f "${DB_PATH}" ]]; then
    echo "SQLite database ${DB_PATH} does not exist" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

TMP_DB_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DB_DIR}"' EXIT

DB_BASENAME="$(basename "${DB_PATH}")"
DB_SNAPSHOT_PATH="${TMP_DB_DIR}/${DB_BASENAME}"

echo "Creating consistent SQLite snapshot via online backup API"
"${SQLITE3_BIN}" "${DB_PATH}" ".backup '${DB_SNAPSHOT_PATH}'"

echo "Creating encrypted SQLite backup at ${OUTPUT_FILE}"
tar -C "${TMP_DB_DIR}" -czf - "${DB_BASENAME}" \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "${OUTPUT_FILE}"

echo "Backup complete"
