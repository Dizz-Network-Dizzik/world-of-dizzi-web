"""KA-M8: proaktiver Analyst NETZWEIT (app-agnostisch) — Delta-Stufe (deterministisch)
+ Tages-LLM-Stufe (constrained, IMMER lokal). Ohne Ollama/Cloud: quick_chat gefaked,
local_model als struktureller Cloud-frei-Beweis."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from app import db
from app.ai import analyst
from app.config import DEFAULT_USER_ID


def _obs(source: str, daten: dict, minuten_alt: int) -> None:
    """Eine observation mit kontrolliertem Alter (für latest/prev-Ordnung)."""
    ca = (datetime.now(timezone.utc) - timedelta(minutes=minuten_alt)
          ).isoformat(timespec="seconds")
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO observations (id,user_id,source,data,created_at) VALUES (?,?,?,?,?)",
        (db.new_id(), DEFAULT_USER_ID, source,
         json.dumps(daten, ensure_ascii=False), ca))
    conn.commit()


def test_kpi_zahlen_parst_und_ueberspringt_maskiert():
    kpis = [{"label": "Saldo", "value": "1.234,56 €"}, {"label": "Quote", "value": "42%"},
            {"label": "Geheim", "value": "•••"}, {"label": "Text", "value": "n/a"},
            {"label": "Zahl", "value": 23}]
    z = analyst._kpi_zahlen(kpis)
    assert z["Saldo"] == 1234.56 and z["Quote"] == 42.0 and z["Zahl"] == 23.0
    assert "Geheim" not in z          # maskiert (•••) ⇒ Datenschutz by construction
    assert "Text" not in z            # unparsebar ⇒ übersprungen


def test_analyze_netz_meldet_status_kippen_und_kpi_sprung():
    _obs("news", {"status": "ok",
                  "kpis": [{"id": "n", "label": "Artikel", "value": 100}]}, 40)
    _obs("news", {"status": "warn",
                  "kpis": [{"id": "n", "label": "Artikel", "value": 200}]}, 10)
    n = analyst.analyze_netz(DEFAULT_USER_ID)
    assert n == 2                     # Status-Kippen (warn) + KPI-Sprung (100→200)
    titel = [x["title"] for x in analyst.notices(DEFAULT_USER_ID)]
    assert any("Status auf 'warn'" in t for t in titel)
    assert any("Artikel 100 → 200" in t for t in titel)


def test_analyze_netz_deckel_pro_app():
    def kpis(mult): return [{"id": f"k{i}", "label": f"L{i}", "value": 10 * mult}
                            for i in range(5)]
    _obs("management", {"status": "ok", "kpis": kpis(1)}, 40)
    _obs("management", {"status": "fehler", "kpis": kpis(3)}, 10)
    # Status-Kippen + 5 starke KPI-Sprünge ⇒ auf NETZ_MAX_PRO_APP gedeckelt.
    assert analyst.analyze_netz(DEFAULT_USER_ID) == analyst.NETZ_MAX_PRO_APP


def test_analyze_netz_still_bei_einem_snapshot():
    _obs("news", {"status": "warn", "kpis": []}, 10)   # nur EINE Beobachtung
    assert analyst.analyze_netz(DEFAULT_USER_ID) == 0


def test_suggest_netz_ist_cloud_frei_und_nur_kpi(monkeypatch):
    _obs("news", {"status": "ok", "kpis": [{"label": "Artikel", "value": 100}]}, 40)
    _obs("news", {"status": "ok", "kpis": [{"label": "Artikel", "value": 150}]}, 10)
    gesehen: dict = {}

    async def fake_quick_chat(messages, model=None, format=None):
        gesehen["model"] = model
        gesehen["prompt"] = messages[0]["content"]
        return '[{"app_id":"news","titel":"Mehr Feeds","begruendung":"Artikel steigen."}]'

    monkeypatch.setattr(analyst.providers, "quick_chat", fake_quick_chat)
    n = asyncio.run(analyst.suggest_netz(DEFAULT_USER_ID))
    # STRUKTURELLER Cloud-frei-Beweis: es wird NUR das lokale Modell benutzt.
    assert gesehen["model"] == analyst.providers.local_model()
    assert "•••" not in gesehen["prompt"]     # nie maskierte/Freitext-Daten im Prompt
    assert n == 1
    assert any(x["severity"] == "vorschlag" for x in analyst.notices(DEFAULT_USER_ID))
