#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NGINX_DIR="${NGINX_DIR:-/etc/nginx}"
MODSEC_DIR="${MODSEC_DIR:-${NGINX_DIR}/modsec}"
TLS_SNIPPETS_DIR="${TLS_SNIPPETS_DIR:-${NGINX_DIR}/snippets}"
SITES_AVAILABLE_DIR="${SITES_AVAILABLE_DIR:-${NGINX_DIR}/sites-available}"
SITES_ENABLED_DIR="${SITES_ENABLED_DIR:-${NGINX_DIR}/sites-enabled}"
SERVER_NAME="${SERVER_NAME:-uniquememory.internal}"

if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_BIN="sudo"
        if ! sudo -v; then
            echo "Unable to obtain sudo credentials" >&2
            exit 1
        fi
    else
        echo "This script must be run as root or with sudo" >&2
        exit 1
    fi
else
    SUDO_BIN=""
fi

run_privileged() {
    if [[ -n "${SUDO_BIN}" ]]; then
        "${SUDO_BIN}" "$@"
    else
        "$@"
    fi
}

copy_if_different() {
    local source_file="$1"
    local dest_file="$2"
    if ! run_privileged test -f "${dest_file}" || ! run_privileged cmp -s "${source_file}" "${dest_file}"; then
        run_privileged install -D -m 0640 "${source_file}" "${dest_file}"
        echo "Updated ${dest_file}"
    else
        echo "No changes for ${dest_file}"
    fi
}

echo "==> Installing ModSecurity configuration"
run_privileged install -d -m 0750 "${MODSEC_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/modsecurity.conf" "${MODSEC_DIR}/modsecurity.conf"

if ! run_privileged test -d "${MODSEC_DIR}/crs"; then
    echo "ERROR: OWASP CRS directory ${MODSEC_DIR}/crs is missing." >&2
    echo "Please install the OWASP Core Rule Set before continuing." >&2
    echo "See: https://github.com/coreruleset/coreruleset" >&2
    exit 1
fi

echo "==> Installing TLS snippet"
run_privileged install -d -m 0750 "${TLS_SNIPPETS_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/tls.conf" "${TLS_SNIPPETS_DIR}/tls-hardening.conf"

NGINX_SITE_PATH="${SITES_AVAILABLE_DIR}/uniquememory.conf"
echo "==> Installing Nginx site configuration (${NGINX_SITE_PATH})"
run_privileged install -d -m 0750 "${SITES_AVAILABLE_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/site.conf" "${NGINX_SITE_PATH}"

run_privileged install -d -m 0750 "${SITES_ENABLED_DIR}"
run_privileged ln -sfn "${NGINX_SITE_PATH}" "${SITES_ENABLED_DIR}/uniquememory.conf"

if command -v nginx >/dev/null 2>&1; then
    echo "==> Testing Nginx configuration"
    run_privileged nginx -t
    echo "==> Reloading Nginx"
    run_privileged systemctl reload nginx
else
    echo "nginx command not found; skipping validation and reload."
fi

echo "Deployment complete. Ensure certificates exist at /etc/nginx/tls/${SERVER_NAME}.crt and .key."
