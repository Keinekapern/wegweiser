# Wegweiser

Wegweiser erstellt **leicht verständliche Wegbeschreibungen zum Ausdrucken**, für Menschen, die wenig Deutsch sprechen oder nicht gut lesen können: zum Beispiel geflüchtete Menschen, die neu in einer Stadt sind und den Weg zum Arzt, zur Apotheke, ins Krankenhaus oder zur Behörde finden müssen. Ziel ist eine barrierearme Hilfe, mit der Mitarbeitende in Unterkünften, Beratungsstellen oder Ehrenamtliche solche Wege schnell und verlässlich mitgeben können.

Dafür setzt der Ausdruck auf Bilder statt Text, wo immer es geht:

- **Karte** mit dem Weg, Start und Ziel, bei Bus und Bahn zusätzlich vergrößerte Karten der Fußwege zur ersten und von der letzten Haltestelle
- **Symbole** statt Worte: für die Art der Einrichtung, die Haltestellen, die Verkehrsmittel und, wo es sie gibt, die Bildzeichen der Buslinien
- **Linienfarben und -nummern** wie an der Haltestelle und auf dem Bus, Takt statt Abfahrtszeiten
- **in 28 Sprachen**, auch Arabisch, Persisch, Tigrinya, Ukrainisch oder Türkisch; die deutschen Namen von Haltestellen und Einrichtungen bleiben stehen, damit man sie auf den Schildern wiederfindet
- **QR-Codes**, mit denen sich das Ziel in der eigenen Karten-App öffnen lässt

Wegweiser ist Open Source und läuft selbst gehostet im eigenen Netz, ohne Konto für die Nutzenden und ohne Tracking. An externe Dienste gehen nur Adressen von Einrichtungen, nie Daten über Menschen.

![Druckansicht: Wegbeschreibung mit Straßenbahn von einer Unterkunft zum Kinder- und Jugendklinikum](docs/screenshots/print.png)

*Alle Screenshots zeigen Beispieldaten aus Freiburg im Breisgau. Die „Beispiel-Unterkunft“ ist ein frei gewählter Startpunkt.*

## Was der Ausdruck enthält

- **Ziel als Überschrift**, darunter die Art der Einrichtung oder ein übersetzter Name in der gewählten Sprache
- **Karte** mit Route, Start, Ziel und Haltestellen; bei ÖPNV zusätzlich **Detailkarten der Fußwege** zur ersten und von der letzten Haltestelle, so nah wie möglich herangezoomt
- **ÖPNV-Verbindung**: Fußweg, Linie mit Linienfarbe und Fahrtrichtung, Ein- und Ausstieg, Dauer, Takt („alle 15 Min.“) statt fester Abfahrtszeiten, dazu weitere Verbindungen
- **Adresse, Telefon, Website und Öffnungszeiten** des Ziels
- **QR-Codes** für Google Maps, OpenStreetMap und Apple Karten, damit jede Person ihre eigene Karten-App nutzen kann
- **Quellenangaben und Erstellungsdatum**, mit dem Hinweis, dass sich Fahrpläne ändern können

Ausgegeben wird über die Druckfunktion des Browsers („Als PDF speichern“) oder über „Als PDF“: Dann erstellt der Server das PDF, mit den gewählten Optionen. Die Druckansicht wartet, bis alle Kartenkacheln geladen sind. Hoch- und Querformat sowie eine Schwarz-Weiß-Variante sind wählbar.

## PDF-Export für viele Ziele und Sprachen

Unter „Export“ (nur Admins) erstellt Wegweiser die Wegbeschreibungen für ausgewählte Standorte, Ziele, Sprachen und Verkehrsmittel auf einmal und packt sie in eine ZIP-Datei. Je Standort wird nur erstellt, was dort angeboten wird. Der Export läuft im Hintergrund mit Fortschrittsanzeige (etwa 1–3 Sekunden je PDF), das ZIP steht danach eine Stunde zum Download bereit.

```
Wegweiser_2026-11-21_2-Standorte.zip
├── Übersicht.pdf                      Inhalt, Optionen, was nicht erstellt werden konnte
├── EA Tübingen/                       Standort-Ebene nur bei mehreren Standorten
│   └── CRONA-Kliniken/
│       ├── CRONA-Kliniken – Arabisch.pdf
│       ├── CRONA-Kliniken – Deutsch.pdf
│       └── CRONA-Kliniken – Persisch (Farsi).pdf
└── NUK Sindelfingen/
    └── …
```

Dateinamen: „Ziel – Sprache.pdf“, die Sprache ausgeschrieben in der Sprache der Oberfläche (auf Deutsch z. B. „Arabisch“, auf Englisch „Arabic“); bei mehreren Verkehrsmitteln zusätzlich „– ÖPNV“ bzw. „– zu Fuß“. Gleich benannte Ziele bekommen die Straße dazu. Namen sind Windows-tauglich (keine Sonderzeichen wie `/ : ?`, höchstens 80 Zeichen).

Die PDFs rendert ein Headless-Chromium (Playwright) im Container aus der Druckansicht. Kartenkacheln werden dabei auf dem Server 7 Tage zwischengespeichert und nur einzeln nacheinander geholt, damit auch große Exporte die Kachelserver nicht belasten; für sehr große oder häufige Exporte trotzdem einen eigenen oder kommerziellen Kachelanbieter verwenden (`TILE_URL`).

## Verständlich über Sprachgrenzen hinweg

Die Sprache der Wegbeschreibung ist pro Ausdruck wählbar, darunter Arabisch, Persisch, Türkisch, Ukrainisch, Russisch, Tigrinya und Somali (insgesamt 28 Sprachen). Rechts-nach-links-Sprachen werden richtig gesetzt. Deutsche Namen von Haltestellen und Einrichtungen bleiben stehen, damit man sie auf den Schildern vor Ort wiederfindet.

![Dieselbe Wegbeschreibung auf Arabisch](docs/screenshots/print-ar.png)

- **Abbiegehinweise** kommen von openrouteservice in dessen Sprachen, für weitere Sprachen erzeugt das Werkzeug sie aus eigenen Vorlagen.
- **Namen der Ziele**: Unter einem Eigennamen wie „Fielmann“ steht die Art der Einrichtung („Optiker“) in der gewählten Sprache. Übersetzbare Namen wie „Kinderklinik“ lassen sich pro Sprache hinterlegen, Vorschläge kommen aus OpenStreetMap.
- **Prüfseite** „Übersetzungen prüfen“: alle Texte einer Sprache auf einer Seite, zum Gegenlesen durch Muttersprachlerinnen und Muttersprachler.
- **Haltestellennamen** werden gekürzt, wenn Start und Ziel im selben Ort liegen („Paduaallee“ statt „Freiburg, Paduaallee“), wie auf den Anzeigen in Bus und Bahn.

## Symbole mit hohem Kontrast

Alle Symbole sind eigene, einfache Zeichnungen mit starkem Kontrast, auch für Menschen mit eingeschränktem Sehvermögen und im Schwarz-Weiß-Druck gut erkennbar.

- **Kategorie-Symbole** für Ziele zeigen konkrete Dinge statt Sinnbilder (Zahn, Brille, Stethoskop), ohne Buchstaben. Gestaltet wurden sie nach Erkenntnissen aus der Forschung zu kulturübergreifend verständlichen Piktogrammen. Die Farbe steht für die Gruppe: Gesundheit, Behörden, Bildung/Soziales, Religion, Alltag.
- **Ohne Kategorie** steht eine Ortsmarke als Umriss vor dem Namen, unbestätigte Ziele tragen in der Oberfläche eine Sanduhr (nicht auf dem Ausdruck).
- **Haltestellenschilder** je Verkehrsmittel: H für Bus und Straßenbahn, eigene Schilder für Bahn, U-Bahn, Fähre und Seilbahn.
- **Liniensymbole und Linienfarben** für Verkehrsbetriebe, deren Linien Bildzeichen tragen, kommen aus regionalen Zusätzen (siehe unten; zurzeit TüBus Tübingen). Die Symbole stehen hinter der Liniennummer in deren Schriftfarbe, wie auf den Bussen.
- **Linien ohne Farbe** bekommen eine Farbe nach Verkehrsmittel, angelehnt an die Beschilderung der Deutschen Bahn: S-Bahn grün, U-Bahn blau, Straßenbahn rot, Bus purpur, Züge und Sonstiges nachtblau.

![Übersicht der Kategorie-Symbole](docs/screenshots/symbols.png)

Die vollständige Übersicht liegt in der laufenden App unter `/static/symbol-preview.html`.

![Schwarz-Weiß-Druck](docs/screenshots/print-bw.png)

### Import und Export

Unter „Admin → Einstellungen → Ziele und Standorte importieren und exportieren“ lassen sich die Daten als Datei sichern, in eine andere Wegweiser-Instanz übernehmen oder in Excel bearbeiten:

- **JSON** enthält alles verlustfrei (übersetzte Namen, Kategorien, auf Wunsch Standorte und Zuordnungen) und eignet sich für den Austausch zwischen Instanzen.
- **CSV** öffnet Excel direkt: Semikolon als Trennzeichen, Koordinaten als „Breite, Länge“ in einer Spalte, übersetzte Namen als Spalten „Name (en)“ usw. Beim Import werden auch englische Spaltennamen, Komma als Trennzeichen und Excels Windows-Zeichensatz erkannt.
- Standorte (Adressen von Unterkünften) sind nur mit Häkchen im Export enthalten.
- Vor dem Import zeigt eine **Vorschau**, was neu ist, was es schon gibt (gleiches OpenStreetMap-Objekt, sonst gleicher Name und gleiche Adresse) und was abweicht; abweichende Einträge werden nur aktualisiert, wenn sie angehakt sind. Fehlerhafte Zeilen werden mit Grund übersprungen.

## Regionale Zusätze

Was nur für eine Stadt oder einen Verkehrsverbund gilt, liegt als Zusatz in `app/regions/<name>/`: eine `region.json` mit Gebiet, Verkehrsmitteln und je Linie Farbe und Bildzeichen, dazu die Symbol-Dateien. Mitgeliefert ist `tuebingen` (TüBus: Bildzeichen wie auf den Busanzeigen, Linienfarben aus dem Liniennetzplan, auch für Linien, die Subunternehmer fahren). Eine Linie bekommt Farbe und Symbol, wenn ihre Einstiegshaltestelle im Gebiet liegt.

Nicht benötigte Zusätze lässt man weg, indem man den Ordner löscht oder in `.env` `REGIONS=` setzt (`REGIONS=none` für keine, `REGIONS=tuebingen` für eine Auswahl; ohne Angabe gelten alle vorhandenen). Das Format steht in `app/regions.py`; neue Zusätze für andere Städte sind willkommen.

## Ziele und Standorte verwalten

Standorte (Startpunkte) und Ziele werden einmal angelegt und stehen danach per Auswahlliste bereit. Ein neues Ziel sucht man über Name oder Adresse in OpenStreetMap; Adresse, Koordinaten, Telefon, Website, Öffnungszeiten, Kategorie und übersetzte Namen werden vorbefüllt und lassen sich korrigieren. Ziele können einzelnen Standorten zugeordnet werden.

![Liste der Ziele](docs/screenshots/destinations.png)

## Admins und Rechte

Wie viel Rechteverwaltung nötig ist, hängt vom Betrieb ab. Die Betriebsart wird in `.env` mit `AUTH_MODE` gewählt:

| `AUTH_MODE` | Gedacht für | Rechte |
|---|---|---|
| `admin` (Standard) | eine Einrichtung oder ein Träger mit gemeinsamer Instanz, auch über Tunnel | Alle erstellen Wegbeschreibungen und schlagen Ziele vor; Admins bestätigen und verwalten (siehe unten) |
| `off` | den eigenen PC oder ein kleines, vertrauenswürdiges Büronetz | Keine Anmeldung, alle dürfen alles, neue Ziele sind sofort dauerhaft. Die Oberfläche weist darauf hin. Zusammen mit `CLOUDFLARE_TUNNEL_TOKEN` startet Wegweiser nicht. |

Mehrere Organisationen betreiben am besten je eine eigene Instanz (eigener Container, eigene Datenbank); die selbst gehosteten Dienste für Routen und Fahrpläne können sie sich teilen. Benutzerkonten mit Rollen je Standort für größere Träger sind vorbereitet, aber noch nicht umgesetzt.

In der Betriebsart `admin` kann ohne Anmeldung jede Person Wegbeschreibungen erstellen und neue Ziele anlegen. Neue Ziele sind sofort nutzbar, tragen aber den Vermerk „unbestätigt“, bis ein Admin sie auf der Admin-Seite bestätigt oder ablehnt. Bis dahin lassen sie sich im selben Browser noch korrigieren.

Nur Admins können bestehende Ziele und Standorte bearbeiten oder löschen, Standorte anlegen, Ziele bestimmten Standorten zuordnen, die ÖPNV-Standardwerte speichern und festlegen, welche Sprachen der Wegbeschreibung zur Auswahl stehen (Admin-Seite → Einstellungen; Deutsch ist immer dabei). Weitere Admins und das eigene Passwort verwaltet man auf der Admin-Seite.

Das erste Admin-Konto wird auf dem Server angelegt (fragt nach dem Passwort):

```sh
docker compose exec -u appuser wegweiser python -m app.admin_cli create <name>
```

Ebenso `password <name>`, `delete <name>` und `list`. Passwörter werden mit scrypt gespeichert; nach fünf Fehlversuchen ist die Anmeldung für 15 Minuten gesperrt.

## Datenquellen

Alle externen Dienste werden nur vom Server aus aufgerufen, gedrosselt und in SQLite zwischengespeichert. API-Schlüssel bleiben auf dem Server. An die Dienste gehen nur Adressen und Koordinaten, keine personenbezogenen Daten.

| Zweck | Quelle | Hinweise |
|---|---|---|
| Suche (Geocoding) | [Nominatim](https://nominatim.org/) (OpenStreetMap) | max. 1 Anfrage/s, [Nutzungsrichtlinie](https://operations.osmfoundation.org/policies/nominatim/) |
| Auto- und Fußrouten, Abbiegehinweise | [openrouteservice](https://openrouteservice.org/) (HeiGIT) | API-Schlüssel nötig; Tageszähler stoppt bei `ORS_DAILY_LIMIT` |
| Bus und Bahn | [Transitous](https://transitous.org/) (MOTIS 2) | nur nicht-kommerziell, Kontakt im User-Agent; Tageszähler stoppt bei `TRANSITOUS_DAILY_LIMIT` ([Nutzungsrichtlinie](https://transitous.org/api/)) |
| Kartenkacheln | tile.openstreetmap.org | lädt der Browser bei Bedarf, kein Vorab-Download; Quellenangabe auf Karte und Ausdruck |

QR-Codes werden lokal erzeugt. Leaflet 1.9.4 und die Noto-Schriften liegen unter `app/static/vendor/` (Lizenzen dort).

## Betrieb und Nutzungsbedingungen

Wegweiser ist Software zum Selbstbetrieb. Es gibt keinen zentralen Dienst: Jede Organisation betreibt ihre eigene Instanz und ist selbst dafür verantwortlich, die Bedingungen der genutzten Dienste einzuhalten. Die Voreinstellungen zielen auf kleine, nicht-kommerzielle Instanzen, etwa eines Vereins oder einer Initiative in der Flüchtlingshilfe.

**Öffentliche Dienste und ihre Grenzen** (Stand November 2026, bitte vor dem Betrieb selbst prüfen):

- **Transitous** ist ein gemeinschaftlich betriebener Dienst für nicht-kommerzielle Nutzung und Open-Source-Projekte. Pro Instanz eine eigene Kontaktangabe in `APP_CONTACT` eintragen. Mehr als 720 Verbindungsanfragen am Tag nur nach Absprache.
- **openrouteservice**: Der kostenlose Standard-Plan von HeiGIT hat Tageslimits und ist nicht für kommerzielle Nutzung gedacht. Jede Instanz braucht einen eigenen API-Schlüssel.
- **Nominatim** (OpenStreetMap-Foundation): höchstens eine Anfrage pro Sekunde, keine Massenabfragen. Wegweiser sucht nur, wenn jemand ein Ziel anlegt, und speichert die Ergebnisse zwischen.
- **Kartenkacheln** von tile.openstreetmap.org: Es gilt die [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/). Die Quellenangabe muss sichtbar bleiben, auch auf dem Ausdruck.

**Kommerzielle oder größere Nutzung**, zum Beispiel durch ein Unternehmen, das im Auftrag von Behörden Unterkünfte betreibt: Die öffentlichen Dienste sind dafür nicht gedacht. Möglich ist dann:

- ÖPNV über einen selbst betriebenen [MOTIS](https://github.com/motis-project/motis)-Server mit offenen Fahrplandaten, etwa GTFS der NVBW für Baden-Württemberg oder DELFI für Deutschland. `TRANSITOUS_BASE_URL` zeigt dann auf diesen Server.
- Routen über ein selbst betriebenes [openrouteservice](https://github.com/GIScience/openrouteservice) (`ORS_BASE_URL`) oder einen kommerziellen Plan bei HeiGIT.
- Kartenkacheln von einem kommerziellen Anbieter oder einem eigenen Kachelserver.

Für ein eigenes openrouteservice bleibt `ORS_API_KEY` leer. Getestet ist das für ganz Baden-Württemberg (MOTIS 2.11 mit NVBW-GTFS, openrouteservice 10.1, Profile Auto und zu Fuß): Der einmalige Import dauert rund 15 Minuten und braucht kurzzeitig etwa 6 GB Arbeitsspeicher. Im Betrieb brauchen beide Dienste zusammen gut 2 GB und rund 5 GB Speicherplatz. Die Ergebnisse stimmten in Stichproben mit Transitous und HeiGIT überein. Quellenangaben und Kartenkacheln lassen sich in `.env` anpassen (`TRANSIT_ATTRIBUTION`, `ROUTE_ATTRIBUTION`, `TILE_URL` usw., Beispiele in `.env.example`). Die NVBW-Fahrpläne stehen unter der Datenlizenz Deutschland – Namensnennung 2.0 und verlangen den Hinweis „Datensatz der NVBW GmbH“ mit Link auf [nvbw.de/open-data](https://www.nvbw.de/open-data). Linienfarben ergänzt das Update-Skript aus einer freien Sammlung. Anleitung: [selfhost/README.md](selfhost/README.md).

**Datenschutz:**

- An die externen Dienste gehen nur Adressen und Koordinaten von Standorten und Zielen. Namen oder andere Angaben zu Bewohnerinnen und Bewohnern gehören nicht in Wegweiser, auch nicht in die Notizfelder.
- Große, öffentlich bekannte Unterkünfte sind unkritisch. Dezentrale oder geschützte Unterkünfte (zum Beispiel für Frauen) sind es nicht: Eine Instanz mit solchen Standorten soll nur im internen Netz oder per VPN erreichbar sein.
- Wegweiser hat keine eigene Anmeldung. Von außerhalb des internen Netzes nur über VPN oder hinter einer Zugangskontrolle erreichbar machen, etwa einem Cloudflare Tunnel mit Cloudflare Access (siehe [Zugriff von außen](#zugriff-von-außen)).
- Wer Fehler meldet oder Screenshots teilt, nimmt Beispieldaten statt echter Standorte.

**Sicherung:** Wegweiser sichert die Datenbank jeden Tag selbst (Standard 2:30 Uhr, `BACKUP_TIME`) und behält die letzten 14 Stände (`BACKUP_KEEP`, 0 = aus). Die Sicherungen landen im Ordner `./backups` neben `./data`; mit `BACKUP_PATH` in `.env` zeigt er auf einen zweiten Datenträger oder einen Ordner, der mit einem Cloud-Speicher abgeglichen wird. Gesichert werden Standorte, Ziele, Namen, Einstellungen und Admin-Konten, nicht der Zwischenspeicher. Auf der Admin-Seite unter „Sicherung der Datenbank“ stehen die vorhandenen Sicherungen zum Download, dazu „Jetzt sichern“ und ein Hinweis, falls die letzte Sicherung fehlgeschlagen ist. Wiederherstellen: Container anhalten, Sicherung über `data/wegweiser.sqlite` kopieren, Container starten.

**Haftung:** Routen, Fahrpläne und Öffnungszeiten stammen aus offenen Datenquellen und können falsch oder veraltet sein. Den Ausdruck vor der Weitergabe kurz prüfen.

## Installation mit Docker

```sh
cp .env.example .env   # ORS_API_KEY und APP_CONTACT eintragen, ggf. APP_PORT anpassen
docker compose up -d --build
```

Die Oberfläche ist danach unter `http://<host>:${APP_PORT:-8420}/` erreichbar. Gedacht ist der Betrieb im internen Netz oder per VPN, nicht öffentlich im Internet.

- Das Image enthält Chromium für die Server-PDFs (rund 900 MB). Der Container braucht normal etwa 100 MB Arbeitsspeicher, beim PDF-Export einige hundert MB mehr (Grenze in `docker-compose.yml`: 1 GB).
- Die SQLite-Datenbank liegt unter `./data/` (Volume). Der Container läuft als UID 1000 und macht `./data` beim Start für sich beschreibbar.
- Die Zeitzone für Datumsangaben auf dem Ausdruck ist `Europe/Berlin` (über `TZ` änderbar).
- Nach Änderungen an `.env` den Container neu erzeugen: `docker compose up -d`.

### Aktualisieren

- **Neue Versionen** von Python-Paketen und Docker-Images (Basis-Image, MOTIS, openrouteservice, cloudflared) schlägt Dependabot wöchentlich als Pull Request vor, Sicherheitsupdates sofort. Jeder Pull Request durchläuft automatisch die Tests (GitHub Actions). Nach dem Übernehmen auf dem Server `git pull` und `./rebuild.sh`.
- **Sicherheitsupdates von Debian und Python im Basis-Image** holt `./rebuild.sh`: neu bauen mit `--pull`, neu starten, alte Wegweiser-Images aufräumen (nur diese, erkennbar am Label `org.wegweiser.app`). Am besten wöchentlich per Cron, z. B. `30 4 * * 1 /pfad/zu/wegweiser/rebuild.sh >> /pfad/zu/wegweiser/rebuild.log 2>&1`.
- Leaflet und die Noto-Schriften liegen fest im Repo (`app/static/vendor/`) und werden von Hand aktualisiert.

### Zugriff von außen

Wegweiser hat keine eigene Anmeldung. Für Zugriff von außerhalb des internen Netzes deshalb entweder ein VPN nutzen oder einen Cloudflare Tunnel **zusammen mit Cloudflare Access**: Dann meldet man sich mit einem Code per E-Mail an, nur freigegebene Adressen kommen durch, und am Router wird kein Port geöffnet. Voraussetzung ist eine eigene Domain, deren DNS bei Cloudflare liegt; Cloudflare Zero Trust ist bis 50 Nutzer kostenlos.

1. **Zuerst den Zugangsschutz:** Im Zero-Trust-Dashboard unter Access eine Anwendung vom Typ „Self-hosted“ für den gewünschten Hostnamen anlegen (z. B. `wegweiser.example.org`), mit einer Regel „Allow“ für die E-Mail-Adressen der Nutzerinnen und Nutzer und der Anmeldung per „One-time PIN“.
2. **Dann den Tunnel:** Unter Networks → Tunnels einen Tunnel mit cloudflared anlegen, das Token in `.env` als `CLOUDFLARE_TUNNEL_TOKEN` eintragen. Als öffentlichen Hostnamen denselben Namen wie in Schritt 1 eintragen, Dienst `HTTP`, Adresse `wegweiser:8000`.
3. In `.env` `FORWARDED_ALLOW_IPS=*` setzen, damit Links mit `https://` entstehen.
4. `docker compose --profile tunnel up -d`
5. **Prüfen:** Den Hostnamen in einem privaten Browserfenster öffnen. Es muss die Anmeldeseite von Cloudflare erscheinen, nicht Wegweiser.

Die Bezeichnungen im Cloudflare-Dashboard ändern sich gelegentlich. Der Tunnel leitet nur diesen einen Hostnamen weiter; andere Dienste auf demselben Rechner bleiben unerreichbar.

## Entwicklung

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8420
.venv/bin/pytest
```

Python 3.12, FastAPI, Jinja2, SQLite, Vanilla JS und Leaflet, ohne Build-Schritt. Die Tests rufen keine externen Dienste auf. Texte der Oberfläche (Deutsch und Englisch) stehen in `app/i18n.py`, Texte des Ausdrucks ebenfalls dort, Kategorienamen in `app/category_names.py`. Projektregeln und Hintergründe stehen in `CLAUDE.md`.

## Lizenz

Wegweiser steht unter der [Europäischen Gemeinschaftslizenz EUPL 1.2](LICENSE). © 2026 Moritz Werner. Mitgelieferte Fremdkomponenten (Leaflet, Noto-Schriften) haben eigene Lizenzen, siehe `app/static/vendor/`. Die Kategorie- und Liniensymbole sind eigene Zeichnungen und stehen ebenfalls unter der EUPL.
