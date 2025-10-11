#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Environment variable BACKUP_PASSPHRASE must be set}"

umask "${BACKUP_UMASK:-077}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MEDIA_ROOT="${MEDIA_ROOT:-${PROJECT_ROOT}/media}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz.enc"

if [[ ! -d "${MEDIA_ROOT}" ]]; then
    echo "Media directory ${MEDIA_ROOT} does not exist" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "Creating encrypted media backup at ${OUTPUT_FILE}"
tar -C "${MEDIA_ROOT}" -czf - . \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "${OUTPUT_FILE}"

echo "Backup complete"
