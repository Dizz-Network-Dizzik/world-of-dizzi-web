"""Notiz-Vorlagen / Templates (docs/33): CRUD + „neue Notiz aus Vorlage".
Platzhalter ({{datum}}/{{titel}}/{{zeit}}) werden gefüllt, dann läuft der normale
Notiz-Schreibpfad (Index + Vault + FTS). Spiegelt die Ordner-/Notiz-CRUD-Tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.vault import MarkdownVault


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _vault(tmp_path) -> MarkdownVault:
    return MarkdownVault(Path(tmp_path) / "apps" / "memory" / "vault")


def test_template_crud(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/templates", json={
            "name": "Meeting", "inhalt": "# {{titel}}\nDatum: {{datum}}",
            "ordner_default": "Meetings"}).json()["id"]
        # in der Liste
        liste = c.get("/api/templates").json()
        assert [t["name"] for t in liste] == ["Meeting"]
        assert liste[0]["ordner_default"] == "Meetings"
        # Detail trägt den Inhalt
        d = c.get(f"/api/templates/{tid}").json()
        assert d["inhalt"].startswith("# {{titel}}") and d["ordner_default"] == "Meetings"
        # Ändern
        c.put(f"/api/templates/{tid}", json={"name": "Meeting-Notiz", "inhalt": "geändert"})
        d2 = c.get(f"/api/templates/{tid}").json()
        assert d2["name"] == "Meeting-Notiz" and d2["inhalt"] == "geändert"
        assert d2["ordner_default"] == "Meetings"   # unberührt
        # Löschen (soft) ⇒ raus aus Liste, Detail 404
        c.delete(f"/api/templates/{tid}")
        assert c.get("/api/templates").json() == []
        assert c.get(f"/api/templates/{tid}").status_code == 404


def test_aus_template_fuellt_platzhalter_und_schreibt(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/templates", json={
            "name": "Tagebuch",
            "inhalt": "# {{titel}}\nHeute ({{datum}}) notiere ich:\n- "}).json()["id"]
        r = c.post(f"/api/notizen/aus-template/{tid}",
                   json={"titel": "Reflexion"}).json()
        assert r["ok"] and r["titel"] == "Reflexion"
        heute = date.today().isoformat()

        # Notiz existiert, Platzhalter gefüllt
        d = c.get(f"/api/notizen/{r['id']}").json()
        assert d["titel"] == "Reflexion"
        assert "# Reflexion" in d["inhalt"] and heute in d["inhalt"]
        assert "{{" not in d["inhalt"]              # keine bekannten Platzhalter mehr

        # FTS-Index gefüllt (= normaler Schreibpfad lief) ⇒ Volltextsuche findet sie
        treffer = c.get("/api/suche", params={"q": "Reflexion"}).json()
        assert r["id"] in [t["id"] for t in treffer]

        # Vault-Datei gespiegelt, mit gefülltem Körper
        v = _vault(tmp_path)
        dateien = list(v.iter_dateien("dizzi"))
        assert len(dateien) == 1
        _, fm, body = dateien[0]
        assert fm["id"] == r["id"] and heute in body


def test_aus_template_ordner_default_wird_angelegt(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/templates", json={
            "name": "Wochenplan", "inhalt": "Plan", "ordner_default": "Planung/2026"}).json()["id"]
        r = c.post(f"/api/notizen/aus-template/{tid}", json={"titel": "KW26"}).json()
        # Ordner-Kette „Planung/2026" wurde angelegt, Notiz liegt im Blatt-Ordner
        ordner = {o["name"]: o for o in c.get("/api/ordner").json()}
        assert "Planung" in ordner and "2026" in ordner
        d = c.get(f"/api/notizen/{r['id']}").json()
        assert d["ordner_id"] == r["ordner_id"] == ordner["2026"]["id"]


def test_aus_template_ordner_override(tmp_path):
    with _client(tmp_path) as c:
        ziel = c.post("/api/ordner", json={"name": "Inbox"}).json()["id"]
        tid = c.post("/api/templates", json={
            "name": "Idee", "inhalt": "x", "ordner_default": "Ideen"}).json()["id"]
        r = c.post(f"/api/notizen/aus-template/{tid}",
                   json={"titel": "Blitzidee", "ordner_id": ziel}).json()
        assert r["ordner_id"] == ziel
        # der override gewinnt ⇒ „Ideen" wurde NICHT angelegt
        assert "Ideen" not in {o["name"] for o in c.get("/api/ordner").json()}


def test_aus_template_unbekannter_platzhalter_bleibt(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/templates", json={
            "name": "X", "inhalt": "Hallo {{titel}}, siehe {{unbekannt}}."}).json()["id"]
        r = c.post(f"/api/notizen/aus-template/{tid}", json={"titel": "Welt"}).json()
        d = c.get(f"/api/notizen/{r['id']}").json()
        assert d["inhalt"] == "Hallo Welt, siehe {{unbekannt}}."


def test_aus_template_titel_default_und_404(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/templates", json={"name": "Standard", "inhalt": "y"}).json()["id"]
        # leerer Titel ⇒ Vorlagen-Name als Notiz-Titel
        r = c.post(f"/api/notizen/aus-template/{tid}", json={}).json()
        assert r["titel"] == "Standard"
        # unbekannte Vorlage ⇒ 404
        assert c.post("/api/notizen/aus-template/gibtsnicht", json={}).status_code == 404
