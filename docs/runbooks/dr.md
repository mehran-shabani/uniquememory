# Disaster Recovery Runbook

This runbook outlines recovery procedures for the core uniquememory services and
data stores. Backups are generated via the scripts in `scripts/backup/` and are
stored encrypted using `openssl` with the `BACKUP_PASSPHRASE` environment
variable.

## Backup schedule

| Asset            | Script                                  | Frequency | Retention |
| ---------------- | --------------------------------------- | --------- | --------- |
| SQLite database  | `scripts/backup/backup_sqlite.sh`       | Hourly    | 30 days   |
| Media uploads    | `scripts/backup/backup_media.sh`        | Daily     | 14 days   |
| Graph dataset    | `scripts/backup/backup_graph.sh`        | Daily     | 30 days   |

Backups are written to `${BACKUP_DIR}` (defaults to `<project>/backups`). Ensure
that the destination is mounted to a secure, off-site object store for
redundancy.

## Recovery prerequisites

1. Obtain the `BACKUP_PASSPHRASE` from the secure secrets vault.
2. Ensure that `openssl`, `tar`, and `python3` are available on the recovery
   host.
3. Restore the repository from the latest release tag to guarantee script
   compatibility.

## Restoring the SQLite database

1. Copy the desired `sqlite-<timestamp>.tar.gz.enc` artifact onto the target
   host.
2. Decrypt and extract:

   ```bash
   export BACKUP_PASSPHRASE='<passphrase>'
   openssl enc -d -aes-256-cbc -pbkdf2 -in sqlite-<timestamp>.tar.gz.enc \
       | tar -xz -C /srv/uniquememory
   ```

3. Verify file permissions (`chmod 640 db.sqlite3`) and restart the Django
   application service.

## Restoring media files

1. Copy the selected `media-<timestamp>.tar.gz.enc` artifact.
2. Decrypt into the media root:

   ```bash
   export BACKUP_PASSPHRASE='<passphrase>'
   openssl enc -d -aes-256-cbc -pbkdf2 -in media-<timestamp>.tar.gz.enc \
       | tar -xz -C /srv/uniquememory/media
   ```

3. Re-run `collectstatic` if necessary and revalidate file ownership (usually
   `www-data:www-data`).

## Restoring graph data

1. Copy `graph-<timestamp>.json.enc` to the application host.
2. Decrypt to a temporary location:

   ```bash
   export BACKUP_PASSPHRASE='<passphrase>'
   openssl enc -d -aes-256-cbc -pbkdf2 -in graph-<timestamp>.json.enc -out /tmp/graph.json
   ```

3. Load the data via Django:

   ```bash
   python3 manage.py loaddata /tmp/graph.json
   ```

4. Remove the decrypted file when complete.

## Verification checklist

- Run `python3 manage.py check` to verify Django integrity.
- Execute smoke tests against the `/api/` endpoint and the consent portal.
- Confirm that the WAF (ModSecurity) and TLS certificates are active on the
  edge proxy using `curl -I https://<host>` and reviewing ModSecurity audit logs.

## DR exercise cadence

Conduct a full restore to a staging environment at least once per quarter and
update this runbook with any lessons learned.
