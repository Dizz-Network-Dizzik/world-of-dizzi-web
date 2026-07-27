"""Ton-Preset + VIP-Liste je Bereich (RG-7, docs/83 §5.6/§5) — Governance am Bereich.

Der **Antwort-Entwurf**-Worker des E-Mail-Piloten bekommt in seinen Zünd-Kontext das
**Ton-Preset** des Bereichs (Sprache, Anrede, Signatur, VERBOTS-Liste) — so klingt ein
Entwurf nach dem Bereich statt generisch, und die Verbote (keine Preis-/Termin-/Rechts-
Zusagen, keine Anhänge versprechen) stehen strukturell im Prompt. Die **VIP-Liste**
markiert Absender, die eine sofortige Glocke + VIP-Kennzeichnung auslösen (§5 „Eskalation").
Beides ist Governance ⇒ Heimat Management (docs/83 §5.6), keyed je Bereich (VO-2-Kanon-id).

Rein + fail-closed: die Helfer WIRKEN nicht (kein Netz, kein Versand) — sie bauen nur Text
für den Zünd-Kontext bzw. ein Boolean für die Eskalations-Weiche. Die LIVE-Einspeisung in
den Core-Lauf ist Teil der gegateten Aktivierung (G-REGIE-LIVE); hier stehen Speicher, CRUD
und die reinen Helfer, die der Lauf dann liest.
"""

from __future__ import annotations

import json
from email.utils import parseaddr
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso

# --- Schema (Management-DB — Governance, Heimat D13) -------------------------

SCHEMA_BEREICH_PRESET = """
CREATE TABLE IF NOT EXISTS regie_bereich_preset (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    bereich_id  TEXT NOT NULL DEFAULT '',        -- VO-2-Kanon-id ('' = Allgemein)
    ton_preset  TEXT NOT NULL DEFAULT '{}',      -- JSON: sprache/anrede/signatur/verbote
    vip_liste   TEXT NOT NULL DEFAULT '[]',      -- JSON: Absender-Adressen (normalisiert)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,                            -- KA-H1 Lösch-Invariante (Soft-Delete-Kaskade)
    UNIQUE (user_id, bereich_id)
);
"""

#: Standard-Verbote des Antwort-Entwurfs (docs/83 §5.6) — strukturell, nicht per Bitte.
STANDARD_VERBOTE = ("keine Preis-Zusagen", "keine Termin-Zusagen",
                    "keine Rechts-Zusagen", "keine Anhänge versprechen")

#: Sicherer Default: deutsche Sprache, neutrale Anrede, Standard-Verbote, keine Signatur.
TON_DEFAULT: dict[str, Any] = {"sprache": "de", "anrede": "", "signatur": "",
                               "verbote": list(STANDARD_VERBOTE)}


# --- Reine Helfer (fail-closed, kein Seiteneffekt) --------------------------

def saniere_ton(roh: Any) -> dict[str, Any]:
    """Normalisiert ein Ton-Preset auf die bekannten, gedeckelten Felder (deny-by-default):
    ``sprache``/``anrede``/``signatur`` als getrimmte Strings, ``verbote`` als String-Liste.
    Fehlt etwas, greift der Default — nie ein roher, unkontrollierter Wert."""
    roh = roh if isinstance(roh, dict) else {}
    sprache = str(roh.get("sprache") or TON_DEFAULT["sprache"]).strip()[:40]
    anrede = str(roh.get("anrede") or "").strip()[:120]
    signatur = str(roh.get("signatur") or "").strip()[:500]
    roh_verbote = roh.get("verbote")
    if isinstance(roh_verbote, (list, tuple)):
        verbote = [str(v).strip()[:120] for v in roh_verbote if str(v).strip()][:20]
    else:
        verbote = list(STANDARD_VERBOTE)
    return {"sprache": sprache, "anrede": anrede, "signatur": signatur, "verbote": verbote}


def saniere_vip(roh: Any) -> list[str]:
    """VIP-Adressen normalisiert (Kleinschreibung, getrimmt, dedupe, gedeckelt).
    Aus „Name <a@b>" wird ``a@b`` (parseaddr); leere/ungültige fallen weg."""
    out: list[str] = []
    for eintrag in (roh or []):
        _name, adresse = parseaddr(str(eintrag))
        adresse = (adresse or str(eintrag)).strip().lower()
        if adresse and adresse not in out:
            out.append(adresse)
    return out[:200]


def ton_preset_text(preset: dict[str, Any]) -> str:
    """Baut die eine Zünd-Kontext-Zeile für den Antwort-Entwurf-Worker (docs/83 §5.6):
    Sprache · Anrede · Signatur · VERBOTS-Liste. Rein — der Lauf hängt sie an den
    Worker-Prompt; hier entsteht nur der Text."""
    p = saniere_ton(preset)
    teile = [f"Sprache: {p['sprache']}"]
    if p["anrede"]:
        teile.append(f"Anrede: {p['anrede']!r}")
    if p["signatur"]:
        teile.append(f"Signatur: {p['signatur']!r}")
    verbote = "; ".join(p["verbote"]) if p["verbote"] else "—"
    return ("Ton dieses Bereichs — " + ". ".join(teile)
            + f". VERBOTEN im Entwurf: {verbote}.")


def ist_vip(vip_liste: Any, absender: str) -> bool:
    """True ⇔ der Absender steht auf der VIP-Liste (Adress-Vergleich, case-insensitive) —
    die Eskalations-Weiche des Piloten (§5: VIP ⇒ sofort Glocke + Kennzeichnung)."""
    _name, adresse = parseaddr(absender or "")
    adresse = (adresse or absender or "").strip().lower()
    return bool(adresse) and adresse in saniere_vip(vip_liste)


# --- Speicher (Management-DB, Hausmuster) -----------------------------------

def preset_lesen(db: Database, user_id: str, bereich_id: str = "") -> dict[str, Any]:
    """Gespeichertes Preset des Bereichs oder der sichere Default (nie leer/fehlend)."""
    row = db.get_conn().execute(
        "SELECT ton_preset, vip_liste FROM regie_bereich_preset "
        "WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL",
        (user_id, bereich_id)).fetchone()
    if row is None:
        return {"bereich_id": bereich_id, "ton_preset": dict(TON_DEFAULT),
                "vip_liste": [], "gesetzt": False}
    return {"bereich_id": bereich_id,
            "ton_preset": saniere_ton(json.loads(row["ton_preset"] or "{}")),
            "vip_liste": saniere_vip(json.loads(row["vip_liste"] or "[]")),
            "gesetzt": True}


def preset_setzen(db: Database, user_id: str, bereich_id: str,
                  ton_preset: Any, vip_liste: Any) -> dict[str, Any]:
    """Upsert des Bereichs-Presets (fail-closed saniert). Idempotent je (user, bereich)."""
    ton = saniere_ton(ton_preset)
    vip = saniere_vip(vip_liste)
    ts = now_iso()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO regie_bereich_preset (id, user_id, bereich_id, ton_preset, vip_liste, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT (user_id, bereich_id) DO UPDATE SET ton_preset=excluded.ton_preset, "
        "vip_liste=excluded.vip_liste, updated_at=excluded.updated_at, deleted_at=NULL",
        (new_id(), user_id, bereich_id, json.dumps(ton, ensure_ascii=False),
         json.dumps(vip, ensure_ascii=False), ts, ts))
    conn.commit()
    db.audit(user_id, "user", "regie_preset_gesetzt",
             {"bereich_id": bereich_id, "vip_anzahl": len(vip)})
    return {"ok": True, "bereich_id": bereich_id, "ton_preset": ton, "vip_liste": vip}


# --- Router (MODUL-Ebene: PEP-563-Falle, s. domain.py) ----------------------

class _PresetIn(BaseModel):
    ton_preset: dict[str, Any] = {}
    vip_liste: list[str] = []


def build_preset_router(db: Database) -> APIRouter:
    """GET/PUT ``/api/regie/preset?bereich_id=`` (Query, damit '' = Allgemein sauber geht)."""
    r = APIRouter()

    @r.get("/api/regie/preset")
    def get_preset(bereich_id: str = "",
                   user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return preset_lesen(db, user.user_id, bereich_id)

    @r.put("/api/regie/preset")
    def put_preset(body: _PresetIn, bereich_id: str = "",
                   user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return preset_setzen(db, user.user_id, bereich_id, body.ton_preset, body.vip_liste)

    return r
