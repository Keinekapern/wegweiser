"""Translations.

Two independent languages:
- UI language (de/en): the web interface. German strings are the message ids,
  ENGLISH maps them to English. Chosen via cookie.
- Directions language (all languages openrouteservice supports): turn-by-turn
  instructions from ORS plus the labels on the directions result / printout.
"""

import unicodedata
from collections.abc import Callable
from datetime import date

from fastapi import Request
from markupsafe import Markup, escape

# ---------------------------------------------------------------------------
# UI language
# ---------------------------------------------------------------------------

UI_LANGUAGES = {"de": "Deutsch", "en": "English"}
DEFAULT_UI_LANG = "de"
UI_LANG_COOKIE = "ui_lang"


class Msg:
    """A translatable message with parameters, rendered later in the UI language."""

    def __init__(self, msgid: str, **params):
        self.msgid = msgid
        self.params = params

    def __str__(self) -> str:
        return translate(DEFAULT_UI_LANG, self)

    def __repr__(self) -> str:
        return f"Msg({self.msgid!r}, {self.params!r})"


class UserError(Exception):
    """Error whose message is shown to the user (translated at render time)."""

    def __init__(self, msg: Msg):
        self.msg = msg
        super().__init__(str(msg))


def translate(lang: str, msg: "str | Msg", **params) -> str:
    if isinstance(msg, Msg):
        params = msg.params | params
        msg = msg.msgid
    text = msg if lang == "de" else ENGLISH.get(msg, msg)
    if params:
        params = {k: translate(lang, v) if isinstance(v, Msg) else v for k, v in params.items()}
        text = text.format(**params)
    return text


def get_ui_lang(request: Request) -> str:
    lang = request.cookies.get(UI_LANG_COOKIE, "")
    return lang if lang in UI_LANGUAGES else DEFAULT_UI_LANG


def translator(lang: str) -> Callable[..., str]:
    return lambda msg, **params: translate(lang, msg, **params)


# German msgid -> English. Keep sorted by area; tests check that every msgid
# used in templates/JS exists here.
ENGLISH: dict[str, str] = {
    # database backups
    "Sicherung": "Backup",
    "Sicherung der Datenbank": "Database backup",
    "Wegweiser sichert die Datenbank jeden Tag um {time} Uhr und behält die letzten {keep} Sicherungen. Gesichert werden Standorte, Ziele, übersetzte Namen, Einstellungen und Admin-Konten.":
        "Wegweiser backs up the database every day at {time} and keeps the latest {keep} "
        "backups: locations, destinations, translated names, settings and admin accounts.",
    "Die automatische Sicherung ist ausgeschaltet (BACKUP_KEEP=0). Sicherungen von Hand sind weiter möglich.":
        "Automatic backups are switched off (BACKUP_KEEP=0). Manual backups are still possible.",
    "Speicherort": "Location",
    "am besten ein zweiter Datenträger oder ein Ordner, der mit einem Cloud-Speicher abgeglichen wird (BACKUP_PATH in .env).":
        "ideally a second drive or a folder synced with cloud storage (BACKUP_PATH in .env).",
    "Sicherung erstellt: {name}": "Backup created: {name}",
    "Die letzte Sicherung ist fehlgeschlagen": "The last backup failed",
    "Jetzt sichern": "Back up now",
    "Erstellt": "Created",
    "Größe": "Size",
    "Herunterladen": "Download",
    "Noch keine Sicherung vorhanden.": "No backup yet.",
    "Wiederherstellen": "Restore",
    "Wegweiser anhalten:": "Stop Wegweiser:",
    "Die gewünschte Sicherung über data/wegweiser.sqlite kopieren (die alte Datei vorher umbenennen).":
        "Copy the backup over data/wegweiser.sqlite (rename the old file first).",
    "Wegweiser wieder starten:": "Start Wegweiser again:",
    # language settings
    "Sprachen der Wegbeschreibung": "Directions languages",
    "Sprachen auswählen": "Choose languages",
    "Sprachen der Wegbeschreibung auswählen": "Choose directions languages",
    "Einstellungen": "Settings",
    "Nur die angehakten Sprachen stehen bei der Wegbeschreibung, im Export und bei den übersetzten Zielnamen zur Auswahl. Deutsch ist immer dabei. Bereits gespeicherte Namen in abgeschalteten Sprachen bleiben erhalten.":
        "Only the ticked languages are offered for directions, in the export and for translated "
        "destination names. German is always included. Names already saved in languages that are "
        "switched off are kept.",
    "Gespeichert: {n} Sprachen stehen zur Auswahl.": "Saved: {n} languages are offered.",
    # PDF export
    "PDF-Export": "PDF export",
    "Export": "Export",
    "Als PDF": "As PDF",
    "PDF auf dem Server erstellen, mit den gewählten Optionen; ein verschobener Kartenausschnitt wird nicht übernommen.":
        "Create the PDF on the server with the chosen options; a moved map section is not used.",
    "Gerade läuft ein PDF-Export. Bitte in ein paar Minuten erneut versuchen.":
        "A PDF export is running. Please try again in a few minutes.",
    "Erstellt Wegbeschreibungen als PDF für mehrere Ziele und Sprachen auf einmal und packt sie in eine ZIP-Datei: je Standort ein Ordner (bei mehreren Standorten), darin je Ziel ein Ordner mit den PDFs aller Sprachen.":
        "Creates directions as PDFs for many destinations and languages at once and packs them "
        "into a ZIP file: one folder per location (with several locations), inside one folder "
        "per destination with the PDFs of all languages.",
    "Alle": "All",
    "Keine": "None",
    "Sprachen": "Languages",
    "Je Standort werden nur die Ziele erstellt, die dort angeboten werden.":
        "For each location, only the destinations offered there are created.",
    "Bei mehreren Verkehrsmitteln steht es im Dateinamen.":
        "With several modes, the mode is part of the file name.",
    "{n} PDFs werden erstellt, Dauer etwa {min} Minuten.": "{n} PDFs will be created, taking about {min} minutes.",
    "{n} PDFs – höchstens {max} sind auf einmal möglich.": "{n} PDFs – at most {max} are possible at once.",
    "Export starten": "Start export",
    "Bitte mindestens einen Standort wählen.": "Please choose at least one location.",
    "Bitte mindestens ein Ziel wählen.": "Please choose at least one destination.",
    "Bitte mindestens eine Sprache wählen.": "Please choose at least one language.",
    "Für diese Auswahl gibt es keine Ziele: Die gewählten Ziele werden bei den gewählten Standorten nicht angeboten.":
        "Nothing to export: the chosen destinations are not offered at the chosen locations.",
    "Das wären {n} PDFs, höchstens {max} sind auf einmal möglich. Bitte weniger Ziele oder Sprachen wählen.":
        "That would be {n} PDFs, at most {max} are possible at once. Please choose fewer "
        "destinations or languages.",
    "Gerade läuft schon ein Export. Bitte warten, bis er fertig ist.":
        "An export is already running. Please wait until it has finished.",
    "Wartet …": "Waiting …",
    "Erstelle PDF {done} von {total} …": "Creating PDF {done} of {total} …",
    "Fertig: {done} PDFs.": "Done: {done} PDFs.",
    "Der Export ist fehlgeschlagen.": "The export failed.",
    "{n} PDFs konnten nicht oder nur unvollständig erstellt werden, siehe Übersicht.pdf im ZIP.":
        "{n} PDFs could not be created or are incomplete, see Overview.pdf in the ZIP.",
    "ZIP herunterladen": "Download ZIP",
    "eine Stunde lang verfügbar": "available for one hour",
    "Neuer Export": "New export",
    "Übersicht": "Overview",
    "automatisch": "automatic",
    "zu Fuß": "on foot",
    "{n} Standorte": "{n} locations",
    "Ohne Namen": "Unnamed",
    "Wegweiser – Export": "Wegweiser – export",
    "Erstellt am": "Created on",
    "Schwarz-Weiß": "black and white",
    "PDFs": "PDFs",
    "von": "of",
    "Inhalt": "Contents",
    "Ordner": "Folder",
    "Nicht oder unvollständig erstellt": "Not created or incomplete",
    "Karte unvollständig (Kacheln fehlen)": "Map incomplete (tiles missing)",
    "Seite konnte nicht erstellt werden": "Page could not be created",
    "Fehler beim Erstellen": "Error while creating",
    "Fahrpläne und Routen ändern sich: Die Wegbeschreibungen geben den Stand vom Erstellungsdatum wieder.":
        "Timetables and routes change: the directions show the state on the date they were created.",
    "Quellen": "Sources",
    # admin / approval of new destinations
    "Admin": "Admin",
    "Admins": "Admins",
    "Admin-Anmeldung": "Admin login",
    "Als Admin anmelden": "Log in as admin",
    "Anmelden": "Log in",
    "Abmelden": "Log out",
    "Angemeldet als {name}": "Logged in as {name}",
    "angemeldet": "logged in",
    "Benutzername": "Username",
    "Passwort": "Password",
    "Passwort wiederholen": "Repeat password",
    "Bisheriges Passwort": "Current password",
    "Neues Passwort": "New password",
    "Passwort ändern": "Change password",
    "Eigenes Passwort ändern": "Change own password",
    "Passwort geändert.": "Password changed.",
    "Nach dem Ändern werden alle anderen Anmeldungen dieses Kontos beendet.":
        "Changing it ends all other sessions of this account.",
    "Admin hinzufügen": "Add admin",
    "Admin „{name}“ angelegt.": "Admin “{name}” created.",
    "Admin „{name}“ wirklich löschen?": "Really delete admin “{name}”?",
    "Benutzername oder Passwort ist falsch.": "Wrong username or password.",
    "Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.":
        "Too many failed attempts. Please try again in 15 minutes.",
    "Bitte einen Benutzernamen angeben.": "Please enter a username.",
    "Diesen Benutzernamen gibt es schon.": "This username already exists.",
    "Das Passwort muss mindestens {n} Zeichen lang sein.":
        "The password must be at least {n} characters long.",
    "Die Passwörter stimmen nicht überein.": "The passwords do not match.",
    "Das bisherige Passwort ist falsch.": "The current password is wrong.",
    "Das eigene Konto kann nicht gelöscht werden.": "You cannot delete your own account.",
    "Es gibt noch kein Admin-Konto. Das erste Konto wird auf dem Server angelegt:":
        "There is no admin account yet. The first one is created on the server:",
    "Bearbeiten und Löschen von Zielen und Standorten sowie das Bestätigen neuer Ziele sind Admins vorbehalten. Neue Ziele kann jede Person anlegen.":
        "Editing and deleting destinations and locations, and approving new destinations, "
        "is reserved for admins. Anyone can create new destinations.",
    "Neue Ziele zur Bestätigung": "New destinations to approve",
    "Keine Ziele warten auf Bestätigung.": "No destinations are waiting for approval.",
    "Diese Ziele wurden ohne Anmeldung angelegt. Sie sind schon nutzbar, werden aber erst nach der Bestätigung dauerhaft. Beim Bestätigen am besten Adresse, Kategorie und Standorte prüfen.":
        "These destinations were created without login. They can already be used but only "
        "become permanent once approved. Best check address, category and locations when approving.",
    "Angelegt": "Created",
    "Bestätigen": "Approve",
    "Ablehnen": "Reject",
    "Ziel „{name}“ ablehnen und löschen?": "Reject and delete destination “{name}”?",
    "unbestätigt": "unapproved",
    "Wartet auf Bestätigung durch einen Admin": "Waiting for approval by an admin",
    "Ziel angelegt. Es ist sofort nutzbar und wird dauerhaft, sobald ein Admin es bestätigt.":
        "Destination created. It can be used right away and becomes permanent once an admin approves it.",
    "Neue Ziele sind sofort nutzbar und werden dauerhaft, sobald ein Admin sie bestätigt.":
        "New destinations can be used right away and become permanent once an admin approves them.",
    "Dieses Ziel ist noch unbestätigt. Bis zur Bestätigung durch einen Admin lässt es sich in diesem Browser noch korrigieren.":
        "This destination is not approved yet. Until an admin approves it, it can still be "
        "corrected in this browser.",
    "Standorte anlegen und ändern können nur Admins.": "Only admins can create and change locations.",
    "Betrieb ohne Anmeldung: Alle, die diese Seite öffnen, können alles ändern. Nur auf dem eigenen PC oder in einem vertrauenswürdigen Netz verwenden.":
        "Running without login: anyone who opens this page can change everything. Only use it "
        "on your own PC or in a trusted network.",
    # navigation / general
    "Wegbeschreibung": "Directions",
    "Ziele": "Destinations",
    "Standorte": "Locations",
    "Sprache der Oberfläche": "Interface language",
    "Design: automatisch": "Theme: automatic",
    "Design: hell": "Theme: light",
    "Design: dunkel": "Theme: dark",
    "Name": "Name",
    "Adresse": "Address",
    "Koordinaten": "Coordinates",
    "Kontakt": "Contact",
    "Breitengrad": "Latitude",
    "Längengrad": "Longitude",
    "Telefon": "Phone",
    "Website": "Website",
    "Bearbeiten": "Edit",
    "Löschen": "Delete",
    "Speichern": "Save",
    "Anlegen": "Create",
    "Abbrechen": "Cancel",
    "Route": "Route",
    "Straße Nr., PLZ Ort": "Street no., postcode city",
    # locations
    "Feste Startpunkte für Wegbeschreibungen.": "Fixed starting points for directions.",
    "Noch keine Standorte angelegt.": "No locations yet.",
    "Standort „{name}“ wirklich löschen?": "Really delete location “{name}”?",
    "Standort bearbeiten": "Edit location",
    "Neuer Standort": "New location",
    "z. B. Büro Innenstadt": "e.g. Downtown office",
    "Standort nicht gefunden": "Location not found",
    # destinations
    "Einrichtungen, zu denen Wegbeschreibungen erstellt werden.":
        "Facilities that directions are created for.",
    "Neues Ziel": "New destination",
    "Ziel bearbeiten": "Edit destination",
    "Noch keine Ziele angelegt.": "No destinations yet.",
    "Ziel „{name}“ wirklich löschen?": "Really delete destination “{name}”?",
    "Geprüfter Google-Maps-Link hinterlegt": "Verified Google Maps link stored",
    "Google-Link": "Google link",
    "← Zurück zur Zielliste": "← Back to destinations",
    "Daten aus OpenStreetMap übernommen – bitte prüfen und ggf. korrigieren.":
        "Data taken from OpenStreetMap – please check and correct if necessary.",
    "Name (Überschrift auf dem Ausdruck)": "Name (heading on the printout)",
    "Öffnungszeiten": "Opening hours",
    "z. B. Mo-Fr 08:00-12:00": "e.g. Mo-Fr 08:00-12:00",
    "Geprüfter Google-Maps-Link (optional)": "Verified Google Maps link (optional)",
    "Wird für den Google-QR-Code verwendet. Ohne Link wird eine Suche nach Name und Adresse erzeugt.":
        "Used for the Google QR code. Without a link, a search for name and address is generated.",
    "Notiz (intern, keine Patientendaten)": "Note (internal, no patient data)",
    "OSM-Objekt": "OSM object",
    "Ziel nicht gefunden": "Destination not found",
    "Kategorie": "Category",
    "Ohne Kategorie": "Without category",
    "Ziel suchen …": "Search destination …",
    "Kein passendes Ziel gefunden.": "No matching destination found.",
    "„{q}“ als neues Ziel anlegen": "Create “{q}” as a new destination",
    "Neues Ziel anlegen": "Create a new destination",
    "Koordinaten (Breite, Länge)": "Coordinates (latitude, longitude)",
    "Koordinaten nicht erkannt. Bitte im Format „48.690351, 9.032999“ eingeben (Breite, Länge).":
        "Coordinates not recognised. Please enter them as “48.690351, 9.032999” (latitude, longitude).",
    "Koordinaten über die Suche oben übernehmen oder z. B. aus Google Maps kopieren und einfügen („48.690351, 9.032999“).":
        "Take the coordinates from the search above or paste them, e.g. from Google Maps (“48.690351, 9.032999”).",
    "Einfügen z. B. aus Google Maps (Rechtsklick auf den Ort → Koordinaten kopieren).":
        "Paste e.g. from Google Maps (right-click the place → copy the coordinates).",
    "Wird automatisch ins internationale Format (+49 …) gebracht.":
        "Converted automatically to international format (+49 …).",
    "Telefonnummer „{phone}“ ist ungültig – bitte mit Vorwahl eingeben.":
        "Phone number “{phone}” is invalid – please include the area code.",
    "In Google Maps suchen": "Search in Google Maps",
    "Link öffnen": "Open link",
    "– keine –": "– none –",
    # categories (app/categories.py)
    "Gesundheit": "Health", "Behörden": "Authorities", "Bildung/Soziales": "Education/social",
    "Religion": "Religion", "Alltag": "Everyday", "Sonstiges": "Other",
    "Krankenhaus": "Hospital", "Arztpraxis": "Doctor's practice", "Zahnarzt": "Dentist",
    "Apotheke": "Pharmacy", "Psychotherapie/Beratung": "Psychotherapy/counselling",
    "Physiotherapie": "Physiotherapy", "Optiker": "Optician",
    "Rathaus/Bürgeramt": "Town hall/citizens' office", "Ausländerbehörde": "Immigration office",
    "Jobcenter/Arbeitsagentur": "Job centre/employment agency", "Polizei": "Police",
    "Gericht": "Court", "Schule": "School", "Kita": "Daycare", "Sprachkurs": "Language course",
    "Beratungsstelle": "Advice centre", "Kirche": "Church", "Moschee": "Mosque",
    "Synagoge": "Synagogue", "Tempel": "Temple", "Gebetsstätte": "Place of worship", "Bahnhof": "Station",
    "Supermarkt": "Supermarket", "Bank": "Bank", "Post": "Post office",
    "Standorte, für die das Ziel angeboten wird": "Locations this destination is offered for",
    "Ohne Häkchen erscheint das Ziel bei allen Standorten.":
        "Without a tick, the destination is offered for all locations.",
    "Standort": "Location",
    "Name in anderen Sprachen (optional)": "Name in other languages (optional)",
    "Nur für Namen, die man übersetzen kann (z. B. „Kinderklinik“), nicht für Eigennamen wie „Fielmann“. Ohne Übersetzung steht auf der Wegbeschreibung die Art der Einrichtung in der gewählten Sprache. Vorschläge aus OpenStreetMap werden bei der Suche eingetragen.":
        "Only for names that can be translated (e.g. “Kinderklinik”), not for proper names like “Fielmann”. Without a translation, the directions show the kind of place in the chosen language. Suggestions from OpenStreetMap are filled in by the search.",
    "Kategorien": "Categories",
    "Überschrift der ÖPNV-Verbindung, zusammengesetzt aus den genutzten Verkehrsmitteln. Korrekturen in app/i18n.py (TRANSIT_MODE_PHRASES) übernehmen.":
        "Heading of the public transport connection, built from the means of transport used. Put corrections into app/i18n.py (TRANSIT_MODE_PHRASES).",
    "Stehen unter dem Namen des Ziels, wenn für die Sprache kein übersetzter Name eingetragen ist. Korrekturen in app/category_names.py übernehmen.":
        "Shown under the destination name when no translated name is stored for the language. Put corrections into app/category_names.py.",
    "Alle Standorte": "All locations",
    "Filtern": "Filter",
    "alle": "all",
    # search panel
    "In OpenStreetMap suchen (Name oder Adresse)": "Search OpenStreetMap (name or address)",
    "z. B. Klinikum Stuttgart Katharinenhospital": "e.g. Klinikum Stuttgart Katharinenhospital",
    "Suchen": "Search",
    "Bitte mindestens 3 Zeichen eingeben.": "Please enter at least 3 characters.",
    "Suche läuft …": "Searching …",
    "Die Suche ist fehlgeschlagen.": "The search failed.",
    "Keine Treffer. Andere Schreibweise oder Adresse versuchen.":
        "No results. Try a different spelling or the address.",
    "{n} Treffer – zum Übernehmen anklicken:": "{n} results – click one to use it:",
    "„{name}“ übernommen.": "“{name}” applied.",
    "Die Suche ist fehlgeschlagen (keine Verbindung zum Server).":
        "The search failed (no connection to the server).",
    "auf Karte prüfen": "check on map",
    # directions page
    "Zuerst einen Standort und ein Ziel anlegen.": "Create a location and a destination first.",
    "Zuerst einen Standort anlegen.": "Create a location first.",
    "Zuerst ein Ziel anlegen.": "Create a destination first.",
    "Start (Standort)": "Start (location)",
    "Ziel": "Destination",
    "– bitte wählen –": "– please choose –",
    "Verkehrsmittel": "Mode of transport",
    "Auto": "Car",
    "Zu Fuß": "On foot",
    "Fahrrad": "Bicycle",
    "Automatisch": "Automatic",
    "Automatische Wahl: zu Fuß bis (Min.)": "Automatic choice: walk up to (min)",
    "Automatisch gewählt: zu Fuß – der Fußweg dauert nur {walk} Min. (Grenze: {limit} Min.).":
        "Chosen automatically: on foot – the walk takes only {walk} min (limit: {limit} min).",
    "Automatisch gewählt: ÖPNV – {transit} Min. statt {walk} Min. zu Fuß.":
        "Chosen automatically: public transport – {transit} min instead of {walk} min on foot.",
    "Automatisch gewählt: zu Fuß – mit Bus und Bahn nicht schneller ({transit} statt {walk} Min.).":
        "Chosen automatically: on foot – public transport is not faster ({transit} instead of {walk} min).",
    "Automatisch gewählt: zu Fuß – keine ÖPNV-Verbindung verfügbar ({error})":
        "Chosen automatically: on foot – no public transport connection available ({error})",
    "Sprache der Wegbeschreibung": "Language of the directions",
    # public transport
    "ÖPNV": "Public transport",
    "ÖPNV-Optionen": "Public transport options",
    "max. {n} Umstiege": "max. {n} transfers",
    "zu Fuß bis {n} Min.": "walk up to {n} min",
    "rollstuhlgerecht": "wheelchair accessible",
    "ändern": "change",
    "Maximale Umstiege": "Maximum transfers",
    "Max. Fußweg zur Starthaltestelle (Min.)": "Max. walk to the first stop (min)",
    "Max. Fußweg von der Zielhaltestelle (Min.)": "Max. walk from the last stop (min)",
    "Erlaubte Verkehrsmittel": "Allowed modes of transport",
    "Bus": "Bus",
    "Straßenbahn/U-Bahn": "Tram/underground",
    "S-Bahn/Regionalzug": "Suburban/regional train",
    "Fernverkehr (ICE/IC, Fernbus)": "Long distance (ICE/IC, coach)",
    "Sonstige (Fähre, Seilbahn …)": "Other (ferry, cable car …)",
    "Rollstuhlgerecht (stufenfreie Wege)": "Wheelchair accessible (step-free paths)",
    "Referenz-Wochentag": "Reference weekday",
    "Uhrzeit": "Time",
    "Montag": "Monday", "Dienstag": "Tuesday", "Mittwoch": "Wednesday",
    "Donnerstag": "Thursday", "Freitag": "Friday", "Samstag": "Saturday", "Sonntag": "Sunday",
    "Als Standard speichern": "Save as default",
    "Standardwerte für ÖPNV gespeichert.": "Public transport defaults saved.",
    "Gesucht wird eine Verbindung am nächsten {weekday} gegen {time} Uhr. Auf dem Ausdruck steht der Takt, keine Abfahrtszeiten.":
        "A connection is searched for next {weekday} around {time}. The printout shows the frequency, not departure times.",
    "Ungültiger Wert für {field}: {value}": "Invalid value for {field}: {value}",
    "Bitte mindestens ein Verkehrsmittel wählen.": "Please select at least one mode of transport.",
    "Keine ÖPNV-Verbindung gefunden. Optionen (Fußweg, Umstiege, Verkehrsmittel) lockern oder andere Uhrzeit wählen.":
        "No public transport connection found. Relax the options (walking, transfers, modes) or choose another time.",
    "Für ÖPNV-Abfragen muss ein Kontakt konfiguriert sein (APP_CONTACT in .env), so verlangt es Transitous.":
        "Public transport requests need a contact (APP_CONTACT in .env), as required by Transitous.",
    "Tageslimit für ÖPNV-Abfragen erreicht ({limit}). Bitte morgen erneut versuchen.":
        "Daily limit for public transport requests reached ({limit}). Please try again tomorrow.",
    "Der ÖPNV-Dienst ist gerade nicht erreichbar.": "The public transport service is currently unavailable.",
    "ÖPNV-Abfrage fehlgeschlagen: {detail}": "Public transport request failed: {detail}",
    "Die Antwort des ÖPNV-Dienstes war unerwartet.":
        "The public transport service returned an unexpected response.",
    # language names (LANGUAGE_NAMES)
    "Deutsch": "German", "Englisch": "English", "Tschechisch": "Czech", "Dänisch": "Danish",
    "Spanisch": "Spanish", "Finnisch": "Finnish", "Französisch": "French", "Griechisch": "Greek",
    "Hebräisch": "Hebrew", "Ungarisch": "Hungarian", "Indonesisch": "Indonesian",
    "Italienisch": "Italian", "Japanisch": "Japanese", "Niederländisch": "Dutch",
    "Norwegisch": "Norwegian", "Polnisch": "Polish",
    "Portugiesisch": "Portuguese", "Rumänisch": "Romanian", "Russisch": "Russian",
    "Türkisch": "Turkish", "Ukrainisch": "Ukrainian", "Vietnamesisch": "Vietnamese",
    "Chinesisch": "Chinese",
    "Arabisch": "Arabic", "Persisch / Farsi": "Persian / Farsi", "Tamil": "Tamil",
    "Somali": "Somali", "Tigrinya": "Tigrinya",
    "Route berechnen": "Calculate route",
    "Karte mit Route": "Map with route",
    "Druckansicht": "Print view",
    # print view
    "← Zurück": "← Back",
    "Abbiegehinweise drucken": "Print turn-by-turn directions",
    "Detailkarten Fußwege": "Detail maps of the walks",
    "Drucken": "Print",
    "Format": "Format",
    "Übersetzungen prüfen": "Review translations",
    "Alle Texte des Ausdrucks in einer Sprache, zum Gegenlesen durch Muttersprachler. Korrekturen bitte notieren und in app/i18n.py übernehmen.":
        "All printout texts of one language, for review by native speakers. Please note corrections and apply them in app/i18n.py.",
    "Abbiegehinweise (selbst erzeugt)": "Turn-by-turn directions (generated)",
    "openrouteservice unterstützt diese Sprache nicht. Die Hinweise werden aus diesen Vorlagen gebildet, der Straßenname folgt nach einem Gedankenstrich.":
        "openrouteservice does not support this language. Instructions are built from these templates; the street name follows after a dash.",
    "Hochformat": "Portrait",
    "Querformat": "Landscape",
    "Für Schwarz-Weiß-Druck optimieren": "Optimise for black-and-white printing",
    "Karte lädt …": "Loading map …",
    "Karte geladen – bereit zum Drucken.": "Map loaded – ready to print.",
    "{n} Kartenkacheln konnten nicht geladen werden. Seite neu laden oder Ausschnitt verschieben.":
        "{n} map tiles could not be loaded. Reload the page or move the map.",
    "Die Karte ist noch nicht vollständig geladen. Trotzdem drucken?":
        "The map has not finished loading. Print anyway?",
    "Kartenausschnitt kann vor dem Drucken verschoben und gezoomt werden.":
        "The map can be moved and zoomed before printing.",
    "Standort oder Ziel wurde nicht gefunden.": "Location or destination not found.",
    # validation
    "{label} darf nicht leer sein.": "{label} must not be empty.",
    "{label} ist keine gültige Zahl.": "{label} is not a valid number.",
    "{label} muss zwischen {min} und {max} liegen.": "{label} must be between {min} and {max}.",
    "{label} ist keine gültige Web-Adresse.": "{label} is not a valid web address.",
    "Google-Maps-Link muss mit https:// beginnen und auf google.… oder maps.app.goo.gl zeigen.":
        "Google Maps link must start with https:// and point to google.… or maps.app.goo.gl.",
    # geocoding errors
    "Die Adresssuche ist gerade nicht erreichbar.": "The address search is currently unavailable.",
    "Nominatim hat die Anfrage abgelehnt (zu viele Anfragen oder gesperrt). Bitte später erneut versuchen.":
        "Nominatim refused the request (too many requests or blocked). Please try again later.",
    "Die Adresssuche hat einen Fehler gemeldet (HTTP {status}).":
        "The address search reported an error (HTTP {status}).",
    "Die Antwort der Adresssuche war unerwartet.": "The address search returned an unexpected response.",
    # routing errors
    "Unbekanntes Verkehrsmittel: {profile}": "Unknown mode of transport: {profile}",
    "Kein openrouteservice-API-Key konfiguriert (ORS_API_KEY in .env).":
        "No openrouteservice API key configured (ORS_API_KEY in .env).",
    "Tageslimit für Routenberechnungen erreicht ({limit}). Bitte morgen erneut versuchen.":
        "Daily limit for route calculations reached ({limit}). Please try again tomorrow.",
    "Der Routing-Dienst ist gerade nicht erreichbar.": "The routing service is currently unavailable.",
    "openrouteservice hat die Anfrage abgelehnt (API-Key ungültig oder Kontingent erschöpft): {detail}":
        "openrouteservice refused the request (invalid API key or quota exhausted): {detail}",
    "Zu viele Routenanfragen. Bitte kurz warten und erneut versuchen.":
        "Too many route requests. Please wait a moment and try again.",
    "Route konnte nicht berechnet werden: {detail}": "Route could not be calculated: {detail}",
    "Die Antwort des Routing-Dienstes war unerwartet.":
        "The routing service returned an unexpected response.",
}

# Strings needed by static JS (exposed as JSON in base.html).
JS_MSGIDS = [
    "Bitte mindestens 3 Zeichen eingeben.",
    "Suche läuft …",
    "Die Suche ist fehlgeschlagen.",
    "Keine Treffer. Andere Schreibweise oder Adresse versuchen.",
    "{n} Treffer – zum Übernehmen anklicken:",
    "„{name}“ übernommen.",
    "Die Suche ist fehlgeschlagen (keine Verbindung zum Server).",
    "auf Karte prüfen",
    "OSM-Objekt",
]


def i18n_context(request: Request) -> dict:
    """Jinja2 context processor."""
    from app.config import APP_NAME
    lang = get_ui_lang(request)
    return {
        "app_name": APP_NAME,
        "t": translator(lang),
        "ui_lang": lang,
        "ui_languages": UI_LANGUAGES,
        "js_strings": {m: translate(lang, m) for m in JS_MSGIDS},
    }


# ---------------------------------------------------------------------------
# Directions language (openrouteservice languages, see ORS APIEnums.Languages)
# ---------------------------------------------------------------------------

DEFAULT_DIRECTIONS_LANG = "de"

# Subset of the openrouteservice languages that is offered in the UI.
# code (as ORS expects it): native name, HTML lang, right-to-left, decimal separator
DIRECTIONS_LANGUAGES: dict[str, tuple[str, str, bool, str]] = {
    "de": ("Deutsch", "de", False, ","),
    "en": ("English", "en", False, "."),
    "cs": ("Čeština", "cs", False, ","),
    "da": ("Dansk", "da", False, ","),
    "es": ("Español", "es", False, ","),
    "fi": ("Suomi", "fi", False, ","),
    "fr": ("Français", "fr", False, ","),
    "gr": ("Ελληνικά", "el", False, ","),
    "he": ("עברית", "he", True, "."),
    "hu": ("Magyar", "hu", False, ","),
    "id": ("Bahasa Indonesia", "id", False, ","),
    "it": ("Italiano", "it", False, ","),
    "ja": ("日本語", "ja", False, "."),
    "nl": ("Nederlands", "nl", False, ","),
    "nb": ("Norsk bokmål", "nb", False, ","),
    "pl": ("Polski", "pl", False, ","),
    "pt": ("Português", "pt", False, ","),
    "ro": ("Română", "ro", False, ","),
    "ru": ("Русский", "ru", False, ","),
    "tr": ("Türkçe", "tr", False, ","),
    "ua": ("Українська", "uk", False, ","),
    "vi": ("Tiếng Việt", "vi", False, ","),
    "zh": ("中文", "zh", False, "."),
    # Not supported by openrouteservice: instructions generated from MANEUVERS below
    "ar": ("العربية", "ar", True, "."),
    "fa": ("فارسی", "fa", True, "."),
    "ta": ("தமிழ்", "ta", False, "."),
    "so": ("Soomaali", "so", False, "."),
    "ti": ("ትግርኛ", "ti", False, "."),
}

# Language names in the UI language (German msgid, English in ENGLISH), shown in
# brackets after the native name in the language dropdown.
LANGUAGE_NAMES = {
    "de": "Deutsch", "en": "Englisch", "cs": "Tschechisch", "da": "Dänisch",
    "es": "Spanisch", "fi": "Finnisch", "fr": "Französisch", "gr": "Griechisch",
    "he": "Hebräisch", "hu": "Ungarisch", "id": "Indonesisch", "it": "Italienisch",
    "ja": "Japanisch", "nl": "Niederländisch", "nb": "Norwegisch", "pl": "Polnisch",
    "pt": "Portugiesisch", "ro": "Rumänisch", "ru": "Russisch", "tr": "Türkisch",
    "ua": "Ukrainisch", "vi": "Vietnamesisch", "zh": "Chinesisch",
    "ar": "Arabisch", "fa": "Persisch / Farsi", "ta": "Tamil", "so": "Somali", "ti": "Tigrinya",
}

DOC_KEYS = ("car", "foot", "summary", "minutes", "hours", "steps", "address", "phone",
            "website", "opening_hours", "created", "start", "destination", "osm", "date")

# Order of each tuple = DOC_KEYS. Translations other than de/en should be
# reviewed by native speakers before relying on them.
_DOC_TABLE: dict[str, tuple[str, ...]] = {
    "de": ("Mit dem Auto", "Zu Fuß", "{distance}, ca. {duration}", "{n} Min.", "{h} Std. {m} Min.",
           "Wegbeschreibung", "Adresse", "Telefon", "Website", "Öffnungszeiten", "Erstellt am {date}",
           "Start", "Ziel", "© OpenStreetMap-Mitwirkende", "%d.%m.%Y"),
    "en": ("By car", "On foot", "{distance}, approx. {duration}", "{n} min", "{h} h {m} min",
           "Directions", "Address", "Phone", "Website", "Opening hours", "Created on {date}",
           "Start", "Destination", "© OpenStreetMap contributors", "%d/%m/%Y"),
    "cs": ("Autem", "Pěšky", "{distance}, cca {duration}", "{n} min", "{h} h {m} min",
           "Popis trasy", "Adresa", "Telefon", "Web", "Otevírací doba", "Vytvořeno {date}",
           "Start", "Cíl", "© přispěvatelé OpenStreetMap", "%d.%m.%Y"),
    "da": ("I bil", "Til fods", "{distance}, ca. {duration}", "{n} min.", "{h} t. {m} min.",
           "Rutevejledning", "Adresse", "Telefon", "Hjemmeside", "Åbningstider", "Oprettet {date}",
           "Start", "Destination", "© OpenStreetMap-bidragydere", "%d.%m.%Y"),
    "es": ("En coche", "A pie", "{distance}, aprox. {duration}", "{n} min", "{h} h {m} min",
           "Indicaciones", "Dirección", "Teléfono", "Sitio web", "Horario", "Creado el {date}",
           "Salida", "Destino", "© colaboradores de OpenStreetMap", "%d/%m/%Y"),
    "fi": ("Autolla", "Kävellen", "{distance}, n. {duration}", "{n} min", "{h} h {m} min",
           "Reittiohjeet", "Osoite", "Puhelin", "Verkkosivusto", "Aukioloajat", "Luotu {date}",
           "Lähtö", "Määränpää", "© OpenStreetMapin tekijät", "%d.%m.%Y"),
    "fr": ("En voiture", "À pied", "{distance}, env. {duration}", "{n} min", "{h} h {m} min",
           "Itinéraire", "Adresse", "Téléphone", "Site web", "Horaires d'ouverture", "Créé le {date}",
           "Départ", "Destination", "© les contributeurs d'OpenStreetMap", "%d/%m/%Y"),
    "gr": ("Με αυτοκίνητο", "Με τα πόδια", "{distance}, περίπου {duration}", "{n} λεπτά",
           "{h} ώρ. {m} λεπ.", "Οδηγίες διαδρομής", "Διεύθυνση", "Τηλέφωνο", "Ιστότοπος",
           "Ωράριο λειτουργίας", "Δημιουργήθηκε στις {date}", "Αφετηρία", "Προορισμός",
           "© συντελεστές του OpenStreetMap", "%d/%m/%Y"),
    "he": ("ברכב", "ברגל", "{distance}, כ-{duration}", "{n} דק׳", "{h} שע׳ {m} דק׳",
           "הוראות הגעה", "כתובת", "טלפון", "אתר אינטרנט", "שעות פתיחה", "נוצר בתאריך {date}",
           "נקודת מוצא", "יעד", "© תורמי OpenStreetMap", "%d/%m/%Y"),
    "hu": ("Autóval", "Gyalog", "{distance}, kb. {duration}", "{n} perc", "{h} óra {m} perc",
           "Útvonalleírás", "Cím", "Telefon", "Weboldal", "Nyitvatartás", "Készült: {date}",
           "Indulás", "Úti cél", "© OpenStreetMap közreműködők", "%Y.%m.%d."),
    "id": ("Dengan mobil", "Berjalan kaki", "{distance}, sekitar {duration}", "{n} mnt",
           "{h} jam {m} mnt", "Petunjuk arah", "Alamat", "Telepon", "Situs web", "Jam buka",
           "Dibuat pada {date}", "Awal", "Tujuan", "© kontributor OpenStreetMap", "%d/%m/%Y"),
    "it": ("In auto", "A piedi", "{distance}, circa {duration}", "{n} min", "{h} h {m} min",
           "Indicazioni stradali", "Indirizzo", "Telefono", "Sito web", "Orari di apertura",
           "Creato il {date}", "Partenza", "Destinazione", "© contributori di OpenStreetMap",
           "%d/%m/%Y"),
    "ja": ("車で", "徒歩で", "{distance}、約{duration}", "{n}分", "{h}時間{m}分",
           "道順", "住所", "電話", "ウェブサイト", "営業時間", "作成日: {date}",
           "出発地", "目的地", "© OpenStreetMap 寄稿者", "%Y/%m/%d"),
    "nl": ("Met de auto", "Te voet", "{distance}, ca. {duration}", "{n} min", "{h} u {m} min",
           "Routebeschrijving", "Adres", "Telefoon", "Website", "Openingstijden", "Gemaakt op {date}",
           "Vertrek", "Bestemming", "© OpenStreetMap-bijdragers", "%d-%m-%Y"),
    "nb": ("Med bil", "Til fots", "{distance}, ca. {duration}", "{n} min", "{h} t {m} min",
           "Veibeskrivelse", "Adresse", "Telefon", "Nettside", "Åpningstider", "Opprettet {date}",
           "Start", "Mål", "© OpenStreetMap-bidragsytere", "%d.%m.%Y"),
    "pl": ("Samochodem", "Pieszo", "{distance}, ok. {duration}", "{n} min", "{h} godz. {m} min",
           "Opis trasy", "Adres", "Telefon", "Strona internetowa", "Godziny otwarcia",
           "Utworzono {date}", "Start", "Cel", "© współtwórcy OpenStreetMap", "%d.%m.%Y"),
    "pt": ("De carro", "A pé", "{distance}, aprox. {duration}", "{n} min", "{h} h {m} min",
           "Direções", "Endereço", "Telefone", "Site", "Horário de funcionamento", "Criado em {date}",
           "Partida", "Destino", "© contribuidores do OpenStreetMap", "%d/%m/%Y"),
    "ro": ("Cu mașina", "Pe jos", "{distance}, aprox. {duration}", "{n} min", "{h} h {m} min",
           "Indicații de traseu", "Adresă", "Telefon", "Site web", "Program", "Creat la {date}",
           "Plecare", "Destinație", "© contribuitorii OpenStreetMap", "%d.%m.%Y"),
    "ru": ("На автомобиле", "Пешком", "{distance}, около {duration}", "{n} мин", "{h} ч {m} мин",
           "Описание маршрута", "Адрес", "Телефон", "Сайт", "Часы работы", "Создано {date}",
           "Начало", "Пункт назначения", "© участники OpenStreetMap", "%d.%m.%Y"),
    "tr": ("Arabayla", "Yürüyerek", "{distance}, yaklaşık {duration}", "{n} dk", "{h} sa {m} dk",
           "Yol tarifi", "Adres", "Telefon", "Web sitesi", "Açılış saatleri",
           "Oluşturulma tarihi: {date}", "Başlangıç", "Varış noktası",
           "© OpenStreetMap katkıcıları", "%d.%m.%Y"),
    "ua": ("Автомобілем", "Пішки", "{distance}, близько {duration}", "{n} хв", "{h} год {m} хв",
           "Опис маршруту", "Адреса", "Телефон", "Вебсайт", "Години роботи", "Створено {date}",
           "Початок", "Пункт призначення", "© учасники OpenStreetMap", "%d.%m.%Y"),
    "vi": ("Bằng ô tô", "Đi bộ", "{distance}, khoảng {duration}", "{n} phút", "{h} giờ {m} phút",
           "Chỉ đường", "Địa chỉ", "Điện thoại", "Trang web", "Giờ mở cửa", "Tạo ngày {date}",
           "Điểm xuất phát", "Điểm đến", "© Những người đóng góp OpenStreetMap", "%d/%m/%Y"),
    "zh": ("驾车", "步行", "{distance}，约{duration}", "{n} 分钟", "{h} 小时 {m} 分钟",
           "路线说明", "地址", "电话", "网站", "营业时间", "创建于 {date}",
           "起点", "目的地", "© OpenStreetMap 贡献者", "%Y/%m/%d"),
    "ar": ("بالسيارة", "سيرًا على الأقدام", "{distance}، حوالي {duration}", "{n} دقيقة",
           "{h} ساعة {m} دقيقة", "الاتجاهات", "العنوان", "الهاتف", "الموقع الإلكتروني",
           "ساعات العمل", "تاريخ الإنشاء: {date}", "نقطة الانطلاق", "الوجهة",
           "© مساهمو OpenStreetMap", "%d/%m/%Y"),
    "fa": ("با خودرو", "پیاده", "{distance}، حدود {duration}", "{n} دقیقه", "{h} ساعت و {m} دقیقه",
           "مسیریابی", "نشانی", "تلفن", "وب‌سایت", "ساعات کاری", "تاریخ تهیه: {date}", "مبدأ",
           "مقصد", "© مشارکت‌کنندگان OpenStreetMap", "%Y/%m/%d"),
    "ta": ("காரில்", "நடந்து", "{distance}, சுமார் {duration}", "{n} நிமி.", "{h} மணி {m} நிமி.",
           "வழிகாட்டுதல்", "முகவரி", "தொலைபேசி", "இணையதளம்", "திறந்திருக்கும் நேரம்",
           "உருவாக்கிய தேதி: {date}", "தொடக்கம்", "சேருமிடம்", "© OpenStreetMap பங்களிப்பாளர்கள்",
           "%d/%m/%Y"),
    "so": ("Baabuur", "Lugeyn", "{distance}, qiyaastii {duration}", "{n} daqiiqo",
           "{h} saac {m} daqiiqo", "Tilmaamaha jidka", "Cinwaanka", "Telefoon", "Websaydh",
           "Saacadaha furitaanka", "La sameeyay {date}", "Bilow", "Meesha loo socdo",
           "© Ka-qaybgalayaasha OpenStreetMap", "%d/%m/%Y"),
    "ti": ("ብመኪና", "ብእግሪ", "{distance}፣ ኣስታት {duration}", "{n} ደቒቕ", "{h} ሰዓት {m} ደቒቕ",
           "መምርሒ መገዲ", "ኣድራሻ", "ቴሌፎን", "መርበብ ሓበሬታ", "ናይ ስራሕ ሰዓታት",
           "ዝተዳለወሉ ዕለት፡ {date}", "መበገሲ", "መዕለቢ", "© ተሳተፍቲ OpenStreetMap", "%d/%m/%Y"),
}

# Printout labels: (qr_hint, sources, apple_maps)
DOC_EXTRA_KEYS = ("qr_hint", "sources", "apple_maps")
_DOC_EXTRA: dict[str, tuple[str, str, str]] = {
    "de": ("Mit dem Handy scannen, um das Ziel in einer Karten-App zu öffnen", "Quellen", "Apple Karten"),
    "en": ("Scan with your phone to open the destination in a map app", "Sources", "Apple Maps"),
    "cs": ("Naskenujte telefonem a otevřete cíl v mapové aplikaci", "Zdroje", "Apple Mapy"),
    "da": ("Scan med telefonen for at åbne destinationen i en kortapp", "Kilder", "Apple Kort"),
    "es": ("Escanee con el móvil para abrir el destino en una app de mapas", "Fuentes", "Apple Mapas"),
    "fi": ("Skannaa puhelimella avataksesi määränpään karttasovelluksessa", "Lähteet", "Apple Kartat"),
    "fr": ("Scannez avec votre téléphone pour ouvrir la destination dans une application de cartes",
           "Sources", "Apple Plans"),
    "gr": ("Σαρώστε με το κινητό για να ανοίξετε τον προορισμό σε εφαρμογή χαρτών", "Πηγές",
           "Apple Χάρτες"),
    "he": ("סרקו בטלפון כדי לפתוח את היעד באפליקציית מפות", "מקורות", "מפות Apple"),
    "hu": ("Olvassa be telefonjával, hogy térképalkalmazásban nyissa meg az úti célt", "Források",
           "Apple Térképek"),
    "id": ("Pindai dengan ponsel untuk membuka tujuan di aplikasi peta", "Sumber", "Apple Peta"),
    "it": ("Scansiona con il telefono per aprire la destinazione in un'app di mappe", "Fonti",
           "Apple Mappe"),
    "ja": ("スマートフォンでスキャンして目的地を地図アプリで開く", "出典", "Appleマップ"),
    "nl": ("Scan met je telefoon om de bestemming in een kaart-app te openen", "Bronnen",
           "Apple Kaarten"),
    "nb": ("Skann med telefonen for å åpne målet i en kartapp", "Kilder", "Apple Kart"),
    "pl": ("Zeskanuj telefonem, aby otworzyć cel w aplikacji z mapami", "Źródła", "Apple Mapy"),
    "pt": ("Digitalize com o telemóvel para abrir o destino numa aplicação de mapas", "Fontes",
           "Apple Mapas"),
    "ro": ("Scanați cu telefonul pentru a deschide destinația într-o aplicație de hărți", "Surse",
           "Apple Hărți"),
    "ru": ("Отсканируйте телефоном, чтобы открыть пункт назначения в приложении карт", "Источники",
           "Apple Карты"),
    "tr": ("Varış noktasını bir harita uygulamasında açmak için telefonunuzla tarayın", "Kaynaklar",
           "Apple Haritalar"),
    "ua": ("Відскануйте телефоном, щоб відкрити пункт призначення в застосунку карт", "Джерела",
           "Apple Карти"),
    "vi": ("Quét bằng điện thoại để mở điểm đến trong ứng dụng bản đồ", "Nguồn", "Apple Bản đồ"),
    "zh": ("用手机扫描，在地图应用中打开目的地", "来源", "Apple 地图"),
    "ar": ("امسح الرمز بهاتفك لفتح الوجهة في تطبيق الخرائط", "المصادر", "خرائط Apple"),
    "fa": ("برای باز کردن مقصد در برنامهٔ نقشه، کد را با تلفن همراه اسکن کنید", "منابع", "نقشه Apple"),
    "ta": ("சேருமிடத்தை வரைபடச் செயலியில் திறக்க உங்கள் கைபேசியால் ஸ்கேன் செய்யவும்", "ஆதாரங்கள்",
           "Apple வரைபடம்"),
    "so": ("Ku iskaan garee taleefankaaga si aad meesha loo socdo ugu furto barnaamij khariidad",
           "Ilaha", "Apple Maps"),
    "ti": ("መዕለቢ ኣብ ናይ ካርታ ኣፕ ንምኽፋት ብተሌፎንኩም ስካን ግበሩ", "ምንጭታት", "Apple Maps"),
}

# Public transport labels
DOC_TRANSIT_KEYS = ("transit", "connection", "walk_to_stop", "walk_to_dest", "direction",
                    "transfers", "every_min", "every_hours", "timetable_note", "timetable_data",
                    "wheelchair_warning", "platform", "bus", "tram", "alternatives")
_DOC_TRANSIT: dict[str, tuple[str, ...]] = {
    "de": ("Mit Bus und Bahn", "Verbindung", "Zu Fuß zur Haltestelle {stop}", "Zu Fuß zum Ziel",
           "Richtung {headsign}", "Umstiege: {n}", "alle {n} Min.", "alle {n} Std.",
           "Fahrplanstand: {date}. Änderungen möglich – bitte vor der Fahrt prüfen.",
           "Fahrplandaten", "Barrierefreiheit laut Fahrplandaten nicht für alle Fahrten bestätigt",
           "Gleis/Steig {platform}", "Bus {line}", "Tram {line}", "Weitere Verbindungen"),
    "en": ("By bus and train", "Connection", "Walk to stop {stop}", "Walk to destination",
           "towards {headsign}", "Transfers: {n}", "every {n} min", "every {n} h",
           "Timetable as of {date}. Subject to change – please check before travelling.",
           "Timetable data", "Accessibility not confirmed for all trips in the timetable data",
           "Platform {platform}", "Bus {line}", "Tram {line}", "Other connections"),
    "cs": ("Veřejnou dopravou", "Spojení", "Pěšky na zastávku {stop}", "Pěšky do cíle",
           "směr {headsign}", "Přestupy: {n}", "každých {n} min", "každé {n} h",
           "Stav jízdního řádu: {date}. Změny vyhrazeny – před cestou ověřte.",
           "Data jízdních řádů", "Bezbariérovost není v datech potvrzena pro všechny spoje",
           "Nástupiště {platform}", "Autobus {line}", "Tramvaj {line}", "Další spojení"),
    "da": ("Med offentlig transport", "Forbindelse", "Gå til stoppested {stop}",
           "Gå til destinationen", "mod {headsign}", "Skift: {n}", "hvert {n}. min.",
           "hver {n}. time", "Køreplan pr. {date}. Ændringer forbeholdes – tjek før rejsen.",
           "Køreplansdata", "Tilgængelighed er ikke bekræftet for alle afgange i køreplansdata",
           "Spor/stoppested {platform}", "Bus {line}", "Sporvogn {line}", "Andre forbindelser"),
    "es": ("En transporte público", "Conexión", "A pie hasta la parada {stop}",
           "A pie hasta el destino", "dirección {headsign}", "Transbordos: {n}", "cada {n} min",
           "cada {n} h", "Horarios a fecha de {date}. Sujetos a cambios: compruébelos antes del viaje.",
           "Datos de horarios",
           "Accesibilidad no confirmada para todos los trayectos según los datos de horarios",
           "Andén {platform}", "Autobús {line}", "Tranvía {line}", "Otras conexiones"),
    "fi": ("Joukkoliikenteellä", "Yhteys", "Kävele pysäkille {stop}", "Kävele määränpäähän",
           "suuntaan {headsign}", "Vaihdot: {n}", "{n} min välein", "{n} h välein",
           "Aikataulut {date}. Muutokset mahdollisia – tarkista ennen matkaa.", "Aikataulutiedot",
           "Esteettömyyttä ei ole vahvistettu kaikille vuoroille aikataulutiedoissa",
           "Laituri {platform}", "Bussi {line}", "Raitiovaunu {line}", "Muut yhteydet"),
    "fr": ("En transports en commun", "Trajet", "À pied jusqu'à l'arrêt {stop}",
           "À pied jusqu'à la destination", "direction {headsign}", "Correspondances : {n}",
           "toutes les {n} min", "toutes les {n} h",
           "Horaires au {date}. Sous réserve de modifications – à vérifier avant le départ.",
           "Données horaires",
           "Accessibilité non confirmée pour tous les trajets selon les données horaires",
           "Quai {platform}", "Bus {line}", "Tram {line}", "Autres trajets"),
    "gr": ("Με μέσα μαζικής μεταφοράς", "Δρομολόγιο", "Με τα πόδια στη στάση {stop}",
           "Με τα πόδια στον προορισμό", "προς {headsign}", "Μετεπιβιβάσεις: {n}",
           "κάθε {n} λεπτά", "κάθε {n} ώρ.",
           "Δρομολόγια έως {date}. Ενδέχονται αλλαγές – ελέγξτε πριν από το ταξίδι.",
           "Δεδομένα δρομολογίων", "Η προσβασιμότητα δεν επιβεβαιώνεται για όλα τα δρομολόγια",
           "Αποβάθρα {platform}", "Λεωφορείο {line}", "Τραμ {line}", "Άλλα δρομολόγια"),
    "he": ("בתחבורה ציבורית", "מסלול", "הליכה לתחנה {stop}", "הליכה ליעד", "לכיוון {headsign}",
           "החלפות: {n}", "כל {n} דק׳", "כל {n} שע׳",
           "לוח זמנים נכון ל-{date}. ייתכנו שינויים – יש לבדוק לפני הנסיעה.",
           "נתוני לוחות זמנים", "הנגישות לא אושרה לכל הנסיעות בנתוני לוח הזמנים",
           "רציף {platform}", "אוטובוס {line}", "רכבת קלה {line}", "חיבורים נוספים"),
    "hu": ("Tömegközlekedéssel", "Útvonal", "Gyalog a(z) {stop} megállóig", "Gyalog az úti célig",
           "{headsign} felé", "Átszállások: {n}", "{n} percenként", "{n} óránként",
           "Menetrend állapota: {date}. Változások lehetségesek – utazás előtt ellenőrizze.",
           "Menetrendi adatok", "Az akadálymentesség nem minden járatnál megerősített",
           "Vágány/kocsiállás {platform}", "Busz {line}", "Villamos {line}", "További járatok"),
    "id": ("Dengan transportasi umum", "Rute", "Jalan kaki ke halte {stop}",
           "Jalan kaki ke tujuan", "arah {headsign}", "Transit: {n}", "setiap {n} mnt",
           "setiap {n} jam", "Jadwal per {date}. Dapat berubah – periksa sebelum berangkat.",
           "Data jadwal", "Aksesibilitas belum dikonfirmasi untuk semua perjalanan",
           "Peron {platform}", "Bus {line}", "Trem {line}", "Rute lainnya"),
    "it": ("Con i mezzi pubblici", "Collegamento", "A piedi fino alla fermata {stop}",
           "A piedi fino alla destinazione", "direzione {headsign}", "Cambi: {n}", "ogni {n} min",
           "ogni {n} h",
           "Orari aggiornati al {date}. Soggetti a modifiche – verificare prima del viaggio.",
           "Dati degli orari",
           "Accessibilità non confermata per tutte le corse secondo i dati degli orari",
           "Binario/fermata {platform}", "Autobus {line}", "Tram {line}", "Altri collegamenti"),
    "ja": ("公共交通機関で", "経路", "{stop}停留所まで徒歩", "目的地まで徒歩", "{headsign}行き",
           "乗り換え: {n}", "{n}分ごと", "{n}時間ごと",
           "{date}時点の時刻表です。変更の可能性があります。出発前にご確認ください。",
           "時刻表データ", "時刻表データでは全便のバリアフリー対応は確認されていません",
           "{platform}番線/乗り場", "バス {line}", "路面電車 {line}", "その他の経路"),
    "nl": ("Met het openbaar vervoer", "Verbinding", "Lopen naar halte {stop}",
           "Lopen naar de bestemming", "richting {headsign}", "Overstappen: {n}", "elke {n} min",
           "elke {n} u", "Dienstregeling per {date}. Wijzigingen voorbehouden – controleer voor vertrek.",
           "Dienstregelingsgegevens",
           "Toegankelijkheid niet voor alle ritten bevestigd in de dienstregelingsgegevens",
           "Spoor/perron {platform}", "Bus {line}", "Tram {line}", "Andere verbindingen"),
    "nb": ("Med kollektivtransport", "Forbindelse", "Gå til holdeplassen {stop}", "Gå til målet",
           "mot {headsign}", "Bytter: {n}", "hvert {n}. min", "hver {n}. time",
           "Rutetider per {date}. Endringer kan forekomme – sjekk før reisen.", "Rutedata",
           "Tilgjengelighet er ikke bekreftet for alle avganger i rutedataene",
           "Spor/plattform {platform}", "Buss {line}", "Trikk {line}", "Andre forbindelser"),
    "pl": ("Komunikacją miejską", "Połączenie", "Pieszo do przystanku {stop}", "Pieszo do celu",
           "kierunek {headsign}", "Przesiadki: {n}", "co {n} min", "co {n} godz.",
           "Rozkład jazdy z dnia {date}. Możliwe zmiany – sprawdź przed podróżą.",
           "Dane rozkładowe",
           "Dostępność dla niepełnosprawnych nie jest potwierdzona dla wszystkich kursów",
           "Peron/stanowisko {platform}", "Autobus {line}", "Tramwaj {line}", "Inne połączenia"),
    "pt": ("De transportes públicos", "Ligação", "A pé até à paragem {stop}",
           "A pé até ao destino", "sentido {headsign}", "Transbordos: {n}", "a cada {n} min",
           "a cada {n} h", "Horários de {date}. Sujeitos a alterações – confirme antes da viagem.",
           "Dados de horários",
           "Acessibilidade não confirmada para todas as viagens nos dados de horários",
           "Plataforma {platform}", "Autocarro {line}", "Elétrico {line}", "Outras ligações"),
    "ro": ("Cu transportul public", "Legătură", "Pe jos până la stația {stop}",
           "Pe jos până la destinație", "direcția {headsign}", "Schimbări: {n}",
           "la fiecare {n} min", "la fiecare {n} h",
           "Orar valabil la {date}. Pot apărea modificări – verificați înainte de călătorie.",
           "Date de orar", "Accesibilitatea nu este confirmată pentru toate cursele",
           "Linia/peronul {platform}", "Autobuzul {line}", "Tramvaiul {line}", "Alte legături"),
    "ru": ("На общественном транспорте", "Маршрут", "Пешком до остановки {stop}",
           "Пешком до места назначения", "в направлении {headsign}", "Пересадки: {n}",
           "каждые {n} мин", "каждые {n} ч",
           "Расписание на {date}. Возможны изменения – проверьте перед поездкой.",
           "Данные расписания",
           "Доступность для инвалидных колясок подтверждена не для всех рейсов",
           "Путь/платформа {platform}", "Автобус {line}", "Трамвай {line}", "Другие варианты"),
    "tr": ("Toplu taşıma ile", "Bağlantı", "{stop} durağına yürüyün", "Varış noktasına yürüyün",
           "{headsign} yönü", "Aktarma: {n}", "{n} dk'da bir", "{n} saatte bir",
           "Tarife durumu: {date}. Değişiklik olabilir – yolculuktan önce kontrol edin.",
           "Tarife verileri",
           "Erişilebilirlik tarife verilerinde tüm seferler için doğrulanmamıştır",
           "Peron {platform}", "Otobüs {line}", "Tramvay {line}", "Diğer bağlantılar"),
    "ua": ("Громадським транспортом", "Маршрут", "Пішки до зупинки {stop}",
           "Пішки до пункту призначення", "у напрямку {headsign}", "Пересадки: {n}",
           "кожні {n} хв", "кожні {n} год",
           "Розклад станом на {date}. Можливі зміни – перевірте перед поїздкою.",
           "Дані розкладу", "Доступність для візків підтверджена не для всіх рейсів",
           "Колія/платформа {platform}", "Автобус {line}", "Трамвай {line}", "Інші варіанти"),
    "vi": ("Bằng phương tiện công cộng", "Tuyến đi", "Đi bộ đến trạm {stop}",
           "Đi bộ đến điểm đến", "hướng {headsign}", "Chuyển tuyến: {n}", "mỗi {n} phút",
           "mỗi {n} giờ",
           "Lịch trình tính đến {date}. Có thể thay đổi – vui lòng kiểm tra trước khi đi.",
           "Dữ liệu lịch trình", "Khả năng tiếp cận chưa được xác nhận cho tất cả chuyến",
           "Sân ga {platform}", "Xe buýt {line}", "Xe điện {line}", "Tuyến khác"),
    "zh": ("乘坐公共交通", "换乘方案", "步行至{stop}站", "步行至目的地", "开往{headsign}方向",
           "换乘次数: {n}", "每 {n} 分钟一班", "每 {n} 小时一班",
           "时刻表截至 {date}，可能有变动，请出行前确认。", "时刻表数据",
           "时刻表数据未确认所有班次均无障碍", "站台 {platform}", "公交 {line}路",
           "有轨电车 {line}", "其他方案"),
    "ar": ("بالمواصلات العامة", "الرحلة", "امشِ إلى محطة {stop}", "امشِ إلى الوجهة",
           "باتجاه {headsign}", "عدد التبديلات: {n}", "كل {n} دقيقة", "كل {n} ساعات",
           "الجدول الزمني بتاريخ {date}. قد تحدث تغييرات – يرجى التحقق قبل السفر.",
           "بيانات الجدول الزمني", "إمكانية الوصول بالكرسي المتحرك غير مؤكدة لجميع الرحلات",
           "الرصيف {platform}", "حافلة {line}", "ترام {line}", "رحلات أخرى"),
    "fa": ("با حمل‌ونقل عمومی", "مسیر سفر", "پیاده تا ایستگاه {stop}", "پیاده تا مقصد",
           "به سمت {headsign}", "تعداد تعویض: {n}", "هر {n} دقیقه", "هر {n} ساعت",
           "برنامهٔ زمانی تا تاریخ {date}. ممکن است تغییر کند – لطفاً پیش از سفر بررسی کنید.",
           "داده‌های برنامهٔ زمانی", "دسترسی با ویلچر برای همهٔ سفرها تأیید نشده است",
           "سکوی {platform}", "اتوبوس {line}", "تراموا {line}", "مسیرهای دیگر"),
    "ta": ("பொதுப் போக்குவரத்தில்", "பயண வழி", "{stop} நிறுத்தத்திற்கு நடந்து செல்லவும்",
           "சேருமிடத்திற்கு நடந்து செல்லவும்", "{headsign} நோக்கி", "மாற்றங்கள்: {n}",
           "ஒவ்வொரு {n} நிமிடத்திற்கும்", "ஒவ்வொரு {n} மணி நேரத்திற்கும்",
           "{date} நிலவரப்படி கால அட்டவணை. மாற்றங்கள் இருக்கலாம் – பயணத்திற்கு முன் சரிபார்க்கவும்.",
           "கால அட்டவணைத் தரவு",
           "எல்லாப் பயணங்களுக்கும் சக்கர நாற்காலி அணுகல் உறுதிப்படுத்தப்படவில்லை",
           "நடைமேடை {platform}", "பேருந்து {line}", "டிராம் {line}", "பிற வழிகள்"),
    "so": ("Gaadiidka dadweynaha", "Socdaalka", "U soco joogsiga {stop}", "U soco meesha loo socdo",
           "u socda {headsign}", "Beddelaadda: {n}", "{n}-kii daqiiqoba mar", "{n}-kii saacadoodba mar",
           "Jadwalka ilaa {date}. Isbeddel ayaa dhici kara – fadlan hubi kahor safarka.",
           "Xogta jadwalka", "Helitaanka kursiga curyaanka lama xaqiijin dhammaan safarada",
           "Madal {platform}", "Bas {line}", "Taraam {line}", "Ikhtiyaarro kale"),
    "ti": ("ብሕዝባዊ መጓዓዝያ", "ጉዕዞ", "ብእግሪ ናብ መዕረፊ {stop}", "ብእግሪ ናብ መዕለቢ", "ናብ {headsign}",
           "ምቕያር፡ {n}", "ኣብ ነፍሲ ወከፍ {n} ደቒቕ", "ኣብ ነፍሲ ወከፍ {n} ሰዓት",
           "ሰሌዳ ግዜ ክሳብ {date}። ለውጢ ክህሉ ይኽእል – በጃኹም ቅድሚ ጉዕዞ ኣረጋግጹ።",
           "ሓበሬታ ሰሌዳ ግዜ", "ንተሽከርካሪ ወንበር ተበጻሒነት ንኹሉ ጉዕዞታት ኣይተረጋገጸን",
           "መድረኽ {platform}", "ኣውቶቡስ {line}", "ትራም {line}", "ካልኦት ኣማራጺታት"),
}

# Mode label for bicycle routes
_DOC_BIKE: dict[str, str] = {
    "de": "Mit dem Fahrrad", "en": "By bike", "cs": "Na kole", "da": "På cykel",
    "es": "En bicicleta", "fi": "Pyörällä", "fr": "À vélo", "gr": "Με ποδήλατο",
    "he": "באופניים", "hu": "Kerékpárral", "id": "Dengan sepeda", "it": "In bicicletta",
    "ja": "自転車で", "nl": "Met de fiets", "nb": "Med sykkel", "pl": "Rowerem",
    "pt": "De bicicleta", "ro": "Cu bicicleta", "ru": "На велосипеде", "tr": "Bisikletle",
    "ua": "Велосипедом", "vi": "Bằng xe đạp", "zh": "骑自行车", "ar": "بالدراجة",
    "fa": "با دوچرخه", "ta": "சைக்கிளில்", "so": "Baaskiil", "ti": "ብብሽክለታ",
}

DOC_KEYS = DOC_KEYS + DOC_EXTRA_KEYS + DOC_TRANSIT_KEYS + ("bike",)

DOC_STRINGS: dict[str, dict[str, str]] = {
    lang: dict(zip(DOC_KEYS, values + _DOC_EXTRA[lang] + _DOC_TRANSIT[lang] + (_DOC_BIKE[lang],),
                   strict=True))
    for lang, values in _DOC_TABLE.items()
}

# Unit symbols where the Latin "km"/"m" is not customary.
_UNITS = {"ru": ("км", "м"), "ua": ("км", "м"), "gr": ("χλμ", "μ"),
          "he": ('ק"מ', "מ׳"), "zh": ("公里", "米"), "ar": ("كم", "م"),
          "fa": ("کیلومتر", "متر")}

# --- Turn-by-turn instructions for languages openrouteservice does not support ----
# openrouteservice step types (instruction "type"): 0 left, 1 right, 2 sharp left,
# 3 sharp right, 4 slight left, 5 slight right, 6 straight, 7 enter roundabout,
# 8 exit roundabout, 9 u-turn, 10 goal, 11 depart, 12 keep left, 13 keep right.
# Street names are appended as "<action> – <street>" to avoid grammar per language.
MANEUVER_KEYS = ("left", "right", "sharp_left", "sharp_right", "slight_left", "slight_right",
                 "straight", "roundabout", "roundabout_exit", "uturn", "arrive", "depart",
                 "keep_left", "keep_right")
_MANEUVERS: dict[str, tuple[str, ...]] = {
    "ar": ("انعطف يسارًا", "انعطف يمينًا", "انعطف بحدة إلى اليسار", "انعطف بحدة إلى اليمين",
           "انعطف قليلًا إلى اليسار", "انعطف قليلًا إلى اليمين", "تابع مباشرة",
           "في الدوار، اسلك المخرج رقم {n}", "اخرج من الدوار", "استدر للخلف",
           "لقد وصلت إلى وجهتك", "ابدأ", "الزم اليسار", "الزم اليمين"),
    "fa": ("به چپ بپیچید", "به راست بپیچید", "به‌شدت به چپ بپیچید", "به‌شدت به راست بپیچید",
           "کمی به چپ بپیچید", "کمی به راست بپیچید", "مستقیم ادامه دهید",
           "در میدان از خروجی {n} خارج شوید", "از میدان خارج شوید", "دور بزنید",
           "به مقصد رسیدید", "حرکت کنید", "سمت چپ بمانید", "سمت راست بمانید"),
    "ta": ("இடதுபுறம் திரும்பவும்", "வலதுபுறம் திரும்பவும்", "கூர்மையாக இடதுபுறம் திரும்பவும்",
           "கூர்மையாக வலதுபுறம் திரும்பவும்", "சற்று இடதுபுறம் திரும்பவும்",
           "சற்று வலதுபுறம் திரும்பவும்", "நேராகச் செல்லவும்",
           "சுற்றுவட்டத்தில் {n}-வது வெளியேற்றத்தில் செல்லவும்",
           "சுற்றுவட்டத்திலிருந்து வெளியேறவும்", "திரும்பிச் செல்லவும் (U-திருப்பம்)",
           "நீங்கள் சேருமிடத்தை அடைந்துவிட்டீர்கள்", "புறப்படவும்", "இடதுபுறமாகவே செல்லவும்",
           "வலதுபுறமாகவே செல்லவும்"),
    "so": ("U leexo bidix", "U leexo midig", "Si adag ugu leexo bidix", "Si adag ugu leexo midig",
           "Wax yar u leexo bidix", "Wax yar u leexo midig", "Toos u soco",
           "Wareegga ka bax bixitaanka {n}aad", "Ka bax wareegga", "Dib u noqo (U-turn)",
           "Waxaad gaartay meesha aad u socotay", "Bilow", "Bidix ku sii soco", "Midig ku sii soco"),
    "ti": ("ናብ ጸጋም ተጠወ", "ናብ የማን ተጠወ", "ብትሪ ናብ ጸጋም ተጠወ", "ብትሪ ናብ የማን ተጠወ",
           "ቁሩብ ናብ ጸጋም ተጠወ", "ቁሩብ ናብ የማን ተጠወ", "ብቐጥታ ቀጽል", "ኣብ ዙርያ፡ {n}ይ መውጽኢ ውሰድ",
           "ካብ ዙርያ ውጻእ", "ተመለስ (U-turn)", "ናብ መዕለቢኻ በጺሕካ ኢኻ", "ጀምር", "ብጸጋም ቀጽል",
           "ብየማን ቀጽል"),
}
MANEUVERS: dict[str, dict[str, str]] = {
    lang: dict(zip(MANEUVER_KEYS, values, strict=True)) for lang, values in _MANEUVERS.items()
}
# Languages whose instructions come from openrouteservice directly
ORS_LANGUAGES = frozenset(DIRECTIONS_LANGUAGES) - frozenset(MANEUVERS)


def ors_language(lang: str) -> str:
    """Language to request from openrouteservice (English data for generated languages)."""
    return lang if lang in ORS_LANGUAGES else "en"

PROFILE_KEYS = {"driving-car": "car", "foot-walking": "foot", "transit": "transit",
                "cycling-regular": "bike"}


PINNED_LANGUAGES = ("de", "en")


def _sort_key(text: str) -> str:
    """Case- and accent-insensitive ('Dänisch' sorts under D)."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(c))


def directions_language_options(ui_lang: str) -> dict[str, tuple[str, str]]:
    """code -> (native name, name as UI msgid); German and English first, the rest
    alphabetically by their name in the UI language."""
    rest = sorted((c for c in DIRECTIONS_LANGUAGES if c not in PINNED_LANGUAGES),
                  key=lambda c: _sort_key(translate(ui_lang, LANGUAGE_NAMES[c])))
    return {c: (DIRECTIONS_LANGUAGES[c][0], LANGUAGE_NAMES[c]) for c in (*PINNED_LANGUAGES, *rest)}


def normalize_directions_lang(lang: str | None) -> str:
    return lang if lang in DIRECTIONS_LANGUAGES else DEFAULT_DIRECTIONS_LANG



# --- Means of transport actually used ("Mit Bus und Bahn", "Mit Bus") ----------
# MOTIS mode -> kind; unknown modes (OTHER, ...) fall back to the generic "transit" text
TRANSIT_KINDS = ("bus", "tram", "metro", "train", "ferry", "cable")
MODE_KINDS = {
    "BUS": "bus", "COACH": "bus", "TRAM": "tram", "SUBWAY": "metro", "METRO": "metro",
    "SUBURBAN": "train", "REGIONAL_RAIL": "train", "REGIONAL_FAST_RAIL": "train", "RAIL": "train",
    "LONG_DISTANCE": "train", "HIGHSPEED_RAIL": "train", "NIGHT_RAIL": "train",
    "FERRY": "ferry", "FUNICULAR": "cable", "AERIAL_LIFT": "cable", "CABLE_CAR": "cable",
}
# lang -> (template with {modes}, nouns in the form the template needs (order of
# TRANSIT_KINDS), separator, separator before the last item). Nouns are inflected where
# the language requires it (instrumental in pl/cs/ua, adessive in fi, ...).
TRANSIT_MODE_PHRASES: dict[str, tuple[str, tuple[str, ...], str, str]] = {
    "de": ("Mit {modes}", ("Bus", "Straßenbahn", "U-Bahn", "Bahn", "Fähre", "Seilbahn"), ", ", " und "),
    "en": ("By {modes}", ("bus", "tram", "underground", "train", "ferry", "cable car"), ", ", " and "),
    "fr": ("{modes}", ("en bus", "en tram", "en métro", "en train", "en ferry", "en téléphérique"), ", ", " et "),
    "es": ("En {modes}", ("autobús", "tranvía", "metro", "tren", "ferry", "teleférico"), ", ", " y "),
    "it": ("In {modes}", ("autobus", "tram", "metropolitana", "treno", "traghetto", "funivia"), ", ", " e "),
    "pt": ("De {modes}", ("autocarro", "elétrico", "metro", "comboio", "ferry", "teleférico"), ", ", " e "),
    "nl": ("Met {modes}", ("bus", "tram", "metro", "trein", "veerboot", "kabelbaan"), ", ", " en "),
    "da": ("Med {modes}", ("bus", "sporvogn", "metro", "tog", "færge", "svævebane"), ", ", " og "),
    "nb": ("Med {modes}", ("buss", "trikk", "T-bane", "tog", "ferje", "taubane"), ", ", " og "),
    "fi": ("{modes}", ("bussilla", "raitiovaunulla", "metrolla", "junalla", "lautalla", "köysiradalla"), ", ", " ja "),
    "cs": ("{modes}", ("autobusem", "tramvají", "metrem", "vlakem", "přívozem", "lanovkou"), ", ", " a "),
    "pl": ("{modes}", ("autobusem", "tramwajem", "metrem", "pociągiem", "promem", "kolejką linową"), ", ", " i "),
    "hu": ("{modes}", ("busszal", "villamossal", "metróval", "vonattal", "komppal", "kötélpályával"), ", ", " és "),
    "ro": ("Cu {modes}", ("autobuzul", "tramvaiul", "metroul", "trenul", "feribotul", "telecabina"), ", ", " și "),
    "gr": ("Με {modes}", ("λεωφορείο", "τραμ", "μετρό", "τρένο", "φέρι", "τελεφερίκ"), ", ", " και "),
    "ru": ("На {modes}", ("автобусе", "трамвае", "метро", "поезде", "пароме", "канатной дороге"), ", ", " и "),
    "ua": ("{modes}", ("автобусом", "трамваєм", "метро", "поїздом", "поромом", "канатною дорогою"), ", ", " і "),
    "tr": ("{modes} ile", ("Otobüs", "Tramvay", "Metro", "Tren", "Feribot", "Teleferik"), ", ", " ve "),
    "ar": ("ب{modes}", ("الحافلة", "الترام", "المترو", "القطار", "العبّارة", "التلفريك"), "، ", " و"),
    "fa": ("با {modes}", ("اتوبوس", "تراموا", "مترو", "قطار", "کشتی", "تله‌کابین"), "، ", " و "),
    "he": ("{modes}", ("באוטובוס", "ברכבת קלה", "ברכבת התחתית", "ברכבת", "במעבורת", "ברכבל"), ", ", " ו"),
    "ja": ("{modes}で", ("バス", "路面電車", "地下鉄", "電車", "フェリー", "ロープウェイ"), "・", "と"),
    "zh": ("乘坐{modes}", ("公交", "有轨电车", "地铁", "火车", "渡轮", "缆车"), "、", "和"),
    "vi": ("Bằng {modes}", ("xe buýt", "xe điện", "tàu điện ngầm", "tàu hỏa", "phà", "cáp treo"), ", ", " và "),
    "id": ("Dengan {modes}", ("bus", "trem", "kereta bawah tanah", "kereta", "feri", "kereta gantung"), ", ", " dan "),
    "ta": ("{modes} மூலம்", ("பேருந்து", "டிராம்", "மெட்ரோ", "ரயில்", "படகு", "கம்பிவட ஊர்தி"), ", ", " மற்றும் "),
    "so": ("{modes}", ("Bas", "Taraam", "Tareenka dhulka hoostiisa", "Tareen", "Doon", "Wiish"), ", ", " iyo "),
    "ti": ("ብ{modes}", ("ኣውቶቡስ", "ትራም", "ሜትሮ", "ባቡር", "መርከብ", "ገመዳዊ መጓዓዝያ"), "፣ ", "፣ "),
}

class DirectionsText:
    """Labels and number formatting for a directions language."""

    def __init__(self, lang: str):
        self.lang = normalize_directions_lang(lang)
        self.name, self.html_lang, self.rtl, self._dec = DIRECTIONS_LANGUAGES[self.lang]
        self._strings = DOC_STRINGS[self.lang]

    def __call__(self, key: str, **params) -> str:
        text = self._strings[key]
        return text.format(**params) if params else text

    def markup(self, key: str, **params) -> Markup:
        """Like calling, but for HTML output: the text is escaped, Markup params are kept."""
        return escape(self._strings[key]).format(**params)

    @property
    def dir(self) -> str:
        return "rtl" if self.rtl else "ltr"

    def instruction(self, step) -> str:
        """ORS instruction text, or generated from the maneuver type for other languages."""
        templates = MANEUVERS.get(self.lang)
        if not templates or getattr(step, "type", None) is None:
            return step.instruction
        key = MANEUVER_KEYS[step.type] if 0 <= step.type < len(MANEUVER_KEYS) else "straight"
        if key == "roundabout":
            text = templates[key].format(n=step.exit_number or "?")
        else:
            text = templates[key]
        name = (step.name or "").strip()
        if name and name != "-" and key not in ("arrive", "roundabout_exit"):
            text = f"{text} – {name}"
        return text

    def profile(self, profile: str) -> str:
        return self(PROFILE_KEYS.get(profile, "car"))

    def transit_modes(self, legs) -> str:
        """'Mit Bus', 'Mit Bus und Bahn' ... from the rides of a connection; the generic
        'public transport' text if a mode is unknown or no phrase exists."""
        kinds = set()
        for leg in legs:
            if getattr(leg, "kind", "") == "walk":
                continue
            kind = MODE_KINDS.get(getattr(leg, "mode", ""))
            if kind is None:
                return self("transit")
            kinds.add(kind)
        phrase = TRANSIT_MODE_PHRASES.get(self.lang)
        if not kinds or phrase is None:
            return self("transit")
        template, nouns, sep, last_sep = phrase
        items = [nouns[TRANSIT_KINDS.index(k)] for k in TRANSIT_KINDS if k in kinds]
        modes = items[0] if len(items) == 1 else sep.join(items[:-1]) + last_sep + items[-1]
        text = template.format(modes=modes)
        return text[:1].upper() + text[1:]

    def distance(self, meters: float) -> str:
        km, m = _UNITS.get(self.lang, ("km", "m"))
        if meters < 1000:
            return f"{round(meters / 10) * 10:.0f} {m}"
        return f"{meters / 1000:.1f}".replace(".", self._dec) + f" {km}"

    def duration(self, seconds: float) -> str:
        minutes = max(1, round(seconds / 60))
        if minutes < 60:
            return self("minutes", n=minutes)
        return self("hours", h=minutes // 60, m=minutes % 60)

    def summary(self, meters: float, seconds: float) -> str:
        return self("summary", distance=self.distance(meters), duration=self.duration(seconds))

    def date(self, d: date) -> str:
        return d.strftime(self("date"))

    def headway(self, minutes: int | None) -> str:
        if not minutes:
            return ""
        if minutes >= 120 and minutes % 60 == 0:
            return self("every_hours", n=minutes // 60)
        return self("every_min", n=minutes)

    def line(self, mode: str, line: str) -> str:
        """'Bus 5' / 'Straßenbahn 4'; trains already carry their type ('RE 4', 'S1')."""
        if mode == "BUS" and line:
            return self("bus", line=line)
        if mode == "TRAM" and line:
            return self("tram", line=line)
        return line or mode.title()

    def transit_summary(self, duration_s: float, transfers: int, headway_min: int | None) -> str:
        parts = [self.duration(duration_s), self("transfers", n=transfers)]
        if headway_min:
            parts.append(self.headway(headway_min))
        return " · ".join(parts)
