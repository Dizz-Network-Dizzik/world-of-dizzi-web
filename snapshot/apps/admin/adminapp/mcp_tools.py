"""Deklarative MCP-Tool-Liste von Dizz Admin — EINE Quelle für (a) den stdio-MCP-
Server (``mcp_server.py``, für den Core-Agent) und (b) das per-App-MCP-Gateway
(``main.py`` → ``appkit.app_gateway``, für den Standalone-Betrieb). Reine Daten —
kein fastmcp-Import ⇒ die laufende App kann sie ohne MCP-Abhängigkeit einlesen.

Jeder Eintrag ``(tool_name, api_pfad, beschreibung)`` = read-only GET auf die App-API
(Namensraum ``admin_`` wird automatisch gesetzt, docs/16 §6)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("geschaefts_kpis", "/api/stats",
     "Geschäfts-Kennzahlen: Umsatz (bezahlt), offene/überfällige Rechnungen, "
     "Kunden, MRR, offener Support, fällige Fristen."),
    ("offene_rechnungen", "/api/rechnungen?status=offen",
     "Alle offenen (gestellten, noch nicht bezahlten) Rechnungen mit Nummer/Kunde/Betrag/Fälligkeit."),
    ("naechste_fristen", "/api/fristen?offen=1",
     "Offene Geschäfts-Fristen (Steuer/Rechnung/Vertrag/Behörde) nach Fälligkeit."),
    ("mahn_vorschlaege", "/api/mahnungen/vorschlaege",
     "Mahnwesen: welche überfällige offene Rechnung braucht (die nächste) Mahnstufe "
     "(Zahlungserinnerung/1./2. Mahnung) — deterministischer Vorschlag, read-only."),
    ("faellige_abos", "/api/rechnung-abos/faellig",
     "Wiederkehrende Rechnungen: welche Abo-Vorlagen sind zum Ziehen fällig "
     "(erzeugen Entwurfs-Rechnungen) — read-only Vorschau."),
    ("netzwerk_status", "/api/netzwerk",
     "Kuratierte Übersicht der Schwester-Apps (online?, Status) — read-only über den Core."),
    ("studien_uebersicht", "/api/studien/uebersicht",
     "Studien-/Ausbildungs-Übersicht: je laufendem Bildungsweg ECTS-Fortschritt, "
     "Notenschnitt, Fachsemester, Risiko-Module, nächste Fristen."),
    ("studien_fristen", "/api/studienfristen",
     "Offene Studien-/Prüfungsfristen (Anmeldung/Abgabe/Rückmeldung/…) über alle "
     "Bildungswege, nach Fälligkeit."),
    ("pruefungsversuche_warnung", "/api/studien/warnungen",
     "Module im Prüfungsversuch-Risiko (letzter Versuch / endgültig nicht bestanden) — "
     "existenziell, früh warnen."),
    ("bereiche", "/api/bereiche",
     "Alle Bereiche/Kontexte (Studium · Geschäft · Mandant · Fortbildung) — die "
     "Kategorie-Achse, an der Dokumente/Projekte/Rechnungen/Fristen kategorisiert hängen."),
    ("fristen_cockpit", "/api/fristen-cockpit",
     "Netzwerkweite Frist-Sicht über ALLE Module (Aufgaben/Termine/Rechnungen/Geschäfts-/"
     "Studien-Fristen), nach Dringlichkeit gruppiert + je Bereich aufgeschlüsselt."),
    ("dokumente", "/api/dokumente",
     "Dokument-Tresor: abgelegte Dokumente mit Typ/Korrespondent/Tags (Volltext-Suche via ?suche=)."),
    ("projekte", "/api/projekte",
     "Projekte der Projektverwaltung mit Status/Fortschritt."),
    ("erinnerungen", "/api/erinnerungen",
     "Projekt-Wächter: überfällige/heute/demnächst fällige Aufgaben + anstehende Termine."),
    ("suche", "/api/suche",
     "Globale Cross-Modul-Suche über Dokumente/Projekte/Aufgaben/Rechnungen/Kunden/Studium (Param ?q=)."),
    ("konnektoren", "/api/konnektoren",
     "Externe-Tool-Konnektoren (Kalender/Projekt/Office-Dienste) im Überblick — "
     "angedockte Instanzen + Typen-Register + Token-/Verbunden-Status (read-only)."),
]

MCP_INSTRUCTIONS = (
    "Read-only Einblick in Dizz Admin (vereinte Verwaltung): Bereiche/Kontexte, "
    "Tresor-Dokumente, Projekte, Geschäfts-KPIs/Rechnungen, Studien, Fristen-Cockpit, "
    "Netzwerk-Status. Beobachten + erinnern (HITL), nie eigenmächtig buchen/handeln; "
    "Geschäfts-/Steuer-/Studien-Daten bleiben lokal.")
