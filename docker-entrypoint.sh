#!/bin/sh
# Make the data directory writable for the app user (Docker creates bind-mount
# directories as root), then drop root privileges before starting the app.
set -e

DB_DIR="$(dirname "${DATABASE_PATH:-/data/wegweiser.sqlite}")"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DB_DIR"
    chown -R appuser:appuser "$DB_DIR"
    # Backup folder (may be on a drive without Unix owners, e.g. exFAT: then it must
    # already be writable, and the app reports failed backups on the backup page)
    if [ -n "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR" && chown -R appuser:appuser "$BACKUP_DIR" 2>/dev/null \
            || echo "Note: could not take ownership of $BACKUP_DIR" >&2
    fi
    exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi

exec "$@"
