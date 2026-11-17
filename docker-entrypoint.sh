#!/bin/sh
# Make the data directory writable for the app user (Docker creates bind-mount
# directories as root), then drop root privileges before starting the app.
set -e

DB_DIR="$(dirname "${DATABASE_PATH:-/data/wegweiser.sqlite}")"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DB_DIR"
    chown -R appuser:appuser "$DB_DIR"
    exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi

exec "$@"
