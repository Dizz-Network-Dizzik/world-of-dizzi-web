"""P6.1 (Multi-User-Reife): die Nacht-Konsolidierung iteriert über ALLE Nutzer
(per-Nutzer-Fälligkeit), im Single-User-Betrieb exakt [dizzi] (Verhalten
unverändert). System-scoped Loops (Observer/Defense/Health-Watch) bleiben bewusst
DEFAULT_USER_ID — sie beobachten EIN System, nicht N Nutzer."""

import pytest

from app import db, main
from app.ai import analyst, memory


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_alle_user_ids_single_user_ist_dizzi():
    assert db.alle_user_ids() == ["dizzi"]


def test_alle_user_ids_vereinigt_aktive_nutzer():
    memory.save_message("alice", "user", "hallo")     # chat_messages
    db.setting_put("bob", "irgendwas", 1)             # app_settings
    db.get_conn().execute(
        "INSERT INTO memory_facts (id, user_id, fact, source, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)", (db.new_id(), "carol", "x", "explizit",
                                 db.now_iso(), db.now_iso()))
    db.get_conn().commit()
    ids = db.alle_user_ids()
    assert {"dizzi", "alice", "bob", "carol"} <= set(ids)


@pytest.mark.anyio
async def test_consolidation_tick_iteriert_alle_nutzer(monkeypatch):
    memory.save_message("alice", "user", "hi")
    memory.save_message("dizzi", "user", "hi")
    gesehen: list[str] = []

    async def fake_consolidate(uid):
        gesehen.append(uid)
        return {"episodes_merged": 0}

    async def fake_suggest(uid):
        return 0

    monkeypatch.setattr(memory, "consolidate", fake_consolidate)
    monkeypatch.setattr(analyst, "suggest", fake_suggest)
    await main._consolidation_tick()
    assert set(gesehen) == {"alice", "dizzi"}          # BEIDE konsolidiert


@pytest.mark.anyio
async def test_consolidation_tick_ueberspringt_frische(monkeypatch):
    db.setting_put("dizzi", "last_consolidation", db.now_iso())   # gerade gelaufen
    gesehen: list[str] = []

    async def fake_consolidate(uid):
        gesehen.append(uid)
        return {}

    async def fake_suggest(uid):
        return 0

    monkeypatch.setattr(memory, "consolidate", fake_consolidate)
    monkeypatch.setattr(analyst, "suggest", fake_suggest)
    await main._consolidation_tick()
    assert gesehen == []                                # nicht fällig ⇒ übersprungen
