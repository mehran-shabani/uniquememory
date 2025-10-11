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

copy_if_different() {
    local source_file="$1"
    local dest_file="$2"
    if [[ ! -f "${dest_file}" ]] || ! cmp -s "${source_file}" "${dest_file}"; then
        install -D -m 0640 "${source_file}" "${dest_file}"
        echo "Updated ${dest_file}"
    else
        echo "No changes for ${dest_file}"
    fi
}

echo "==> Installing ModSecurity configuration"
install -d -m 0750 "${MODSEC_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/modsecurity.conf" "${MODSEC_DIR}/modsecurity.conf"

if [[ ! -d "${MODSEC_DIR}/crs" ]]; then
    echo "WARNING: OWASP CRS directory ${MODSEC_DIR}/crs is missing."
fi

echo "==> Installing TLS snippet"
install -d -m 0750 "${TLS_SNIPPETS_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/tls.conf" "${TLS_SNIPPETS_DIR}/tls-hardening.conf"

NGINX_SITE_PATH="${SITES_AVAILABLE_DIR}/uniquememory.conf"
echo "==> Installing Nginx site configuration (${NGINX_SITE_PATH})"
install -d -m 0750 "${SITES_AVAILABLE_DIR}"
copy_if_different "${PROJECT_ROOT}/deploy/nginx/site.conf" "${NGINX_SITE_PATH}"

ln -sfn "${NGINX_SITE_PATH}" "${SITES_ENABLED_DIR}/uniquememory.conf"

if command -v nginx >/dev/null 2>&1; then
    echo "==> Testing Nginx configuration"
    sudo nginx -t
    echo "==> Reloading Nginx"
    sudo systemctl reload nginx
else
    echo "nginx command not found; skipping validation and reload."
fi

echo "Deployment complete. Ensure certificates exist at /etc/nginx/tls/${SERVER_NAME}.crt and .key."
