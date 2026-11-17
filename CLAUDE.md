# Wegweiser – Projektkontext für Claude Code

## Ziel
Ein kleines, selbst gehostetes Web-Tool, das **druckfertige Wegbeschreibungen** (A4) von festen Standorten zu Einrichtungen (Krankenhäuser, Arztpraxen, Behörden usw.) erzeugt.
Es ersetzt den bisherigen Ablauf: Google-Maps-Druckansicht → Screenshot in Word-Vorlage → Überschrift anpassen → QR-Code einfügen.

Open-Source-Projekt (EUPL-1.2). Jede Organisation betreibt ihre eigene Instanz; es gibt keinen zentralen Dienst. Keine öffentliche Erreichbarkeit der Instanzen.

## Zielplattform
- Kleiner Linux-Server, NAS oder alter Rechner mit Docker; dort laufen oft andere Dienste → Ressourcen schonen, Ports nicht kollidieren lassen
- Zugriff nur im internen Netz bzw. per VPN – **keine Portfreigabe ins Internet**
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
   - Ausgabe über die Druckfunktion des Browsers („Als PDF speichern“) mit sauberem `@media print`-CSS

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
| ÖPNV (später, selbst gehostet) | NVBW-GTFS „bwgesamt“ (ODbL) mit MOTIS oder OpenTripPlanner | Lizenzhinweis ODbL / NVBW |

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
- **Keine echten Adressen von Unterkünften** (Standorten) in Code, Tests, Screenshots, Commits oder Issues – nur Beispieldaten; Adressen von Unterkünften für Geflüchtete sind schutzbedürftig
- Auf dem Zielserver laufen andere Dienste: keine Docker-Befehle ausführen, die fremde Container, Netzwerke oder Volumes betreffen (kein `docker system prune` o. Ä.)

## Offene Entscheidungen
- Port und Hostname im Heimnetz
- Kartenkachel-Anbieter für den Druck (OSM-Standard vs. Alternative)
- Druck nur über den Browser oder zusätzlich serverseitiges PDF (z. B. WeasyPrint/Playwright)
- Zeitpunkt für den Umstieg auf selbst gehostetes Routing und ÖPNV
