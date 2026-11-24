#!/usr/bin/env bash
# Downloads timetable (GTFS) and map data (OSM) and rebuilds MOTIS / openrouteservice.
#
#   ./update.sh            new timetable? -> MOTIS re-import (~2-6 min downtime for public transport)
#   ./update.sh --osm      also new map data -> MOTIS re-import and ORS graph rebuild (~15 min)
#   ./update.sh --force    re-import even if nothing changed
#
# First run: downloads everything and builds both services. Needs ~8 GB free RAM while
# building (MOTIS import ~6 GB, ORS build ~5.5 GB, one after the other) and ~6 GB disk.
# Only touches the containers of this compose project (wegweiser-motis, wegweiser-ors)
# and older versions of their images that no container uses.
set -euo pipefail
cd "$(dirname "$0")"

GTFS_URL=${GTFS_URL:-https://www.nvbw.de/fileadmin/user_upload/service/open_data/fahrplandaten_mit_liniennetz/bwgesamt.zip}
OSM_URL=${OSM_URL:-https://download.geofabrik.de/europe/germany/baden-wuerttemberg-latest.osm.pbf}
COLORS_URL=${COLORS_URL:-https://raw.githubusercontent.com/Traewelling/line-colors/refs/heads/main/line-colors.csv}
UA="wegweiser-selfhost-update/1.0"
export UID_GID=${UID_GID:-"$(id -u):$(id -g)"}

want_osm=0; force=0
for arg in "$@"; do
  case $arg in
    --osm) want_osm=1 ;;
    --force) force=1 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 2 ;;
  esac
done

log() { echo "$(date '+%F %T') $*"; }
mkdir -p downloads motis ors

# download URL FILE -> exit 0 if FILE was replaced by a newer version
download() {
  local url=$1 out=$2 tmp=$2.part
  rm -f "$tmp"
  local cond=()
  [ -s "$out" ] && cond=(-z "$out")
  if ! curl -fsSL --retry 3 -A "$UA" -R "${cond[@]}" -o "$tmp" "$url"; then
    rm -f "$tmp"; log "WARNUNG: Download fehlgeschlagen, alte Daten bleiben: $url"; return 1
  fi
  if [ ! -s "$tmp" ]; then rm -f "$tmp"; return 1; fi   # not modified
  if [[ $out == *.zip ]] && ! python3 -m zipfile -t "$tmp" >/dev/null; then
    rm -f "$tmp"; log "FEHLER: $url ist kein gültiges ZIP"; exit 1
  fi
  mv "$tmp" "$out"
}

gtfs_new=0; osm_new=0
log "Fahrplan prüfen: $GTFS_URL"
if download "$GTFS_URL" downloads/timetable.gtfs.zip; then gtfs_new=1; log "neuer Fahrplan geladen"; fi
if [ $want_osm = 1 ] || [ ! -s downloads/region.osm.pbf ]; then
  log "Kartendaten prüfen: $OSM_URL"
  if download "$OSM_URL" downloads/region.osm.pbf; then osm_new=1; log "neue Kartendaten geladen"; fi
fi
[ -d motis/data ] || force=1

# Line colours (the NVBW timetable has none): regenerate the MOTIS import script and
# re-import if it changed. A failed download keeps the previous colours.
download "$COLORS_URL" downloads/line-colors.csv || true
if [ -s downloads/line-colors.csv ]; then
  python3 line_colors.py downloads/timetable.gtfs.zip downloads/line-colors.csv \
    line-colors-aliases.csv motis/line-colors.lua.new
else
  echo "function process_route(route) end" > motis/line-colors.lua.new
fi
if ! cmp -s motis/line-colors.lua.new motis/line-colors.lua; then
  mv motis/line-colors.lua.new motis/line-colors.lua; force=1; log "Linienfarben geändert"
else
  rm motis/line-colors.lua.new
fi
[ -d ors/graphs/foot-walking ] || osm_new=1

if [ $gtfs_new = 1 ] || [ $osm_new = 1 ] || [ $force = 1 ]; then
  log "MOTIS: Import"
  docker compose stop motis >/dev/null 2>&1 || true
  if ! MOTIS_MEM_LIMIT=7g docker compose run --rm --no-deps motis /motis import >/dev/null; then
    docker compose up -d motis >/dev/null 2>&1 || true   # keep public transport available
    log "FEHLER: MOTIS-Import fehlgeschlagen (Ausgabe: docker compose run --rm motis /motis import)"
    exit 1
  fi
  docker compose up -d motis
  log "MOTIS: läuft wieder"
else
  log "MOTIS: nichts zu tun"
  docker compose up -d motis >/dev/null 2>&1   # make sure it runs (e.g. after a reboot or stop)
fi

if [ $osm_new = 1 ]; then
  log "openrouteservice: Graphen neu bauen (dauert etwa 15 Minuten)"
  ORS_REBUILD=True ORS_XMX=5g ORS_MEM_LIMIT=6g docker compose up -d --force-recreate ors
  for _ in $(seq 1 360); do
    curl -s -m 5 "http://localhost:${ORS_PORT:-8422}/ors/v2/health" | grep -q '"status":"ready"' && break
    sleep 10
  done
  curl -s -m 5 "http://localhost:${ORS_PORT:-8422}/ors/v2/health" | grep -q '"status":"ready"' \
    || { log "FEHLER: openrouteservice ist nach 60 Minuten nicht bereit (docker logs wegweiser-ors)"; exit 1; }
  docker compose up -d --force-recreate ors   # back to normal memory settings
  log "openrouteservice: fertig"
else
  docker compose up -d ors >/dev/null 2>&1
fi

# Old versions of this project's images (e.g. after a version bump in docker-compose.yml):
# only the repositories named in our compose file, only versions no container uses
cleanup_images() {
  local current repo ref id
  for current in $(docker compose config --images); do
    repo=${current%:*}
    docker images "$repo" --format '{{.Repository}}:{{.Tag}} {{.ID}}' | while read -r ref id; do
      [ "$ref" = "$current" ] && continue
      [ -n "$(docker ps -aq --filter "ancestor=$id")" ] && continue
      if [ "${ref##*:}" = "<none>" ]; then
        docker image rm "$id" >/dev/null 2>&1 && log "Altes Image entfernt: $repo ($id)"
      else
        docker image rm "$ref" >/dev/null 2>&1 && log "Altes Image entfernt: $ref"
      fi
    done
  done
}
cleanup_images

# Warn before the timetable runs out (NVBW data usually ends at the next timetable change)
end=$(python3 - <<'EOF'
import csv, io, zipfile
with zipfile.ZipFile("downloads/timetable.gtfs.zip") as z:
    if "feed_info.txt" in z.namelist():
        rows = list(csv.DictReader(io.TextIOWrapper(z.open("feed_info.txt"), "utf-8-sig")))
        print(rows[0].get("feed_end_date", "") if rows else "")
EOF
)
if [ -n "$end" ]; then
  days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 ))
  log "Fahrplan gültig bis $end (noch $days Tage)"
  [ "$days" -lt 14 ] && log "WARNUNG: Fahrplan läuft bald ab – neuer Fahrplan noch nicht veröffentlicht?"
fi
exit 0
