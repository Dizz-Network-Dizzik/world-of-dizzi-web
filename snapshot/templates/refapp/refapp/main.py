"""Referenz-App — beweist den App-Vertrag end-to-end (Vorbild für jede App).

Start (Entwicklung):
    <venv-python> -m uvicorn refapp.main:app_factory --factory
        --host 127.0.0.1 --port 8290 --app-dir templates/refapp

Die „Domäne" ist bewusst winzig (Notizen zählen): sie zeigt die drei Stellen,
an denen eine echte App ihren Inhalt einsetzt — Domänen-Schema, Domänen-Router,
``summary_fn``. Alles Vertragliche kommt aus appkit.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__

from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit.auth import UserContext, current_user
from appkit.db import Database, default_db_path, new_id, now_iso
from appkit.dizzi_id import install_dizzi_id
from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.mcp import namespaced
from appkit.summary import Kpi

APP_ID = "refapp"

# MCP-Tools KURZ deklarieren; namespaced() präfixt sie in den App-Namensraum
# (<id>_<tool>, docs/16 §6) — derselbe Präfix, den build_http_mcp im mcp_server
# automatisch setzt. So bleiben Manifest und tatsächliche Tool-Namen konsistent.
_MCP_TOOLS = ["kachel_stats", "lebenszeichen"]

MANIFEST = AppManifest(
    id=APP_ID, name="Referenz-App", brand="Dizz Ref", version=__version__,
    port=8290, icon="box", sensitivity="normal",
    mcp=McpInfo(command=["<venv-python>", "mcp_server.py"],
                tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    shares=Shares(summary=True, tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
)

# Domänen-Schema: folgt zwingend den Vertrags-Konventionen (UUID/user_id/
# Timestamps/Soft-Delete — appkit/db.py Docstring).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS notizen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_notizen ON notizen (user_id, created_at);
"""


class NotizIn(BaseModel):
    """Request-Modelle MÜSSEN auf Modul-Ebene stehen: mit ``from __future__
    import annotations`` löst FastAPI String-Annotationen über die Modul-Globals
    auf — ein lokal definiertes Modell würde still zum Query-Parameter."""

    text: str


def build_app(data_dir: Path | None = None):
    """Baut die vertragskonforme App. ``data_dir``-Injektion für Tests;
    Produktion: ``DIZZ_REFAPP_DATA_DIR`` bzw. Standard ``C:\\Dizzik\\data``."""
    root = data_dir or Path(os.environ.get("DIZZ_REFAPP_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root), extra_schema=_SCHEMA)

    router = APIRouter()

    @router.post("/api/notizen")
    def notiz_anlegen(body: NotizIn,
                      user: UserContext = Depends(current_user)) -> dict:
        ts = now_iso()
        db.get_conn().execute(
            "INSERT INTO notizen (id, user_id, text, created_at, updated_at) VALUES (?,?,?,?,?)",
            (new_id(), user.user_id, body.text, ts, ts))
        db.get_conn().commit()
        db.audit(user.user_id, "user", "notiz_angelegt", {"len": len(body.text)})
        return {"ok": True}

    def summary() -> list[Kpi]:
        row = db.get_conn().execute(
            "SELECT COUNT(*) AS n, MAX(created_at) AS letzte FROM notizen "
            "WHERE deleted_at IS NULL").fetchone()
        return [Kpi(id="notizen", label="Notizen", value=row["n"], unit="Stk"),
                Kpi(id="letzte", label="Zuletzt", value=row["letzte"] or "—")]

    app = create_app(MANIFEST, db, summary_fn=summary, routers=[router],
                     version=__version__)
    # Dizzi-ID-Anschluss (K1): /auth/login|callback|logout|me + Identitäts-
    # Provider. Ohne laufenden IdP bleibt die App standalone auf Stufe 'lokal'.
    install_dizzi_id(app, MANIFEST, data_root=root)

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet die App ihr EIGENES
    # read-only MCP-Gate (/mcp) an; im Verbund (Modus 'auto') schaltet es ab, sobald der
    # Core sein zentrales Gateway führt. Gleiche Tool-Quelle wie der stdio-MCP (mcp_tools).
    # opt-in/Token/Hochsicher-Gate. Muster für jede neue App.
    from . import mcp_tools  # noqa: E402  (Tool-Quelle, lokal importiert)
    from appkit.app_gateway import build_app_gateway  # noqa: E402
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))

    # Standard-Frontend (H-5): generisches Skelett + kanonisches ui-kit same-origin.
    # /ui-kit liefert mit no-cache (H-1, ETag-Revalidierung ⇒ kein ?v=-Bump). Eine neue
    # App ersetzt static/index.html durch ihre Domäne (Kit + Verhalten bleiben).
    base = Path(__file__).resolve().parents[1]

    @app.get("/", include_in_schema=False)
    def _index():
        return FileResponse(base / "static" / "index.html", media_type="text/html")

    ui_kit_dir = base / "ui-kit"
    if ui_kit_dir.is_dir():
        class _UiKitFiles(StaticFiles):  # H-1: Cache-Control no-cache -> Revalidierung via ETag
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit_dir)), name="ui-kit")
    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): Import der Datei hat keine Seiteneffekte."""
    return build_app()
