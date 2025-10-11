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

## Deployment

The deployment script (`scripts/deploy.sh`) installs these files into the
system-level Nginx directory and reloads the service. If the infrastructure uses
containers (e.g. Docker), mount the files as read-only volumes inside the proxy
container and reload Nginx.

Example:

```bash
cd /path/to/uniquememory
sudo ./scripts/deploy.sh
```

## ModSecurity notes

- The configuration expects the OWASP Core Rule Set (CRS) to be installed under
  `/etc/nginx/modsec/crs`. Install it before running the deployment script. For
  example:

  ```bash
  sudo mkdir -p /etc/nginx/modsec
  cd /etc/nginx/modsec
  sudo git clone https://github.com/coreruleset/coreruleset.git crs
  sudo cp crs/crs-setup.conf.example crs/crs-setup.conf
  ```

  Adjust the `Include` paths in `modsecurity.conf` if you use a different
  location. Refer to the [official CRS installation guide](https://coreruleset.org/docs/deployment/)
  for additional deployment options and tuning advice.
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
