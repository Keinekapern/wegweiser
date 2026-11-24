# Wegweiser – Projektkontext für Claude Code

## Ziel
Ein kleines, selbst gehostetes Web-Tool, das **druckfertige Wegbeschreibungen** (A4) von festen Standorten zu Einrichtungen (Krankenhäuser, Arztpraxen, Behörden usw.) erzeugt.
Es ersetzt den bisherigen Ablauf: Google-Maps-Druckansicht → Screenshot in Word-Vorlage → Überschrift anpassen → QR-Code einfügen.

Open-Source-Projekt (EUPL-1.2). Jede Organisation betreibt ihre eigene Instanz; es gibt keinen zentralen Dienst. Instanzen sind nie ohne Zugangskontrolle aus dem Internet erreichbar.

## Zielplattform
- Kleiner Linux-Server, NAS oder alter Rechner mit Docker; dort laufen oft andere Dienste → Ressourcen schonen, Ports nicht kollidieren lassen
- Zugriff im internen Netz, per VPN oder über einen Tunnel mit Zugangskontrolle (z. B. Cloudflare Tunnel + Access) – **keine Portfreigabe ins Internet**, nie ohne Login erreichbar
- Private Angaben zum eigenen Server stehen in `CLAUDE.local.md` (nicht im Repo)
- Deployment über `docker compose`

## Funktionen

### MVP (Phase 1)
1. **Standorte verwalten**: feste Startpunkte (Name, Adresse, Koordinaten), auswählbar per Dropdown
2. **Ziele verwalten**: gespeicherte Zielliste (Name, Adresse, Koordinaten, Telefon, Website, Öffnungszeiten, geprüfter Google-Maps-Link, Notiz)
   - Neues Ziel per Suche (Name oder Adresse) → Treffer auswählen → Daten aus OSM vorbefüllen → manuell korrigieren → speichern
3. **Route berechnen** (Auto und/oder zu Fuß) und auf einer Karte darstellen
4. **Druckansicht A4**:
   - Überschrift = Name des Ziels
   - Karte mit Route, Start- und Zielmarker
   - Adresse und Kontaktdaten des Ziels
   - QR-Codes (siehe unten)
   - Erstellungsdatum und Quellenangaben (Pflicht, siehe Datenquellen)
   - sauberes `@media print`-CSS; Ausgabe über die Druckfunktion des Browsers oder als Server-PDF (Button „Als PDF“, siehe Punkt 6)
5. **Rechte**: Ohne Anmeldung Wegbeschreibungen erstellen und neue Ziele anlegen (Status „pending“, sofort nutzbar, im selben Browser korrigierbar). Admins (Konten in der DB, `app/auth.py`, erstes Konto per `python -m app.admin_cli`) bestätigen neue Ziele und dürfen allein bearbeiten, löschen, Standorte anlegen, Ziele Standorten zuordnen und ÖPNV-Standardwerte speichern. Jede ändernde Aktion ist ein POST; Cookies SameSite=Lax. `AUTH_MODE=off` schaltet die Anmeldung ganz ab (eigener PC); `AUTH_MODE=users`: alle melden sich an, Rollen admin/manager/staff mit Standorten (Konten in Tabelle `admins`, Standorte in `admin_locations`), Startpasswort muss beim ersten Login geändert werden, der PDF-Renderer kommt über `auth.render_token()` an der Anmeldung vorbei. **Rechte nur über `auth.can(request, "<aktion>")` / `auth.require(...)` bzw. `Allowed("<aktion>")` prüfen**, nie direkt über `current_user` oder Rollen. Mehrere Organisationen = mehrere Instanzen, keine Mandantenfähigkeit.
6. **Server-PDFs und Massenexport** (`app/services/pdf.py`, `export.py`, Namen in `app/export_names.py`): Playwright/Chromium rendert die Druckansicht (wartet auf `<html data-print-ready>`), Kacheln laufen über einen Disk-Cache (7 Tage, gedrosselt); immer nur ein Browser gleichzeitig. Tests nutzen einen Fake-Renderer.
7. **Regionale Zusätze** (`app/regions/<key>/region.json` + Dateien, Loader `app/regions.py`): alles, was nur für eine Stadt gilt (z. B. TüBus-Liniensymbole und -farben), gehört in einen solchen Zusatz, nicht in Kern-Code oder Migrationen; abschaltbar über `REGIONS`. Linien ohne Farbe: Farbe nach Verkehrsmittel (DB-Beschilderung, `transit.MODE_COLORS`).

### Phase 2: ÖPNV
- ÖPNV-Verbindung vom Standort zum Ziel
- Auf dem Ausdruck: Starthaltestelle, Linie(n) mit Fahrtrichtung, Umstiege, **Zielhaltestelle**, Fußweg Haltestelle → Ziel auf der Karte
- Lieber Takt („alle 30 Min.“) als konkrete Abfahrtszeiten; Hinweis „Stand: <Datum>, Fahrplanänderungen möglich“
- **Im Interface einstellbar** (als Standardwerte speicherbar und pro Ausdruck änderbar):
  - maximale Umstiege
  - maximaler Fußweg zur Start- und zur Zielhaltestelle (Zeit oder Entfernung)
  - erlaubte Verkehrsmittel (z. B. nur Bus, Bus + Bahn)
  - Barrierefreiheit (rollstuhlgerecht)
  - Referenz-Wochentag und -Uhrzeit für die Suche

### Phase 3: Komfort (optional)
- Mehrere Kartenanbieter-Links über eine statische Auswahlseite (siehe QR-Codes)
- Eigene Hosts für Routing (OSRM/Valhalla) und ÖPNV (MOTIS mit NVBW-GTFS) auf dem eigenen Server
- Vorlagen-Layouts, Logo

## QR-Codes / Kartenanbieter
Die Person, die den Ausdruck bekommt, soll ihren Kartenanbieter selbst wählen können. Stufenweise umsetzen:
1. **MVP**: mehrere kleine, beschriftete QR-Codes (Google Maps, OpenStreetMap, ggf. Apple Karten)
   - Google: Maps-URLs ohne API-Key, `https://www.google.com/maps/search/?api=1&query=...` (optional `query_place_id`); wenn ein geprüfter Link gespeichert ist, diesen verwenden
2. **Später**: ein einziger QR-Code auf eine **statische** Auswahlseite (GitHub/Codeberg Pages, nicht auf der Wegweiser-Instanz), Parameter (Name, lat, lon, optional Google-Link) im URL
- QR-Codes **lokal** erzeugen (JS- oder Python-Bibliothek), keinen externen QR-Dienst aufrufen

## Datenquellen und Nutzungsregeln (unbedingt einhalten)
| Zweck | Quelle | Regeln |
|---|---|---|
| Kartenkacheln | OSM-Standardkacheln (tile.openstreetmap.org) oder alternativer Anbieter | Attribution „© OpenStreetMap-Mitwirkende“ sichtbar, auch auf dem Ausdruck; gültiger Referer/User-Agent; **kein Vorab-/Massendownload** |
| Geocoding | Nominatim (öffentlich) oder openrouteservice/Pelias | Nominatim: max. 1 Anfrage/s, aussagekräftiger User-Agent, nur nutzerausgelöst, **Ergebnisse cachen** |
| Auto-/Fußrouten | openrouteservice (HeiGIT), kostenloser Standard-Plan | API-Key nur serverseitig; Tageslimits beachten (ca. 2.000 Routen, 1.000 Geocodings); **aktuelle Basis-URL prüfen** (alte api.openrouteservice.org wird laut Drittquelle abgeschaltet, neu vermutlich api.heigit.org) |
| ÖPNV | Transitous (öffentliche MOTIS-2-API, `https://api.transitous.org/api/`) | Nur nicht-kommerziell; User-Agent mit App-Name, Version und Kontakt; > 720 `/plan`-Anfragen pro Tag nur nach Absprache; Antworten cachen; aktuelle API-Version aus der OpenAPI-Spezifikation nehmen |
| ÖPNV (selbst gehostet) | NVBW-GTFS „bwgesamt“ mit MOTIS | Datenlizenz Deutschland – Namensnennung 2.0: „Datensatz der NVBW GmbH“ mit Link auf https://www.nvbw.de/open-data; Fahrplan gilt jeweils nur bis zum nächsten Fahrplanwechsel |

- Externe APIs **nur über das Backend** aufrufen (Keys geheim halten, zentral cachen und drosseln)
- Keine personenbezogenen Daten (z. B. Patientendaten) an externe Dienste senden – nur Adressen und Einrichtungen
- Google-Places-API wird **nicht** genutzt; Öffnungszeiten usw. kommen aus OSM-Tags (`opening_hours`, `phone`, `website`) plus manueller Pflege

## Architektur (Vorschlag, bei Bedarf begründet abweichen)
- **Backend**: Python 3.12 + FastAPI, `httpx` für externe Aufrufe
- **Datenbank**: SQLite (Standorte, Ziele, Einstellungen, Cache-Tabellen)
- **Frontend**: serverseitig ausgelieferte HTML-Seiten + Vanilla JS, Leaflet für die Karte; kein schweres Framework, kein Build-Schritt, wenn vermeidbar
- **Druck**: eigene Druckansicht mit `@media print`, A4 hochformatig; die Karte muss beim Drucken vollständig geladen sein (vor dem Drucken auf das Laden der Kacheln warten)
- **Container**: ein `Dockerfile` + `docker-compose.yml`; SQLite-Datei auf einem Volume unter `./data/`
- **Konfiguration**: `.env` (nicht im Repo) + `.env.example` (im Repo, ohne echte Werte)

Vorgeschlagene Struktur:
```
app/
  main.py          # FastAPI-App, Routen
  db.py            # SQLite-Zugriff
  services/        # geocoding.py, routing.py, transit.py, qr.py
  templates/       # HTML (Jinja2)
  static/          # JS, CSS, Leaflet
tests/
data/              # SQLite, nicht im Repo
docker-compose.yml
Dockerfile
.env.example
```

## Arbeitsweise für Claude
- Sprache der Oberfläche: **Deutsch** (Standard) und Englisch, Texte in `app/i18n.py` (deutsche Texte sind die Schlüssel); Code, Bezeichner und Commits: Englisch
- Sprache der Wegbeschreibung (Abbiegehinweise, Beschriftungen auf dem Ausdruck): alle von openrouteservice unterstützten Sprachen, wählbar pro Wegbeschreibung
- In kleinen, lauffähigen Schritten arbeiten; nach jedem Schritt kurz sagen, was getestet werden kann
- Vor neuen Abhängigkeiten oder Architekturänderungen kurz nachfragen
- Externe APIs in Tests mocken; keine echten API-Aufrufe in automatisierten Tests
- Secrets niemals committen; `.env` steht in `.gitignore`
- Bei Unsicherheit über aktuelle API-Details (Endpunkte, Parameter, Limits) die offizielle Doku bzw. OpenAPI-Spezifikation prüfen statt raten
- **Keine echten Adressen von Unterkünften** (Standorten) in Code, Tests, Screenshots, Commits oder Issues – nur Beispieldaten; nicht jede Unterkunft ist öffentlich bekannt (dezentrale oder geschützte Unterkünfte), und im öffentlichen Repo soll das niemand einzeln prüfen müssen
- Auf dem Zielserver laufen andere Dienste: keine Docker-Befehle ausführen, die fremde Container, Netzwerke oder Volumes betreffen (kein `docker system prune` o. Ä.)

## Offene Entscheidungen
- Kartenkachel-Anbieter für den Druck: vorerst OSM-Standard (`TILE_URL` umstellbar); Wechsel erst bei vielen Standorten oder wenn Verfügbarkeit zugesichert sein muss
