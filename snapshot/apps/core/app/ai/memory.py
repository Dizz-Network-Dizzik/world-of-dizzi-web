"""Gedächtnis-Ebene L1 (Profil-Fakten) + Chat-Verlauf.

Mem0-Pattern light (docs/02): Fakten werden explizit („merk dir …") oder
automatisch (kleines Lokal-Modell extrahiert nach jedem Austausch) gespeichert
und in den System-Prompt jeder Anfrage injiziert. **L2** (Episoden-Verdichtung,
``maybe_summarize_episode``) und **L4** (Nacht-Konsolidierung ``consolidate`` via
``_consolidation_loop``, main.py) sind LIVE; L3 = der RAG-Vektor-Index (Dizz Memory).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import RootModel

from .. import db
from . import providers

# Antwort-Schema (docs/50 P2.1): EINE Quelle für format= (constrained decoding)
# UND Validierung. RootModel[list[str]] ⇒ flaches Array-Schema (kein $ref) ⇒
# auf dem nativen Ollama-format-Slot grammatik-sicher.
_Fakten = RootModel[list[str]]

MAX_FACTS_IN_PROMPT = 40
MAX_EPISODES_IN_PROMPT = 3
EPISODE_AFTER_MSGS = 16   # ab so vielen aktiven Nachrichten wird verdichtet …
EPISODE_KEEP_RECENT = 6   # … die jüngsten bleiben wörtlich erhalten
_EXPLICIT_RE = re.compile(r"\bmerk(?:e)?\s+dir\b[:,]?\s*", re.IGNORECASE)

PERSONA = (
    "Du bist Dizzi, die persönliche KI-Kommandozentrale von dizzi. "
    "Du hilfst beim Verwalten von Projekten, Alltag, Finanzen und Bürokratie. "
    "Antworte auf Deutsch, ehrlich, kompakt und konkret. "
    "Wenn du etwas nicht weißt, sag es."
)


# --- Fakten (L1) ------------------------------------------------------------

def facts(user_id: str) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT id, fact, source, created_at FROM memory_facts "
        "WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_fact(user_id: str, fact: str, source: str) -> bool:
    """Speichert einen Fakt; near-Duplikate (case-insensitive) werden ignoriert."""
    fact = fact.strip().rstrip(".")
    if len(fact) < 4:
        return False
    conn = db.get_conn()
    dup = conn.execute(
        "SELECT 1 FROM memory_facts WHERE user_id=? AND deleted_at IS NULL "
        "AND lower(fact)=lower(?)",
        (user_id, fact),
    ).fetchone()
    if dup:
        return False
    ts = db.now_iso()
    conn.execute(
        "INSERT INTO memory_facts (id, user_id, fact, source, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (db.new_id(), user_id, fact, source, ts, ts),
    )
    conn.commit()
    db.audit(user_id, "ki", "memory_fact_added", {"fact": fact, "source": source})
    return True


def delete_fact(user_id: str, fact_id: str) -> bool:
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE memory_facts SET deleted_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL",
        (db.now_iso(), fact_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def explicit_fact_from(message: str) -> str | None:
    """„merk dir: X" ⇒ X — nur bis zum Satzende, nicht der ganze Nachrichtenrest."""
    m = _EXPLICIT_RE.search(message)
    if not m:
        return None
    rest = message[m.end():].strip()
    first = re.split(r"(?<=[.!?])\s+", rest, maxsplit=1)[0].strip()
    return first or None


async def auto_extract(user_id: str, user_msg: str, assistant_msg: str) -> int:
    """Lässt das schnelle Lokal-Modell 0–2 dauerhafte Fakten extrahieren."""
    if not db.setting_get(user_id, "ai_auto_memory", True):
        return 0
    prompt = (
        "Extrahiere aus diesem Austausch 0 bis 2 DAUERHAFTE Fakten über den Nutzer "
        "(Vorlieben, Lebensumstände, laufende Projekte). KEINE einmaligen Aufgaben, "
        "keine Fragen, nichts Triviales. Formuliere jeden Fakt auf DEUTSCH. "
        "Antworte NUR als JSON-Liste von Strings, "
        'z. B. ["dizzi mag X"] oder [].\n\n'
        f"Nutzer: {user_msg}\nAssistent: {assistant_msg}"
    )
    try:
        raw = await providers.quick_chat(
            [{"role": "user", "content": prompt}], format=_Fakten.model_json_schema())
        # Defensiv: falls das Modell doch Prosa drumherum setzt, auf das Array kürzen.
        raw = raw[raw.find("[") : raw.rfind("]") + 1]
        items = _Fakten.model_validate_json(raw).root
        added = 0
        for it in items[:2]:
            if isinstance(it, str) and add_fact(user_id, it, "auto"):
                added += 1
        return added
    except Exception:
        return 0  # Auto-Memory ist Komfort, nie ein Fehlergrund


# --- Episoden (L2): Lebenszyklus roh → verdichtet → Essenz -------------------

def episodes(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT id, summary, kind, started_at, ended_at FROM episodes "
        "WHERE user_id=? AND deleted_at IS NULL ORDER BY ended_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _add_episode(user_id: str, summary: str, kind: str, started: str, ended: str) -> None:
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO episodes (id, user_id, summary, kind, started_at, ended_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), user_id, summary.strip(), kind, started, ended, db.now_iso()),
    )
    conn.commit()


async def maybe_summarize_episode(user_id: str) -> bool:
    """Verdichtet alte Verlaufs-Nachrichten zu einer Episode (progressive
    summarization, docs/recherche Welle 5): jüngste bleiben wörtlich, der
    ältere Block wird zusammengefasst und im Verlauf soft-deleted."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM chat_messages "
        "WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at",
        (user_id,),
    ).fetchall()
    if len(rows) < EPISODE_AFTER_MSGS:
        return False
    old = rows[:-EPISODE_KEEP_RECENT]
    transcript = "\n".join(f"{r['role']}: {r['content']}" for r in old)
    prompt = (
        "Fasse dieses Gespräch in 2–3 deutschen Sätzen zusammen: Themen, "
        "Entscheidungen, offene Punkte. Keine Floskeln, nur Substanz.\n\n" + transcript
    )
    try:
        summary = await providers.quick_chat([{"role": "user", "content": prompt}])
    except Exception:
        return False  # Verdichtung ist Komfort — nie Nachrichten ohne Episode löschen
    _add_episode(user_id, summary, "episode", old[0]["created_at"], old[-1]["created_at"])
    ts = db.now_iso()
    conn.executemany(
        "UPDATE chat_messages SET deleted_at=? WHERE id=?",
        [(ts, r["id"]) for r in old],
    )
    conn.commit()
    db.audit(user_id, "ki", "episode_created", {"messages": len(old)})
    return True


async def consolidate(user_id: str) -> dict[str, int]:
    """Nacht-Konsolidierung: viele alte Episoden → eine Essenz (Lebenszyklus-
    Prinzip). Läuft täglich, gesteuert über Setting ``last_consolidation``."""
    eps = [e for e in episodes(user_id, limit=100) if e["kind"] == "episode"]
    merged = 0
    if len(eps) > 12:
        oldest = sorted(eps, key=lambda e: e["ended_at"])[:8]
        text = "\n".join(f"- {e['summary']}" for e in oldest)
        prompt = (
            "Verdichte diese Gesprächs-Zusammenfassungen zu EINEM deutschen Absatz "
            "(max. 4 Sätze) mit dem dauerhaft Wichtigen:\n\n" + text
        )
        try:
            essence = await providers.quick_chat([{"role": "user", "content": prompt}])
            _add_episode(user_id, essence, "essenz", oldest[0]["started_at"], oldest[-1]["ended_at"])
            conn = db.get_conn()
            ts = db.now_iso()
            conn.executemany(
                "UPDATE episodes SET deleted_at=? WHERE id=?",
                [(ts, e["id"]) for e in oldest],
            )
            conn.commit()
            merged = len(oldest)
        except Exception:
            pass
    db.setting_put(user_id, "last_consolidation", db.now_iso())
    db.audit(user_id, "ki", "consolidation_run", {"episodes_merged": merged})
    return {"episodes_merged": merged}


# --- Verlauf ----------------------------------------------------------------

def save_message(user_id: str, role: str, content: str, provider: str | None = None) -> None:
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, provider, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (db.new_id(), user_id, role, content, provider, db.now_iso()),
    )
    conn.commit()


def history(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT role, content, provider, created_at FROM chat_messages "
        "WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def build_messages(
    user_id: str, user_msg: str, context_turns: int = 12,
    rag_chunks: list[dict[str, Any]] | None = None,
) -> list[dict]:
    """System-Prompt (Persona + Fakten + Episoden + Wissen) + Verlauf + Nachricht."""
    fs = facts(user_id)[-MAX_FACTS_IN_PROMPT:]
    sys = PERSONA
    if fs:
        sys += "\n\nWas du über den Nutzer weißt:\n" + "\n".join(f"- {f['fact']}" for f in fs)
    eps = episodes(user_id, limit=MAX_EPISODES_IN_PROMPT)
    if eps:
        sys += "\n\nFrühere Gespräche (verdichtet, neueste zuerst):\n" + "\n".join(
            f"- {e['summary']}" for e in eps
        )
    if rag_chunks:
        sys += (
            "\n\nWissen aus den Dokumenten des Nutzers (nenne die Quelle in Klammern, "
            "wenn du daraus antwortest):\n"
            + "\n".join(f"[{c['source']}]\n{c['text']}" for c in rag_chunks)
        )
    msgs: list[dict] = [{"role": "system", "content": sys}]
    msgs += [
        {"role": h["role"], "content": h["content"]}
        for h in history(user_id, limit=context_turns)
    ]
    msgs.append({"role": "user", "content": user_msg})
    return msgs
