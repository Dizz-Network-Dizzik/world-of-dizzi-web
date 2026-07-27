"""Tests Remote-MCP-Gateway (docs/30 §H1) — der ausgehende MCP-Server am Core,
über den eine externe KI (Claude) das ganze Netzwerk mit EINER Verbindung erreicht.
Tools werden gestubbt (kein fastmcp/Subprozess nötig); geprüft wird das Protokoll +
die opt-in/Token-Sicherheit. ``temp_db`` (conftest) isoliert jeden Lauf.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.ai import tools as ai_tools

client = TestClient(app)


async def _stub_registry(sensitive: bool = True):
    async def run(args):
        return "echo:" + str(args.get("x", ""))
    return [ai_tools.ToolSpec(
        "demo_tool", "Demo-Werkzeug",
        {"type": "object", "properties": {"x": {"type": "string"}}}, run)]


def _rpc(method, params=None, rid=1, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": rid,
                                     "method": method, "params": params or {}}, headers=h)


def test_gateway_off_by_default():
    assert _rpc("initialize").status_code == 403          # frische temp-db ⇒ deaktiviert


def test_gateway_enable_flow(monkeypatch):
    monkeypatch.setattr(ai_tools, "registry", _stub_registry)
    en = client.post("/mcp/enable").json()
    assert en["enabled"] is True and en["token"].startswith("dzmcp_")
    tok = en["token"]
    # Token-Pflicht
    assert _rpc("initialize").status_code == 401
    assert _rpc("initialize", token="falsch").status_code == 401
    # initialize ⇒ Version + ServerInfo + tools-capability
    init = _rpc("initialize", {"protocolVersion": "2025-06-18"}, token=tok).json()
    assert init["result"]["serverInfo"]["name"].startswith("Dizz Network")
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in init["result"]["capabilities"]
    # tools/list ⇒ das gestubbte App-Tool
    tl = _rpc("tools/list", token=tok).json()
    werkzeuge = {t["name"]: t for t in tl["result"]["tools"]}
    assert "demo_tool" in werkzeuge and "inputSchema" in werkzeuge["demo_tool"]
    # tools/call ⇒ läuft + MCP-content
    tc = _rpc("tools/call", {"name": "demo_tool", "arguments": {"x": "hi"}}, token=tok).json()
    assert tc["result"]["isError"] is False
    assert tc["result"]["content"][0]["text"] == "echo:hi"
    # unbekanntes Tool ⇒ JSON-RPC-Fehler
    assert "error" in _rpc("tools/call", {"name": "gibtsnicht"}, token=tok).json()
    # Notification (keine id) ⇒ 202 ohne Body
    n = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={"Authorization": "Bearer " + tok})
    assert n.status_code == 202
    # ping
    assert _rpc("ping", token=tok).json()["result"] == {}
    # info liefert die fertige Claude-Konfiguration
    info = client.get("/mcp/info").json()
    assert info["enabled"] is True
    cfg = info["claude_config"]["mcpServers"]["dizz-network"]
    assert cfg["url"].endswith("/mcp") and cfg["headers"]["Authorization"] == "Bearer " + tok


async def _stub_strukturiert_registry(sensitive: bool = True):
    async def obj(args):
        return '{"saldo": 1234, "waehrung": "EUR"}'   # JSON-Objekt ⇒ structuredContent
    async def liste(args):
        return '[1, 2, 3]'                            # JSON-Array ⇒ NUR Text (Spec: Objekt)
    async def prosa(args):
        return 'einfach Text'                         # kein JSON ⇒ NUR Text
    return [
        ai_tools.ToolSpec("finanzen_saldo", "Saldo (read)", {}, obj),
        ai_tools.ToolSpec("news_schlagzeilen", "Liste (read)", {}, liste),
        ai_tools.ToolSpec("news_zusammenfassung", "Text (read)", {}, prosa),
    ]


def test_mcp_2025_06_18_annotations_und_structured_content(monkeypatch):
    """MCP 2025-06-18: tools/list trägt readOnly-Annotationen (das Gateway listet nur
    read-only-Tools ⇒ exakt), tools/call liefert structuredContent NUR für JSON-Objekte
    (+ immer den äquivalenten content-Text, abwärtskompatibel)."""
    monkeypatch.setattr(ai_tools, "registry", _stub_strukturiert_registry)
    tok = client.post("/mcp/enable").json()["token"]
    # initialize echot die stabile Spec-Version 2025-06-18
    init = _rpc("initialize", {"protocolVersion": "2025-06-18"}, token=tok).json()
    assert init["result"]["protocolVersion"] == "2025-06-18"
    # tools/list ⇒ readOnlyHint=True + openWorldHint=False (lokal), destructiveHint=False
    werk = {t["name"]: t for t in _rpc("tools/list", token=tok).json()["result"]["tools"]}
    ann = werk["finanzen_saldo"]["annotations"]
    assert ann["readOnlyHint"] is True and ann["openWorldHint"] is False
    assert ann["destructiveHint"] is False
    # tools/call (Objekt) ⇒ structuredContent == geparste Daten + content-Text bleibt
    tc = _rpc("tools/call", {"name": "finanzen_saldo"}, token=tok).json()["result"]
    assert tc["structuredContent"] == {"saldo": 1234, "waehrung": "EUR"}
    assert tc["content"][0]["text"] == '{"saldo": 1234, "waehrung": "EUR"}'
    assert tc["isError"] is False
    # Array ⇒ KEIN structuredContent (Spec: Objekt), nur Text
    arr = _rpc("tools/call", {"name": "news_schlagzeilen"}, token=tok).json()["result"]
    assert "structuredContent" not in arr and arr["content"][0]["text"] == "[1, 2, 3]"
    # Prosa ⇒ KEIN structuredContent
    pr = _rpc("tools/call", {"name": "news_zusammenfassung"}, token=tok).json()["result"]
    assert "structuredContent" not in pr


async def _stub_sens_registry(sensitive: bool = True):
    async def run(args):
        return "ok"
    return [
        ai_tools.ToolSpec("admin_projekt_status", "hoch", {}, run),        # hoch ⇒ erlaubt
        ai_tools.ToolSpec("admin_dokument_datei", "Dateiinhalt", {}, run),  # *_datei* ⇒ hochsicher
        ai_tools.ToolSpec("health_metrik", "Gesundheit", {}, run),         # health = hoechst
    ]


def test_hochsicher_gate(monkeypatch):
    monkeypatch.setattr(ai_tools, "registry", _stub_sens_registry)
    tok = client.post("/mcp/enable").json()["token"]
    # Standard: NUR das hoch-Tool sichtbar; hochsicher (Datei) + hoechst (health) gesperrt
    namen = [t["name"] for t in _rpc("tools/list", token=tok).json()["result"]["tools"]]
    assert "admin_projekt_status" in namen
    assert "admin_dokument_datei" not in namen and "health_metrik" not in namen
    # Direkter Call aufs gesperrte Tool ⇒ isError + Freigabe-Hinweis (keine Daten)
    gesperrt = _rpc("tools/call", {"name": "admin_dokument_datei"}, token=tok).json()
    assert gesperrt["result"]["isError"] is True
    assert "Freigabe" in gesperrt["result"]["content"][0]["text"]
    # Explizite Freigabe (befristet) ⇒ jetzt sichtbar + aufrufbar
    assert client.post("/mcp/freigabe-hochsicher", params={"minuten": 5}).json()["hochsicher_freigegeben"] is True
    namen2 = [t["name"] for t in _rpc("tools/list", token=tok).json()["result"]["tools"]]
    assert "admin_dokument_datei" in namen2 and "health_metrik" in namen2
    assert _rpc("tools/call", {"name": "admin_dokument_datei"}, token=tok).json()["result"]["isError"] is False
    # Sperren ⇒ wieder gesperrt, info spiegelt es
    client.post("/mcp/freigabe-sperren")
    assert "admin_dokument_datei" not in [t["name"] for t in _rpc("tools/list", token=tok).json()["result"]["tools"]]
    assert client.get("/mcp/info").json()["sicherheit"]["hochsicher_freigegeben"] is False


def test_gateway_disable_und_rotate(monkeypatch):
    monkeypatch.setattr(ai_tools, "registry", _stub_registry)
    t1 = client.post("/mcp/enable").json()["token"]
    assert _rpc("initialize", token=t1).status_code == 200
    assert client.post("/mcp/disable").json()["enabled"] is False
    assert _rpc("initialize", token=t1).status_code == 403      # aus ⇒ 403
    # wieder an + Token rotieren ⇒ alter Token gilt nicht mehr
    client.post("/mcp/enable")
    t2 = client.post("/mcp/rotate-token").json()["token"]
    assert t2 != t1
    assert _rpc("initialize", token=t1).status_code == 401
    assert _rpc("initialize", token=t2).status_code == 200


async def _stub_aktion_registry(sensitive: bool = True):
    async def run(args):
        return "ok"
    return [
        ai_tools.ToolSpec("kommunikation_letzte_nachrichten", "Metadaten (read)", {}, run),
        ai_tools.ToolSpec("kommunikation_mail_senden_vorschlagen", "Sende-VORSCHLAG (Aktion)", {}, run),
    ]


def test_aktions_tools_extern_gesperrt(monkeypatch):
    """read-only-v1: Schreib-/Aktions-Tools (z. B. *_vorschlagen) erscheinen NICHT im
    ausgehenden Gateway und ein direkter Call wird verweigert — sie laufen über die
    App-eigene HITL-Freigabe. Dizzis INTERNER Agent behält sie (separater Pfad)."""
    monkeypatch.setattr(ai_tools, "registry", _stub_aktion_registry)
    tok = client.post("/mcp/enable").json()["token"]
    namen = [t["name"] for t in _rpc("tools/list", token=tok).json()["result"]["tools"]]
    assert "kommunikation_letzte_nachrichten" in namen          # read bleibt
    assert "kommunikation_mail_senden_vorschlagen" not in namen  # Aktion raus
    blk = _rpc("tools/call", {"name": "kommunikation_mail_senden_vorschlagen"}, token=tok).json()
    assert blk["result"]["isError"] is True
    assert "read-only" in blk["result"]["content"][0]["text"].lower()


async def _stub_explizit_registry(sensitive: bool = True):
    async def run(args):
        return "ok"
    return [
        # harmlos BENANNT (news = normal), aber explizit als Aktion markiert ⇒ MUSS raus
        ai_tools.ToolSpec("news_schlagzeilen_a", "liest", {}, run, is_action=True),
        # harmlos BENANNT, aber explizit hochsicher ⇒ MUSS ohne Freigabe gesperrt sein
        ai_tools.ToolSpec("news_zusammenfassung", "fasst", {}, run, sensitivity="hochsicher"),
        # Kontrolle: ohne Attribut + harmloser Name ⇒ erlaubt + sichtbar
        ai_tools.ToolSpec("news_schlagzeilen", "liest", {}, run),
    ]


def test_explizites_attribut_haertet_zusaetzlich(monkeypatch):
    """docs/33 R6: explizites ``is_action``/``sensitivity`` am ToolSpec sperrt auch Tools,
    deren NAME kein Muster trifft (fail-safe: das Attribut kann nur ZUSÄTZLICH sperren).
    Beweis: zwei harmlos benannte news-Tools (normal) werden via Attribut gesperrt, das
    attributlose Kontroll-Tool bleibt sichtbar — Namensinferenz allein würde alle drei zeigen."""
    monkeypatch.setattr(ai_tools, "registry", _stub_explizit_registry)
    tok = client.post("/mcp/enable").json()["token"]
    namen = [t["name"] for t in _rpc("tools/list", token=tok).json()["result"]["tools"]]
    assert "news_schlagzeilen" in namen                 # Kontrolle (attributlos) erlaubt
    assert "news_schlagzeilen_a" not in namen           # explizit is_action ⇒ raus
    assert "news_zusammenfassung" not in namen          # explizit hochsicher ⇒ raus
    a = _rpc("tools/call", {"name": "news_schlagzeilen_a"}, token=tok).json()
    assert a["result"]["isError"] is True and "read-only" in a["result"]["content"][0]["text"].lower()
    h = _rpc("tools/call", {"name": "news_zusammenfassung"}, token=tok).json()
    assert h["result"]["isError"] is True and "Freigabe" in h["result"]["content"][0]["text"]
