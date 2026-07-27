"""CLI-Werkzeug: Re-Index des RAG-Vektorindex (alle Notizen neu einbetten).

Nutzt das KONFIGURIERTE Embedding-Modell (Env ``DIZZ_MEMORY_EMBED_MODELL`` /
Setting ``embed_modell`` / Default ``bge-m3``) — derselbe Auflösungs-Pfad wie
der laufende Server, also ideal nach einem Modellwechsel.

Aufruf (venv-Python; braucht ein erreichbares Ollama mit dem Modell):
    <venv-python> -m archivapp.reindex [--user dizzi] [--modell qwen3-embedding]

Der Lauf ist idempotent + abbruch-sicher (Strg+C lässt das bereits Indexierte
gültig; erneuter Aufruf vervollständigt). Verkraftet große Vaults (Notiz-für-
Notiz, streamend)."""

from __future__ import annotations

import sys

from appkit.auth import DEFAULT_USER_ID

from .main import build_app


def _arg(argv: list[str], name: str, default: str | None = None) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    user = _arg(argv, "--user", DEFAULT_USER_ID) or DEFAULT_USER_ID
    modell = _arg(argv, "--modell")              # optional: überschreibt Env/Setting

    # Echtes Ollama-Embed, KEINE Hintergrund-Daemons (reines Werkzeug).
    app = build_app(use_ollama=True, embed_modell=modell,
                    rag_autobuild=False, start_import_timer=False)
    rag = app.state.rag
    db = app.state.db
    if not rag.probe():
        print(f"Embedder nicht verfügbar (Ollama erreichbar? Modell '{rag.modell}' geladen?). "
              "Re-Index würde 0 Chunks erzeugen — Abbruch.")
        return 2

    rows = db.get_conn().execute(
        "SELECT id, user_id, titel, inhalt, created_at FROM notizen "
        "WHERE user_id=? AND deleted_at IS NULL", (user,)).fetchall()
    notizen = [dict(r) for r in rows]
    print(f"Re-Index · Modell {rag.modell} (dim {rag.dim}) · {len(notizen)} Notizen …")

    def _prog(fertig: int, gesamt: int, chunks: int) -> None:
        print(f"\r  {fertig}/{gesamt} Notizen · {chunks} Chunks", end="", flush=True)

    try:
        res = rag.reindex(notizen, on_progress=_prog)
    except KeyboardInterrupt:
        print("\nAbgebrochen (bereits indexierte Notizen bleiben gültig).")
        return 130
    print(f"\nFertig: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
