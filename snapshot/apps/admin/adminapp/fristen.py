"""Fristen-Cockpit von Dizz Admin (docs/28 §3, Phase 3) — der netzwerkweite,
**kategorie-gefilterte** Frist-Aggregator über ALLE Module der vereinten App:
Aufgaben + Termine (Projekte) · Rechnungen + Geschäfts-Fristen (Geschäft) ·
Studien-/Prüfungsfristen (Studium) · Dokument-Aufbewahrung (Tresor, opt-in).

Read-only — beobachtet + bündelt, schlägt nie eigenmächtig etwas an (die
HITL-Aktionen leben in den Quell-Modulen). Jede Frist trägt ihren ``bereich_id``
⇒ „sofort sichtbar: diese Frist = Studium, jene = Geschäft" (Bereichs-Achse,
docs/28 §1). Die per-Modul-Wächter (`/api/erinnerungen`, `/api/waechter`,
`/api/fristen/uebersicht`) bleiben; dies ist die EINE übergreifende Sicht darüber.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from appkit.auth import UserContext, current_user
from appkit.db import Database

from .tresor import aufbewahrung_bis

# Dringlichkeits-Ränge (für Sortierung/Gruppierung).
DRINGLICHKEIT = ("ueberfaellig", "heute", "woche", "monat", "spaeter")

# A5 (docs/30): aus welchen Frist-Arten sich direkt eine Aufgabe erzeugen lässt.
# `aufgabe` ist ausgenommen (ist schon eine); `aufbewahrung` zeigt auf ein Dokument.
ZU_AUFGABE_ARTEN = ("rechnung", "frist", "studienfrist", "termin", "mahnung", "dokument")


class FristZuAufgabeIn(BaseModel):
    """A5 Frist→Aufgabe (in-Prozess, docs/30): erzeugt aus einer Cockpit-Frist eine
    Aufgabe im Projekte-Modul. ``ref`` = die stabile Cockpit-Referenz
    (``admin:<art>:<id>``). Optionale Übersteuerungen für Titel/Priorität/Projekt."""
    ref: str
    titel: str = ""             # leer ⇒ aus der Quelle abgeleitet
    prioritaet: str = "mittel"
    projekt_id: str = ""


# ── iCalendar (RFC 5545) — die Fristen netzwerkweit als abonnierbarer Feed ──────
# Datenportabilität (2026-Standard): JEDE Kalender-App (Apple/Google/Outlook) kann
# den unifizierten Fristen-Strom read-only abonnieren. Reiner Text — keine Lib nötig.
def _ics_escape(text: str) -> str:
    """Escapt SUMMARY/DESCRIPTION-Text gemäß RFC 5545 §3.3.11."""
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")
            .replace("\r", "\\n"))   # lone CR (ohne LF): lenient iCal-Parser könnten ihn als Zeilenbruch lesen (G3)


def _ics_fold(zeile: str) -> str:
    """Faltet Content-Lines >75 Oktette (RFC 5545 §3.1, CRLF + Leerzeichen-Einzug).
    Byte-genau (UTF-8), damit Mehrbyte-Zeichen nicht mitten zerteilt werden."""
    roh = zeile.encode("utf-8")
    if len(roh) <= 75:
        return zeile
    teile, rest = [], roh
    grenze = 75
    while len(rest) > grenze:
        schnitt = grenze
        while schnitt > 0 and (rest[schnitt] & 0xC0) == 0x80:  # nicht in einem UTF-8-Folgebyte schneiden
            schnitt -= 1
        teile.append(rest[:schnitt]); rest = rest[schnitt:]; grenze = 74  # Folgezeilen: 1 Oktett fürs Leerzeichen
    teile.append(rest)
    return "\r\n ".join(t.decode("utf-8") for t in teile)


def _ics_datum(faellig: str) -> str:
    """ISO-Date (YYYY-MM-DD…) → iCal DATE-Wert (YYYYMMDD) für ganztägige Fristen."""
    return (faellig or "")[:10].replace("-", "")


def _bucket(faellig: str, heute: str, woche: str, monat: str) -> str:
    """ISO-Date-Vergleich (lexikalisch korrekt) → Dringlichkeits-Eimer."""
    if faellig < heute:
        return "ueberfaellig"
    if faellig == heute:
        return "heute"
    if faellig <= woche:
        return "woche"
    if faellig <= monat:
        return "monat"
    return "spaeter"


class FristenCockpit:
    """Aggregiert alle Frist-Quellen der vereinten App, normalisiert auf einen
    einheitlichen Eintrag und gruppiert nach Dringlichkeit — optional nach Bereich
    gefiltert. Reine Lese-Logik auf den geteilten Domänen-Tabellen."""

    def __init__(self, db: Database, projekte=None) -> None:
        self.db = db
        self.projekte = projekte    # ProjekteDomain — A5 Frist→Aufgabe (in-Prozess)

    def _sammle(self, user_id: str, *, mit_aufbewahrung: bool) -> list[dict[str, Any]]:
        conn = self.db.get_conn()
        heute = date.today().isoformat()
        items: list[dict[str, Any]] = []

        def add(quelle, art, titel, faellig, bereich_id, ref, **extra):
            if faellig:
                items.append({"quelle": quelle, "art": art, "titel": titel,
                              "faellig": faellig, "bereich_id": bereich_id or "",
                              "ref": ref, **extra})

        # Aufgaben (Projekte) — offene mit Fälligkeit
        for r in conn.execute(
                "SELECT id, titel, faellig, prioritaet, bereich_id FROM aufgaben "
                "WHERE user_id=? AND deleted_at IS NULL AND status!='erledigt' "
                "AND faellig!=''", (user_id,)).fetchall():
            add("projekte", "aufgabe", r["titel"], r["faellig"], r["bereich_id"],
                f"admin:aufgabe:{r['id']}", prioritaet=r["prioritaet"])

        # Termine (Projekte) — nur anstehende (ab heute)
        for r in conn.execute(
                "SELECT id, titel, beginn, bereich_id FROM termine "
                "WHERE user_id=? AND deleted_at IS NULL AND beginn!=''", (user_id,)).fetchall():
            tag = (r["beginn"] or "")[:10]
            if tag >= heute:
                add("projekte", "termin", r["titel"], tag, r["bereich_id"],
                    f"admin:termin:{r['id']}")

        # Rechnungen (Geschäft) — gestellt + unbezahlt
        for r in conn.execute(
                "SELECT id, nummer, titel, faellig_am, bereich_id FROM rechnungen "
                "WHERE user_id=? AND deleted_at IS NULL AND status='offen' "
                "AND faellig_am!=''", (user_id,)).fetchall():
            label = r["titel"] or f"Rechnung {r['nummer']}".strip()
            add("geschaeft", "rechnung", label, r["faellig_am"], r["bereich_id"],
                f"admin:rechnung:{r['id']}")

        # Mahnungen (A8) — offene Mahn-Fristen; Bereich erbt von der Rechnung
        for r in conn.execute(
                "SELECT m.id, m.stufe, m.titel, m.frist_am, r.bereich_id FROM mahnungen m "
                "LEFT JOIN rechnungen r ON r.id=m.rechnung_id AND r.deleted_at IS NULL "
                "WHERE m.user_id=? AND m.status='offen' AND m.deleted_at IS NULL "
                "AND m.frist_am<>''", (user_id,)).fetchall():
            add("geschaeft", "mahnung", r["titel"] or f"Mahnung Stufe {r['stufe']}",
                r["frist_am"], r["bereich_id"] or "", f"admin:mahnung:{r['id']}",
                stufe=r["stufe"])

        # Geschäfts-Fristen
        for r in conn.execute(
                "SELECT id, titel, kategorie, faellig_am, bereich_id FROM fristen "
                "WHERE user_id=? AND deleted_at IS NULL AND erledigt=0 "
                "AND faellig_am!=''", (user_id,)).fetchall():
            add("geschaeft", "frist", r["titel"], r["faellig_am"], r["bereich_id"],
                f"admin:frist:{r['id']}", kategorie=r["kategorie"])

        # Studien-/Prüfungsfristen — bereich_id über den Bildungsweg
        for r in conn.execute(
                "SELECT sf.id, sf.titel, sf.art, sf.faellig_am, bw.bereich_id "
                "FROM studienfrist sf LEFT JOIN bildungsweg bw "
                "  ON bw.id=sf.bildungsweg_id AND bw.deleted_at IS NULL "
                "WHERE sf.user_id=? AND sf.deleted_at IS NULL AND sf.erledigt=0 "
                "AND sf.faellig_am!=''", (user_id,)).fetchall():
            add("studium", "studienfrist", r["titel"], r["faellig_am"], r["bereich_id"],
                f"admin:studienfrist:{r['id']}", studien_art=r["art"])

        # Dokument-Aufbewahrung (Tresor) — opt-in (Jahre weit voraus, informativ)
        if mit_aufbewahrung:
            for r in conn.execute(
                    "SELECT id, titel, typ, erstellt_am, bereich_id FROM dokumente "
                    "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall():
                jahr = aufbewahrung_bis(r["typ"], r["erstellt_am"])
                if jahr:
                    add("tresor", "aufbewahrung", r["titel"], f"{jahr}-12-31",
                        r["bereich_id"], f"admin:dokument:{r['id']}", typ=r["typ"])

        return items

    def cockpit(self, user_id: str, *, bereich_id: str | None = None,
                horizont_tage: int = 90, mit_aufbewahrung: bool = False) -> dict[str, Any]:
        """Gebündelte Frist-Sicht. ``bereich_id`` filtert auf einen Bereich
        (``''`` = nur „Allgemein"/unzugeordnet); None = alle. Überfällige sind
        IMMER dabei; künftige nur innerhalb ``horizont_tage``."""
        heute_d = date.today()
        heute = heute_d.isoformat()
        woche = (heute_d + timedelta(days=7)).isoformat()
        monat = (heute_d + timedelta(days=30)).isoformat()
        horizont = (heute_d + timedelta(days=max(0, horizont_tage))).isoformat()

        gruppen: dict[str, list] = {k: [] for k in DRINGLICHKEIT}
        je_bereich: dict[str, int] = {}
        for it in self._sammle(user_id, mit_aufbewahrung=mit_aufbewahrung):
            if bereich_id is not None and it["bereich_id"] != bereich_id:
                continue
            # Horizont: Überfälliges immer, Künftiges nur bis horizont. Aufbewahrung
            # (Jahre voraus, rein informativ) ist vom Horizont ausgenommen — sie
            # erscheint nur per opt-in und immer im Eimer „später".
            if it["art"] != "aufbewahrung" and it["faellig"] > horizont:
                continue
            it["dringlichkeit"] = _bucket(it["faellig"], heute, woche, monat)
            gruppen[it["dringlichkeit"]].append(it)
            je_bereich[it["bereich_id"]] = je_bereich.get(it["bereich_id"], 0) + 1

        for k in gruppen:
            gruppen[k].sort(key=lambda x: (x["faellig"], x["titel"]))
        zaehler = {k: len(v) for k, v in gruppen.items()}
        return {"heute": heute, "horizont": horizont,
                "bereich_id": bereich_id, "gruppen": gruppen, "zaehler": zaehler,
                "je_bereich": je_bereich, "gesamt": sum(zaehler.values())}

    def _bereich_namen(self, user_id: str) -> dict[str, str]:
        """id→Name der nicht gelöschten Bereiche (für Kategorie/Beschreibung im Feed)."""
        rows = self.db.get_conn().execute(
            "SELECT id, name FROM bereiche WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchall()
        return {r["id"]: r["name"] for r in rows}

    # Modul-Label je Frist-Art (für SUMMARY/CATEGORIES im iCal-Feed).
    _ART_LABEL = {"aufgabe": "Aufgabe", "termin": "Termin", "rechnung": "Rechnung",
                  "frist": "Frist", "mahnung": "Mahnung", "studienfrist": "Studien-Frist",
                  "aufbewahrung": "Aufbewahrung"}

    def cockpit_ics(self, user_id: str, *, bereich_id: str | None = None,
                    horizont_tage: int = 365, mit_aufbewahrung: bool = False) -> str:
        """Der unifizierte Fristen-Strom als iCalendar (RFC 5545) — abonnierbar aus
        jeder Kalender-App. Ganztägige VEVENTs; ``UID`` = stabile ``ref`` ⇒ Re-Sync
        idempotent (kein Duplikat). Default-Horizont weit (365 T), damit ein Abo auch
        Künftiges sieht. Reine Lese-Projektion über dieselbe Quelle wie ``cockpit``."""
        daten = self.cockpit(user_id, bereich_id=bereich_id, horizont_tage=horizont_tage,
                             mit_aufbewahrung=mit_aufbewahrung)
        namen = self._bereich_namen(user_id)
        items = sorted((it for gruppe in daten["gruppen"].values() for it in gruppe),
                       key=lambda x: (x["faellig"], x["titel"]))
        jetzt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        kal_name = "Dizz Admin — Fristen" + (
            f" · {namen.get(bereich_id, 'Allgemein')}" if bereich_id is not None else "")
        zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0",
                  "PRODID:-//the world of dizzi//Dizz Admin Fristen//DE",
                  "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                  _ics_fold("X-WR-CALNAME:" + _ics_escape(kal_name)),
                  _ics_fold("X-WR-CALDESC:" + _ics_escape(
                      "Unifizierter Fristen-Strom (Aufgaben · Termine · Rechnungen · "
                      "Geschäfts-/Studien-Fristen) aus Dizz Admin."))]
        for it in items:
            tag = _ics_datum(it["faellig"])
            if not tag:
                continue
            try:                                  # ganztägig: DTEND = Folgetag (exklusiv)
                tag_ende = (date.fromisoformat(it["faellig"][:10]) + timedelta(days=1)).strftime("%Y%m%d")
            except ValueError:
                tag_ende = tag
            bname = namen.get(it["bereich_id"], "Allgemein") if it["bereich_id"] else "Allgemein"
            art = self._ART_LABEL.get(it["art"], it["art"])
            uid = (it["ref"] or f"{it['quelle']}:{it['titel']}:{tag}") + "@dizz-admin"
            beschr = f"Bereich: {bname} · Art: {art} · Quelle: {it['quelle']}"
            zeilen += [
                "BEGIN:VEVENT",
                _ics_fold("UID:" + _ics_escape(uid)),
                "DTSTAMP:" + jetzt,
                "DTSTART;VALUE=DATE:" + tag,
                "DTEND;VALUE=DATE:" + tag_ende,
                _ics_fold("SUMMARY:" + _ics_escape(f"⏰ {it['titel']}")),
                _ics_fold("DESCRIPTION:" + _ics_escape(beschr)),
                _ics_fold("CATEGORIES:" + _ics_escape(bname) + "," + _ics_escape(art)),
                "TRANSP:TRANSPARENT",
                "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-P1D",
                _ics_fold("DESCRIPTION:" + _ics_escape(it["titel"])), "END:VALARM",
                "END:VEVENT"]
        zeilen.append("END:VCALENDAR")
        return "\r\n".join(zeilen) + "\r\n"

    # ── A5: Frist → Aufgabe (in-Prozess, docs/30) ──────────────────────────
    def _quelle_details(self, user_id: str, ref: str) -> dict[str, Any] | None:
        """Löst eine Cockpit-Referenz (``admin:<art>:<id>``) auf einen einheitlichen
        Frist-Steckbrief auf: ``{art, label, faellig, bereich_id}``. ``None`` wenn die
        Referenz unbekannt ist; ``{"fehler": ...}`` wenn die Art nicht wandelbar ist."""
        teile = (ref or "").split(":")
        if len(teile) < 3 or teile[0] != "admin":
            return None
        art, rid = teile[1], ":".join(teile[2:])
        if art == "aufgabe":
            return {"fehler": "Das ist bereits eine Aufgabe."}
        if art not in ZU_AUFGABE_ARTEN:
            return {"fehler": f"Aus '{art}' lässt sich keine Aufgabe erzeugen."}
        conn = self.db.get_conn()
        try:
            if art == "rechnung":
                r = conn.execute("SELECT nummer, titel, faellig_am, bereich_id FROM rechnungen "
                                 "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                                 (rid, user_id)).fetchone()
                if r:
                    label = (r["titel"] or "").strip() or f"Rechnung {r['nummer']}".strip()
                    return {"art": art, "label": f"Rechnung nachfassen: {label}",
                            "faellig": r["faellig_am"], "bereich_id": r["bereich_id"]}
            elif art == "frist":
                r = conn.execute("SELECT titel, faellig_am, bereich_id FROM fristen "
                                 "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                                 (rid, user_id)).fetchone()
                if r:
                    return {"art": art, "label": r["titel"], "faellig": r["faellig_am"],
                            "bereich_id": r["bereich_id"]}
            elif art == "studienfrist":
                r = conn.execute(
                    "SELECT sf.titel, sf.faellig_am, bw.bereich_id FROM studienfrist sf "
                    "LEFT JOIN bildungsweg bw ON bw.id=sf.bildungsweg_id AND bw.deleted_at IS NULL "
                    "WHERE sf.id=? AND sf.user_id=? AND sf.deleted_at IS NULL",
                    (rid, user_id)).fetchone()
                if r:
                    return {"art": art, "label": r["titel"], "faellig": r["faellig_am"],
                            "bereich_id": r["bereich_id"] or ""}
            elif art == "termin":
                r = conn.execute("SELECT titel, beginn, bereich_id FROM termine "
                                 "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                                 (rid, user_id)).fetchone()
                if r:
                    return {"art": art, "label": r["titel"], "faellig": (r["beginn"] or "")[:10],
                            "bereich_id": r["bereich_id"]}
            elif art == "mahnung":
                r = conn.execute(
                    "SELECT m.stufe, m.titel, m.frist_am, r.bereich_id FROM mahnungen m "
                    "LEFT JOIN rechnungen r ON r.id=m.rechnung_id AND r.deleted_at IS NULL "
                    "WHERE m.id=? AND m.user_id=? AND m.deleted_at IS NULL",
                    (rid, user_id)).fetchone()
                if r:
                    return {"art": art, "label": r["titel"] or f"Mahnung Stufe {r['stufe']}",
                            "faellig": r["frist_am"], "bereich_id": r["bereich_id"] or ""}
            elif art == "dokument":   # Aufbewahrungs-Frist eines Tresor-Dokuments
                r = conn.execute("SELECT titel, typ, erstellt_am, bereich_id FROM dokumente "
                                 "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                                 (rid, user_id)).fetchone()
                if r:
                    jahr = aufbewahrung_bis(r["typ"], r["erstellt_am"])
                    return {"art": art, "label": f"Aufbewahrung prüfen: {r['titel']}",
                            "faellig": f"{jahr}-12-31" if jahr else "",
                            "bereich_id": r["bereich_id"]}
        except Exception:   # noqa: BLE001 — fehlende Tabelle/Spalte ⇒ „unbekannt"
            return None
        return None

    def frist_zu_aufgabe(self, user_id: str, ref: str, *, titel: str = "",
                         prioritaet: str = "mittel", projekt_id: str = "") -> dict[str, Any]:
        """Erzeugt aus einer Cockpit-Frist eine Aufgabe (Projekte-Modul, in-Prozess).
        Idempotent: gibt es zur selben ``ref`` schon eine (nicht gelöschte) Aufgabe,
        wird KEINE zweite angelegt (Status ``vorhanden``). Die Aufgabe erbt Fälligkeit
        und Bereich der Quelle (Bereichs-Achse bleibt erhalten)."""
        if self.projekte is None:
            return {"ok": False, "fehler": "Projekte-Modul nicht verfügbar."}
        det = self._quelle_details(user_id, ref)
        if det is None:
            return {"ok": False, "fehler": "Frist-Referenz unbekannt."}
        if det.get("fehler"):
            return {"ok": False, "fehler": det["fehler"]}
        conn = self.db.get_conn()
        vorhanden = conn.execute(
            "SELECT id FROM aufgaben WHERE user_id=? AND quelle_ref=? AND deleted_at IS NULL",
            (user_id, ref)).fetchone()
        if vorhanden:
            return {"ok": True, "status": "vorhanden", "id": vorhanden["id"],
                    "aufgabe_id": vorhanden["id"]}
        titel = (titel or "").strip() or det["label"] or "Aufgabe aus Frist"
        try:
            aid = self.projekte.neue_aufgabe(
                user_id, titel=titel, projekt_id=(projekt_id or "").strip(),
                prioritaet=prioritaet, faellig=(det.get("faellig") or ""),
                notiz=f"Erzeugt aus Frist {ref}.", quelle_ref=ref)
        except ValueError as e:
            return {"ok": False, "fehler": str(e)}
        bereich_id = det.get("bereich_id") or ""
        if bereich_id:                          # Bereichs-Achse der Quelle übernehmen
            conn.execute("UPDATE aufgaben SET bereich_id=? WHERE id=? AND user_id=?",
                         (bereich_id, aid, user_id))
            conn.commit()
        self.db.audit(user_id, "user", "frist_zu_aufgabe",
                      {"ref": ref, "aufgabe_id": aid, "art": det["art"]})
        return {"ok": True, "status": "angelegt", "id": aid, "aufgabe_id": aid,
                "titel": titel, "faellig": det.get("faellig") or "", "bereich_id": bereich_id}

    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/fristen-cockpit")
        def fristen_cockpit(bereich_id: str | None = None, horizont_tage: int = 90,
                            aufbewahrung: str = "0",
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            return self.cockpit(user.user_id, bereich_id=bereich_id,
                                horizont_tage=horizont_tage,
                                mit_aufbewahrung=aufbewahrung in ("1", "true"))

        @r.post("/api/fristen-cockpit/zu-aufgabe")
        def fristen_zu_aufgabe(body: FristZuAufgabeIn,
                               user: UserContext = Depends(current_user)):
            """A5 (docs/30): macht aus einer Cockpit-Frist eine Aufgabe (in-Prozess,
            Projekte-Modul). Idempotent über die Herkunfts-Referenz; erbt Fälligkeit
            + Bereich der Quelle. HITL — wird per Klick aus dem Cockpit ausgelöst."""
            if not (body.ref or "").strip():
                raise HTTPException(400, "ref ist Pflicht.")
            res = self.frist_zu_aufgabe(user.user_id, body.ref.strip(),
                                        titel=body.titel, prioritaet=body.prioritaet,
                                        projekt_id=body.projekt_id)
            if not res.get("ok"):
                return JSONResponse(res, status_code=404 if "unbekannt" in res.get("fehler", "")
                                    else 400)
            return res

        @r.get("/api/fristen-cockpit.ics")
        def fristen_cockpit_ics(bereich_id: str | None = None, horizont_tage: int = 365,
                                aufbewahrung: str = "0",
                                user: UserContext = Depends(current_user)) -> Response:
            """iCalendar-Feed (RFC 5545) desselben Fristen-Stroms — abonnierbar aus
            jeder Kalender-App (Datenportabilität, 2026-Standard). ``bereich_id``
            filtert (None=alle), Default-Horizont 365 Tage."""
            ics = self.cockpit_ics(user.user_id, bereich_id=bereich_id,
                                   horizont_tage=horizont_tage,
                                   mit_aufbewahrung=aufbewahrung in ("1", "true"))
            return Response(content=ics, media_type="text/calendar; charset=utf-8",
                            headers={"Content-Disposition":
                                     "inline; filename=dizz-admin-fristen.ics"})

        return r
