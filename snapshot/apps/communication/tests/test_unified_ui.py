"""UI-Marker des Dizz-Chat-Umbaus (statische Prüfung; der echte Browser-Feel-Check
ist 👤). Stellt sicher, dass das Frontend die Panels + Lade-/Aktions-Funktionen +
Endpunkte verdrahtet — damit ein Refactor die Verdrahtung nicht still abreißt.
CSP-strikt: keine inline-Handler."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from kommapp.main import build_app


def test_dizzchat_ui_marker(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in (
                # Panels: Dizz Chat (Kern) + Kontakte/Smart Contacts + Konten/Konnektoren
                ">Dizz Chat<", "Smart Contacts", "Konten &amp; Konnektoren",
                'id="dizzchat"',
                # Dizz-Chat-Container (Verlauf + Triage-Summary + Termin-Flow + Video)
                'id="uni-liste"', 'id="uni-thread"', 'id="triageout"',
                'id="termine-vorschlaege"', 'id="jitsi-frame"', 'id="chat-triage-btn"',
                # Kontakte-Panel (Smart Contacts: Suche/Sort/Kategorie/Favoriten)
                'id="kontakte"', 'id="kontakte-suche"', 'id="kontakte-sort"',
                'id="kontakte-kat"', 'id="kontakte-vorschlaege"', 'id="kontakte-simform"',
                # Konten-Panel: Connector-Katalog + Kanal-Strip
                'id="kanaele-strip"', 'id="konnektoren-liste"',
                # Render-/Aktions-Funktionen
                "function ladeSmartInbox", "function oeffneUniKontakt",
                "function ladeKontakte", "function ladeKonnektoren",
                "function chatTriage", "function termineAnlegen",
                "function toggleFavorit", "function setKategorie",
                "function videoBeitreten", "function uniAntwort",
                # Delegation (CSP-strikt) + Endpunkte
                'data-dz-act="chatTriage"', 'data-dz-act="toggleFavorit"',
                'data-dz-act="setKategorie"', 'data-dz-act="videoFuerKontakt"',
                "/api/smartkontakte", "/verlauf", "/antwort", "/api/konnektoren",
                "/api/termine/anlegen", "/favorit", "/kategorie",
                # in den Lade-Zyklus eingehängt
                "ladeKontakte();", "ladeKonnektoren();"):
            assert marker in html, marker
        # CSP-strikt: keine inline-Event-Handler
        assert re.search(r"\son[a-z]+=[\"']", html) is None
