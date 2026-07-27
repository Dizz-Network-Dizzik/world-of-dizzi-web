"""Prüfkit für die netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17).

Bewusst pytest-frei (plain functions) — die App-Suiten importieren es und bauen
ihre eigenen Assertions darum. Zwei Ebenen:

* ``user_tabellen_ohne_deckung`` = STATIK: fängt die KA-H1-Fehlerklasse für
  immer. Sobald jemand eine neue Tabelle mit ``user_id`` anlegt, die WEDER
  ``deleted_at`` trägt (⇒ die Soft-Delete-Kaskade ``db.soft_delete_user`` greift)
  NOCH im ``on_delete``-Hook der App hart gelöscht wird NOCH eine dokumentierte
  Ausnahme ist, wird die Liste nicht mehr leer und die Suite der App rot. Kein
  Seeding nötig — reine Schema-Introspektion.
* ``pruefe_hook_loescht`` = DYNAMIK: nach einer echten Konto-Löschung beweist die
  App, dass die Hook-Tabellen des Nutzers wirklich leer sind (Seed → Löschen → 0).

Grenze (ehrlich): Kind-Tabellen OHNE eigene ``user_id``-Spalte (z. B. news
``watchlist_artikel``, das nur über eine FK-Kette am Nutzer hängt) sieht die
Statik NICHT — sie haben keine ``user_id``, tauchen also gar nicht erst auf.
Solche Tabellen deckt allein der dynamische Test der App (Seed → Löschen → 0).

Bewusst auf einer nackten ``sqlite3``-Connection statt über ``Database`` — damit
auch der Core (eigene conn-Verwaltung, kein ``appkit.db.Database``) das Kit nutzt.
Positionale Row-Zugriffe (``r[0]``/``r[1]``) sind row_factory-agnostisch
(funktionieren mit ``sqlite3.Row`` UND dem Default-Tuple).
"""

from __future__ import annotations


def _user_tabellen(conn) -> list[tuple[str, bool]]:
    """Alle Tabellen mit ``user_id``-Spalte: ``(name, hat_deleted_at)``.
    Introspektion wie ``appkit.db.Database.user_tabellen`` (db.py:210-221)."""
    namen = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()]
    out: list[tuple[str, bool]] = []
    for t in namen:
        spalten = {r[1] for r in conn.execute(
            f"PRAGMA table_info({t})").fetchall()}
        if "user_id" in spalten:
            out.append((t, "deleted_at" in spalten))
    return out


def user_tabellen_ohne_deckung(
    conn, *, hook_tabellen: frozenset[str],
    ausnahmen: frozenset[str] = frozenset({"audit_log"}),
) -> list[str]:
    """Alle Tabellen mit ``user_id``-Spalte, die WEDER ``deleted_at`` haben
    (Soft-Delete-Kaskade) NOCH vom ``on_delete``-Hook hart gelöscht werden
    (``hook_tabellen``) NOCH bewusste dokumentierte Ausnahme sind (``ausnahmen``,
    Default nur ``audit_log`` = Löschbeleg, muss überleben). Erwartung jeder
    gesunden App: ``[]``. Rückgabe sortiert (stabile, lesbare Fehlermeldung)."""
    offen = [
        t for t, hat_deleted in _user_tabellen(conn)
        if not hat_deleted and t not in hook_tabellen and t not in ausnahmen
    ]
    return sorted(offen)


def pruefe_hook_loescht(conn, user_id: str,
                        tabellen: frozenset[str]) -> dict[str, int]:
    """Nach einer Konto-Löschung: ``SELECT COUNT(*)`` je Hook-Tabelle WHERE
    ``user_id=?``. Erwartung: alle Werte 0 (der Hook hat hart geräumt). Rückgabe
    ``{tabelle: rest_zeilen}`` — die App assertet ``all(v == 0 for v in ...)``."""
    out: dict[str, int] = {}
    for t in sorted(tabellen):
        out[t] = conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (user_id,)
        ).fetchone()[0]
    return out
