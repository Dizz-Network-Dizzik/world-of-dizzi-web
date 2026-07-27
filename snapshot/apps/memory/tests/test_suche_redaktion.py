"""KA-M6: sensible Notizen erscheinen in der Suche (id/titel/sensibel), aber ihr Auszug
ist redigiert ("") — der vertrauliche Inhalt darf nie über einen Treffer-Snippet leaken
(auch nicht cross-app über das Core-Relay). FTS-Pfad reicht als Beweis der Redaktions-Naht;
semantisch/hybrid nutzen dieselbe ``d.get("sensibel")``-Wache."""
from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def test_suche_redigiert_sensiblen_auszug(tmp_path):
    app = am.build_app(data_dir=tmp_path, start_import_timer=False,
                       http_post=lambda url, json: None)
    with TestClient(app) as c:
        c.post("/api/notizen", json={
            "titel": "Oeffentlich",
            "inhalt": "das geheimwort erscheint hier voellig offen."})
        c.post("/api/notizen", json={
            "titel": "Privat", "sensibel": True,
            "inhalt": "das geheimwort steht in einer sensiblen notiz."})
        treffer = c.get("/api/suche", params={"q": "geheimwort"}).json()
        assert len(treffer) == 2                          # beide erscheinen als Treffer
        nach_titel = {t["titel"]: t for t in treffer}
        assert nach_titel["Privat"]["sensibel"] is True
        assert nach_titel["Privat"]["auszug"] == ""       # sensibel ⇒ Auszug redigiert
        assert nach_titel["Oeffentlich"]["auszug"]        # normaler Auszug bleibt erhalten
