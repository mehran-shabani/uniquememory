# Nginx WAF, IDS, and TLS Hardening

This directory contains hardened configuration snippets for the public Nginx
entrypoint. The goal is to ensure that application traffic is protected by
ModSecurity (acting as a combined WAF/IDS) and to enforce modern TLS defaults.

## Files

- `site.conf` – primary server block referencing the TLS and ModSecurity
  snippets. Includes baseline security headers and rate limiting for the API.
- `modsecurity.conf` – ModSecurity v3 configuration with OWASP CRS integration
  and safe defaults for blocking sensitive payloads.
- `tls.conf` – opinionated TLS configuration that enforces TLS 1.2+, strong
  ciphers, OCSP stapling, and secure session resumption settings.

## Prerequisites

Before deploying these snippets ensure the following dependencies are installed
and configured on the target host:

- **ModSecurity v3 with the Nginx connector.** On Debian/Ubuntu systems install
  it with `sudo apt install libnginx-mod-security`. For other distributions
  consult the vendor packages or build instructions from the
  [ModSecurity project](https://github.com/SpiderLabs/ModSecurity).
- **OWASP Core Rule Set (CRS) under `/etc/nginx/modsec/crs`.** You can install
  it either from the distribution package (`sudo apt install modsecurity-crs`) or
  manually by cloning the upstream repository:

  ```bash
  sudo mkdir -p /etc/nginx/modsec
  cd /etc/nginx/modsec
  sudo git clone https://github.com/coreruleset/coreruleset.git crs
  sudo cp crs/crs-setup.conf.example crs/crs-setup.conf
  ```

  The `modsecurity.conf` snippet includes the CRS using the exact paths:

  ```
  Include "/etc/nginx/modsec/crs/crs-setup.conf"
  Include "/etc/nginx/modsec/crs/rules/*.conf"
  ```

  Update these directives if you install the CRS to a different location.
- **Directory and file permissions.** Ensure the following ownership and modes
  so that only privileged users can modify the rules while Nginx can read them:

  | Path | Purpose | Owner:Group | Mode |
  | ---- | ------- | ----------- | ---- |
  | `/etc/nginx/modsec/` | Base ModSecurity directory | `root:root` | `0750` |
  | `/etc/nginx/modsec/crs/` | OWASP CRS checkout | `root:root` | `0750` |
  | `/etc/nginx/modsec/modsecurity.conf` | Main ModSecurity config | `root:root` | `0640` |
  | `/etc/nginx/modsec/crs/crs-setup.conf` | CRS tuning file | `root:root` | `0640` |

  Adjust ownership if your distribution expects the `nginx` group instead of
  `root` for read access.
- **Configuration variables.** Tune `SecRuleEngine` in `modsecurity.conf`
  (`DetectionOnly` during testing, `On` for blocking) and customize
  `crs/crs-setup.conf` to enable or disable rule sets that suit your
  application.
- **Rule maintenance.** When installed from git, update CRS rules with
  `sudo git -C /etc/nginx/modsec/crs pull`. When installed from packages, update
  via the operating system's package manager.
- Refer to the [official CRS installation guide](https://coreruleset.org/docs/deployment/)
  for distribution-specific instructions and advanced tuning strategies.

## Deployment

The deployment script (`scripts/deploy.sh`) installs these files into the
system-level Nginx directory and reloads the service. If the infrastructure uses
containers (e.g. Docker), mount the files as read-only volumes inside the proxy
container and reload Nginx. The script validates that the CRS directory exists
before copying files.

Example:

```bash
cd /path/to/uniquememory
sudo ./scripts/deploy.sh
```

After the files are installed, validate and reload Nginx to pick up the new
rules:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## ModSecurity notes

- Use the `SecRuleEngine DetectionOnly` setting during initial rollout to tune
  false positives, then switch to `On` once satisfied.
- Audit logs are written to `/var/log/modsec_audit.log` by default; ensure
  logrotate is configured for this file.

## TLS operations

- Provision certificates with your preferred ACME provider and store them in
  `/etc/nginx/tls/`. Update the `ssl_certificate` paths in `site.conf` if a
  different location is used.
- The configuration enables OCSP stapling and sets HSTS to one year. Enable the
  `preload` directive only after confirming that every subdomain is served over
  HTTPS and you are ready to submit the domain to the preload list.
- Session tickets are disabled to avoid long-term key reuse. If you enable them,
  rotate the ticket keys frequently.
