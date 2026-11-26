# Eigene Server für Routen und ÖPNV

Wegweiser nutzt standardmäßig öffentliche Dienste (Transitous, openrouteservice von HeiGIT). Für kommerzielle oder größere Nutzung sind diese nicht gedacht. Dieses Verzeichnis enthält eine Vorlage, mit der man beide Dienste selbst betreibt:

- **MOTIS 2** für Bus und Bahn, mit den Fahrplandaten der NVBW für Baden-Württemberg
- **openrouteservice** für Fußwege, mit dem OpenStreetMap-Auszug von Geofabrik

Andere Regionen gehen genauso: `GTFS_URL` und `OSM_URL` auf andere Daten setzen, etwa DELFI-GTFS für Deutschland.

## Bedarf (gemessen für Baden-Württemberg, November 2026)

| | Aufbau (einmalig bzw. bei neuen Daten) | Betrieb |
|---|---|---|
| MOTIS | ca. 6 Min. beim ersten Import (davon 4–5 Min. Busverläufe), danach ca. 1 Min.; bis 4,7 GB RAM | ca. 0,6 GB RAM |
| openrouteservice | ca. 2 Min., bis 2,5 GB RAM | ca. 0,65 GB RAM |
| Speicherplatz | ca. 4,5 GB inkl. Rohdaten (MOTIS 2,8 GB, openrouteservice 0,3 GB, Rohdaten 1,3 GB) | |

Für den Betrieb reichen also 2 GB RAM, für den Aufbau sind 5 GB freier Arbeitsspeicher nötig. Beide Aufbauschritte laufen nacheinander.

Die Einstellungen sind auf Wegweiser zugeschnitten (Fußwege innerhalb von Orten, wenige Anfragen):

- openrouteservice baut nur das Profil zu Fuß, ohne Höhendaten und ohne Beschleunigungsstrukturen (Landmarks). Die Graphen bleiben auf der Platte (`graphs_data_access: MMAP`); im Arbeitsspeicher landet nur, was Anfragen tatsächlich lesen, also die Umgebung der Standorte und Ziele. Fußwege antworten in 20–30 ms (3 km) bzw. ca. 90 ms (12 km).
- MOTIS importiert den Fahrplan für 30 Tage ab dem Importtag; `update.sh` importiert deshalb spätestens alle 14 Tage neu, auch ohne neuen Fahrplan.
- Fernverkehr lässt sich in Wegweiser abwählen (ÖPNV-Einstellungen), er muss dafür nicht aus den Daten entfernt werden.

### Ganz Deutschland (Test November 2026)

Mit denselben Einstellungen, auf einem Server mit 4 Kernen und höchstens 5 GB RAM für den Aufbau:

| | Aufbau | Betrieb |
|---|---|---|
| openrouteservice (Geofabrik `germany-latest`, 4,9 GB) | ca. 63 Min. bei 5 GB RAM (mit mehr Speicher schneller) | ca. 1–1,3 GB RAM, 1,9 GB Platte; Fußwege 15–130 ms |
| MOTIS (gtfs.de Nahverkehr) | Test läuft noch | |

Für Deutschland kann man den Aufbau auch auf einem größeren Rechner machen und die Verzeichnisse `ors/graphs` und `motis/data` auf den Server kopieren.

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
./update.sh          # neuer Fahrplan? -> MOTIS neu importieren (ÖPNV ca. 2–6 Min. nicht verfügbar)
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

- Die Linienverläufe im NVBW-Fahrplan springen oft in gerader Linie von Haltestelle zu Haltestelle (Stand November 2026 bei rund der Hälfte aller Verläufe mindestens ein Sprung über 300 m), etwa quer über Bahnhofsgleise. Für Busse berechnet MOTIS die Verläufe deshalb selbst aus OpenStreetMap (`route_shapes` in `motis/config.yml`, Busprofil mit Busspuren und Busschleusen); Straßenbahn und Bahn behalten die Verläufe aus dem Fahrplan. Die berechneten Verläufe landen in einem Zwischenspeicher, spätere Importe rechnen nur Geändertes neu.
- Der NVBW-Fahrplan enthält keine Linienfarben. `update.sh` ergänzt sie aus der Sammlung [Traewelling/line-colors](https://github.com/Traewelling/line-colors) (CC0). Die Betreiber heißen dort anders als bei der NVBW und werden deshalb über ihre Liniennummern zugeordnet, nur bei eindeutigem Ergebnis (Stand November 2026: rund 1.700 von 3.800 Linien, darunter alle großen Stadtverkehre). Linien ohne Farbe erscheinen in der Standardfarbe. Falsche oder fehlende Zuordnungen lassen sich in `line-colors-aliases.csv` korrigieren; fehlende Farben am besten direkt bei Traewelling ergänzen, dann profitieren alle davon.
- Keine Echtzeitdaten (Verspätungen); für Wegbeschreibungen mit Takt ist das nicht nötig.
