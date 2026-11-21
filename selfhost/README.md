# Eigene Server für Routen und ÖPNV

Wegweiser nutzt standardmäßig öffentliche Dienste (Transitous, openrouteservice von HeiGIT). Für kommerzielle oder größere Nutzung sind diese nicht gedacht. Dieses Verzeichnis enthält eine Vorlage, mit der man beide Dienste selbst betreibt:

- **MOTIS 2** für Bus und Bahn, mit den Fahrplandaten der NVBW für Baden-Württemberg
- **openrouteservice** für Fußwege (und Auto), mit dem OpenStreetMap-Auszug von Geofabrik

Andere Regionen gehen genauso: `GTFS_URL` und `OSM_URL` auf andere Daten setzen, etwa DELFI-GTFS für Deutschland.

## Bedarf (gemessen für Baden-Württemberg, November 2026)

| | Aufbau (einmalig bzw. bei neuen Daten) | Betrieb |
|---|---|---|
| MOTIS | ca. 1,5 Min., bis 6 GB RAM | ca. 0,5 GB RAM |
| openrouteservice | ca. 15 Min., bis 5,5 GB RAM | ca. 1,6 GB RAM |
| Speicherplatz | ca. 6 GB inkl. Rohdaten | |

Für den Betrieb reichen also 4 GB RAM, für den Aufbau sind 8 GB freier Arbeitsspeicher nötig. Beide Aufbauschritte laufen nacheinander.

## Einrichten

```sh
cd selfhost
./update.sh          # lädt Fahrplan und Kartendaten, baut beide Dienste auf, startet sie
```

In der `.env` von Wegweiser dann:

```sh
TRANSITOUS_BASE_URL=http://host.docker.internal:8421
ORS_BASE_URL=http://host.docker.internal:8422/ors
ORS_API_KEY=
TRANSIT_ATTRIBUTION=Datensatz der NVBW GmbH
TRANSIT_ATTRIBUTION_URL=https://www.nvbw.de/open-data
ROUTE_ATTRIBUTION=openrouteservice
```

`host.docker.internal` ist der Rechner selbst, wenn Wegweiser auf demselben Rechner läuft (in `docker-compose.yml` eingetragen); sonst dessen IP-Adresse im internen Netz. Danach Wegweiser neu starten (`docker compose up -d`). Vorhandene Routen im Zwischenspeicher stammen noch von den öffentlichen Diensten; sie verfallen nach einigen Tagen von selbst. Ports lassen sich mit `MOTIS_PORT` und `ORS_PORT` ändern.

## Aktuell halten

Der NVBW-Fahrplan gilt jeweils nur bis zum nächsten Fahrplanwechsel (Mitte Dezember, oft auch im Juni). Das Skript lädt nur, was sich geändert hat, und warnt, wenn der Fahrplan in weniger als 14 Tagen abläuft.

```sh
./update.sh          # neuer Fahrplan? -> MOTIS neu importieren (ÖPNV ca. 2 Min. nicht verfügbar)
./update.sh --osm    # zusätzlich neue Kartendaten -> auch openrouteservice neu bauen
```

Vorschlag für `crontab -e` (nachts, Fahrplan wöchentlich, Karte monatlich):

```
0 3 * * 0   /pfad/zu/wegweiser/selfhost/update.sh       >> /pfad/zu/wegweiser/selfhost/update.log 2>&1
0 4 1 * *   /pfad/zu/wegweiser/selfhost/update.sh --osm >> /pfad/zu/wegweiser/selfhost/update.log 2>&1
```

Wegweiser speichert Verbindungen einige Tage zwischen (`TRANSIT_CACHE_DAYS`). Nach einem Fahrplanwechsel können ältere Antworten also noch kurz angezeigt werden.

## Lizenzen der Daten

- **Fahrplan:** Datensatz der NVBW GmbH, [Datenlizenz Deutschland – Namensnennung 2.0](https://www.nvbw.de/open-data/lizenz). Auf dem Ausdruck muss „Datensatz der NVBW GmbH“ mit Link stehen (siehe `TRANSIT_ATTRIBUTION`).
- **Karte und Wege:** © OpenStreetMap-Mitwirkende, ODbL. Steht immer auf dem Ausdruck.
- **Linienfarben:** Traewelling/line-colors, CC0 (keine Namensnennung nötig).
- **Software:** MOTIS (MIT), openrouteservice (GPL-3.0), unverändert als Docker-Images.

## Bekannte Einschränkungen

- Der NVBW-Fahrplan enthält keine Linienfarben. `update.sh` ergänzt sie aus der Sammlung [Traewelling/line-colors](https://github.com/Traewelling/line-colors) (CC0). Die Betreiber heißen dort anders als bei der NVBW und werden deshalb über ihre Liniennummern zugeordnet, nur bei eindeutigem Ergebnis (Stand November 2026: rund 1.700 von 3.800 Linien, darunter alle großen Stadtverkehre). Linien ohne Farbe erscheinen in der Standardfarbe. Falsche oder fehlende Zuordnungen lassen sich in `line-colors-aliases.csv` korrigieren; fehlende Farben am besten direkt bei Traewelling ergänzen, dann profitieren alle davon.
- Keine Echtzeitdaten (Verspätungen); für Wegbeschreibungen mit Takt ist das nicht nötig.
