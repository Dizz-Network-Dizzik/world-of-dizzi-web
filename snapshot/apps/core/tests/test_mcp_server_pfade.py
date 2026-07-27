"""W2.0-Regression (docs/54 §6): die Core-MCP-Server-Pfade müssen im Monorepo existieren.

Vor dem Fix (27.06.2026) zeigte ``tools.MCP_SERVERS`` auf das Vor-Monorepo-Geschwister-
Layout ⇒ ``_mcp_toolspecs`` übersprang JEDEN Server (``if not path.is_file(): continue``)
⇒ Dizzis Agent UND das Inbound-MCP-Gateway hatten 0 App-Tools (nur die internen). Diese
Tests (ohne Subprozess/Ollama) fangen eine erneute Pfad-Drift sofort.

W2.0-RESTLOCH (27.06.2026, Funktions-Forscher-Brille): die Pfade stimmten danach, ABER
der stdio-Subprozess startet mit gestripptem ``PYTHONPATH`` (MCP-SDK-Default) ⇒ Connector-
Apps mit Vor-Monorepo-Shim (alle außer news/tradingbot) fanden ``appkit`` nicht und crashten
beim Start ⇒ ihre Tools fehlten erneut lautlos. Fix = ``tools._connector_env`` reicht
``PYTHONPATH=packages`` an den Subprozess weiter. Die folgenden Tests sichern das ab.
"""

import asyncio
import os

from app.ai import mcp_gateway, tools


def test_mcp_server_pfade_existieren():
    """Jeder gelistete stdio-MCP-Server muss eine echte Datei sein."""
    fehlend = [sid for sid, p in tools.MCP_SERVERS if not p.is_file()]
    assert not fehlend, f"MCP_SERVERS-Pfade fehlen (Monorepo-Drift?): {fehlend}"


def test_mcp_server_ids_haben_sensitivitaet():
    """Die server_id ist zugleich Tool-Namensraum UND Sensitivitäts-Schlüssel im
    Gateway (``mcp_gateway._APP_SENS``) — jede gelistete id braucht dort einen Eintrag,
    sonst fiele das Tool auf den vorsichtigen Default zurück statt auf seine echte Stufe."""
    ids = {sid for sid, _ in tools.MCP_SERVERS}
    fehlend = ids - set(mcp_gateway._APP_SENS)
    assert not fehlend, f"server_id ohne _APP_SENS-Eintrag: {fehlend}"


def test_connector_env_traegt_packages_pythonpath():
    """Der Subprozess-Env-Builder MUSS ``packages`` auf ``PYTHONPATH`` legen, sonst
    findet ein Connector mit Vor-Monorepo-Shim ``appkit`` nicht (W2.0-Restloch)."""
    env = tools._connector_env()
    pfade = env.get("PYTHONPATH", "").split(os.pathsep)
    assert str(tools._PACKAGES) in pfade, f"PYTHONPATH ohne packages: {env.get('PYTHONPATH')!r}"
    assert (tools._PACKAGES / "appkit" / "__init__.py").is_file(), "packages/appkit fehlt"


def test_stale_shim_connector_laedt_tools_live():
    """Echter Spawn-Beweis: ein Connector mit Vor-Monorepo-Shim (finanzen/money) muss
    über ``_client_for`` starten und seine Tools listen. Ohne den ``_connector_env``-Fix
    crasht der Subprozess am ``import appkit`` und liefert 0 Tools. list_tools braucht
    KEIN laufendes Backend (build_http_mcp registriert die Tools lokal) ⇒ hermetisch."""
    pfad = dict(tools.MCP_SERVERS)["finanzen"]

    async def _run():
        try:
            client = await tools._client_for("finanzen", pfad)
            namen = [t.name for t in await client.list_tools()]
        finally:
            await tools._drop_client("finanzen")
        return namen

    namen = asyncio.run(_run())
    assert any(n.startswith("finanzen_") for n in namen), f"finanzen-Connector lud 0 Tools: {namen}"


# ── _extract_result: Array-Tools dürfen NICHT als null verschwinden ───────────
# FALLE (27.06.2026, Funktions-Forscher): FastMCP setzt ``res.data`` nur für JSON-
# OBJEKTE (structuredContent ist objekt-only). Tools mit top-level Array (z. B.
# news_quellen/memory_ordner/kommunikation_konten) haben data=structured=None — die
# Liste steckt nur im Text-content. ``getattr(res,"data",None)`` ließ sie lautlos zu
# "null" werden (Agent + Gateway). _extract_result parst den content-Fallback.
class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeRes:
    def __init__(self, data=None, structured_content=None, content=None):
        self.data = data
        self.structured_content = structured_content
        self.content = content or []


def test_extract_result_array_aus_content():
    """Array-Tool: data/structured None ⇒ Liste MUSS aus dem Text-content kommen."""
    res = _FakeRes(content=[_FakeBlock('[{"id": "x"}, {"id": "y"}]')])
    assert tools._extract_result(res) == [{"id": "x"}, {"id": "y"}]


def test_extract_result_dict_bevorzugt_data():
    """Dict-Tool: das strukturierte ``data`` hat Vorrang vor dem Text."""
    res = _FakeRes(data={"ok": True}, structured_content={"ok": True},
                   content=[_FakeBlock('{"ok": true}')])
    assert tools._extract_result(res) == {"ok": True}


def test_extract_result_prosa_bleibt_text():
    """Nicht-JSON-Prosa im content bleibt als String erhalten (kein Datenverlust)."""
    assert tools._extract_result(_FakeRes(content=[_FakeBlock("nur prosa")])) == "nur prosa"


def test_extract_result_leer_ist_none():
    """Kein data/structured/content ⇒ None (kein Crash)."""
    assert tools._extract_result(_FakeRes()) is None
