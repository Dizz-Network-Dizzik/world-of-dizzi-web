"""MCP-Server von Dizz Communication (read-only, stdio).

Start: <venv-python> mcp_server.py   (im kommunikation-Ordner)
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).

HOECHST-App (Vertrag §3): der MCP-Host (Dizzis KI, ggf. Cloud-Boost) bekommt
AUSSCHLIESSLICH Metadaten/Kopfzeilen/Zähler — **NIEMALS Nachrichten-Volltexte**.
Darum zeigt KEIN Tool auf ``/api/posteingang`` (das trägt ``text``); die
Übersicht kommt aus ``/api/konversationen`` (Titel/Zähler) und den dedizierten
``/api/mcp/*``-Endpoints (Betreff/Absender/Datum, ohne Body). KI-Triage/Antwort
bleiben lokal in der App (Dossier §6).
"""

from __future__ import annotations

import os

import kommapp  # noqa: F401  (Pfad-Shim: macht appkit importierbar)
from kommapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS
from appkit.mcp import build_http_mcp

BASE = os.environ.get("DIZZ_KOMMUNIKATION_URL", "http://127.0.0.1:8218")

mcp = build_http_mcp("kommunikation", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)


# --- EINZIGES Aktions-Tool (K4, Human-in-the-Loop) ---------------------------
# Über die read-only-Metadaten hinaus: Dizzis KI darf einen Versand VORSCHLAGEN,
# aber NIE auslösen. Das Tool ruft nur POST /api/actions/propose (legt einen
# pending-Vorschlag an); die Freigabe (approve) verlangt Stufe ``verifiziert``
# und ist standalone fail-closed (403). Der MCP-Prozess führt also nichts aus —
# er reicht eine Bitte ein, über die der Mensch in der App entscheidet.
def mail_senden_vorschlagen(konto_id: str, an: str,
                            betreff: str = "", text: str = "") -> object:
    """Schlägt einen E-Mail-Versand als HITL-Aktion vor (führt NICHTS aus).

    Liefert die Vorschlags-id (Status ``pending``). Der Versand passiert erst,
    wenn der Nutzer den Vorschlag in Dizz Communication freigibt (Stufe
    verifiziert; ohne Anmeldung bleibt er fail-closed liegen)."""
    import httpx
    try:
        r = httpx.post(f"{BASE}/api/actions/propose", timeout=8.0, json={
            "name": "mail_senden", "source": "mcp",
            "params": {"konto_id": konto_id, "an": an,
                       "betreff": betreff, "text": text}})
        r.raise_for_status()
        out = r.json()
        out["hinweis"] = ("Nur VORGESCHLAGEN (pending). Freigabe ausschließlich "
                          "durch den Nutzer in der App — der MCP führt nie aus.")
        return out
    except Exception as e:
        return {"error": f"App 'kommunikation' nicht erreichbar (propose): {e}"}


mcp.tool(mail_senden_vorschlagen)

if __name__ == "__main__":
    mcp.run()  # stdio
