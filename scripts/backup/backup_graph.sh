#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Environment variable BACKUP_PASSPHRASE must be set}"

umask "${BACKUP_UMASK:-077}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/graph-${TIMESTAMP}.json.enc"
MANAGE_PY="${MANAGE_PY:-${PROJECT_ROOT}/manage.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "${BACKUP_DIR}"

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

echo "Dumping graph data via Django manage.py"
"${PYTHON_BIN}" "${MANAGE_PY}" dumpdata graph --indent 2 > "${TMP_FILE}"

echo "Encrypting graph backup to ${OUTPUT_FILE}"
openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -in "${TMP_FILE}" -out "${OUTPUT_FILE}"

echo "Backup complete"
