"""ELSTER-Transport — Vault + Zertifikat + Konnektor + Scharfschalt-Akt (M1-2,
docs/65 §8/§11/§12). Die vault-abhängige Schicht: sie wird NACH ``create_app``
verdrahtet, weil der appkit-Vault erst dort entsteht (``app.state.vault``).

Sie trägt die drei Geheimnis-Ränder des Transports — und hält sie dicht (I-2):

  * **PIN → Vault, ohne Echo:** die Zertifikats-PIN geht via ``vault.put`` unter den
    Schlüssel ``elster_pin_<zugang_id>`` (VREV-R-2: an die zugang_id gebunden) und
    wird NIE zurückgegeben, nie geloggt, nie in die DB geschrieben.
  * **.pfx → Daten-Wurzel, nie ins Repo:** das Software-Zertifikat wird atomar unter
    ``<data>\\apps\\money\\elster\\<zugang_id>.pfx`` abgelegt (io_safe); die Response
    trägt nur den Import-Status, nie die Bytes.
  * **Scharfschalten = Zwei-Schlüssel (§8):** Schlüssel 1 (angelegt) sitzt seit M1-1
    auf der Zeile; Schlüssel 2 (bestätigt) setzt der getrennte Scharfschalt-Akt —
    aber NUR, wenn Zertifikat UND PIN vorliegen (sonst wäre „scharf" irreführend).
    Senken ist immer ein einziger Klick.

Der ``ElsterKonnektor`` (``TokenConnector``, ``richtung="senden"``, ``sensitivity="hoch"``)
macht den Sende-Kanal in ``/api/konnektoren`` SICHTBAR: „verbunden" erst mit Zertifikat
+ PIN + Scharfschaltung. Gesendet wird dennoch NIE autonom über den Konnektor — die
Übermittlung ist ein bewusster HITL-Akt des Sende-Motors (M1-5, §8), die Basis-``senden``-
Methode bleibt der reine Deklarations-Slot.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from appkit import io_safe
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.connectors import ConnectorRegistry, TokenConnector, connectors_router
from appkit.vault import Vault

from . import vertrag as v
from .persistenz import ElsterSpeicher

#: ELSTER-Software-Zertifikate (.pfx) sind klein (wenige KB); harte Obergrenze gegen
#: versehentliche/böswillige Riesen-Uploads. Kein fachliches Limit, nur eine Schranke.
MAX_PFX_BYTES = 256 * 1024


class PinIn(BaseModel):
    pin: str                     # Zertifikats-PIN — geht in den Vault, wird NIE zurückgegeben


class ZertifikatIn(BaseModel):
    inhalt_b64: str              # Base64 des .pfx — wandert in die Daten-Wurzel, nie ins Repo


class ElsterKonnektor(TokenConnector):
    """Sichtbarkeits-Adapter des ELSTER-Sende-Kanals (§11). „verbunden" spiegelt die
    reale Sende-Bereitschaft: mindestens ein Zugang mit importiertem Zertifikat, PIN im
    Vault UND Zwei-Schlüssel-Scharfschaltung. Senden selbst läuft NIE autonom hier
    (Basis-``senden`` = HITL-Deklarations-Slot, §8) — der Konnektor zeigt nur an."""

    id = "elster"
    label = "ELSTER (Finanzamt)"
    kind = "steuer"
    richtung = "senden"          # die Steuererklärung geht RAUS
    sensitivity = "hoch"
    aktivierung = ("Zertifikat importieren + PIN im Tresor hinterlegen + scharfschalten "
                   "(Zwei-Schlüssel, docs/65 §8) + ERiC-Hersteller-ID setzen.")
    permissions = ("elster:senden",)

    def __init__(self, speicher: ElsterSpeicher, vault: Vault, *,
                 user_id: str = DEFAULT_USER_ID) -> None:
        super().__init__(vault_get=vault.get)
        self._speicher = speicher
        self._vault = vault
        self._user_id = user_id

    def verfuegbar(self) -> bool:
        for row in self._speicher.zugaenge_rows(self._user_id):
            if (row["zertifikat_importiert"]
                    and (row["angelegt_am"] or "").strip()
                    and (row["bestaetigt_am"] or "").strip()
                    and self._vault.get(row["pin_vault_key"]) is not None):
                return True
        return False


def _cert_dir(speicher: ElsterSpeicher) -> Path:
    """Ablage der Software-Zertifikate: ``<data>\\apps\\money\\elster\\`` (neben der
    App-DB, unter der Daten-Wurzel — nie im Repo, §8)."""
    return Path(speicher.db.db_path).parent / "elster"


def mache_aufraeumer(speicher: ElsterSpeicher, vault: Vault):
    """Delete-Zeit-Aufräumer (DSGVO „weg = weg" am Secret-Rand): entfernt beim Löschen
    eines Zugangs die Vault-PIN UND die .pfx-Datei. Fehler beim Datei-Löschen sind
    tolerierbar (die DB-Zeile geht ohnehin), der Vault-Eintrag ist die harte Pflicht."""
    cert_dir = _cert_dir(speicher)

    def _aufraeumen(row: Any) -> None:
        vault.delete(row["pin_vault_key"])
        try:
            (cert_dir / f"{row['id']}.pfx").unlink(missing_ok=True)
        except OSError:
            pass

    return _aufraeumen


def build_konnektor_router(speicher: ElsterSpeicher, vault: Vault, *,
                           user_id: str = DEFAULT_USER_ID) -> APIRouter:
    """Die vault-abhängigen ELSTER-Nähte (M1-2) + der Konnektor-Status. Wird per
    ``app.include_router`` NACH ``create_app`` eingehängt (dann existiert der Vault)."""
    reg = ConnectorRegistry()
    reg.register(ElsterKonnektor(speicher, vault, user_id=user_id))
    # Eigener, PRÄFIXLOSER Router für die /api/elster/…-Nähte; der Konnektor-Status
    # (GET /api/konnektoren, eigener Präfix) wird separat eingehängt — NICHT direkt auf
    # diesen Router legen, sonst erbten die elster-Routen den /api/konnektoren-Präfix.
    r = APIRouter()
    cert_dir = _cert_dir(speicher)

    @r.post("/api/elster/zugaenge/{zugang_id}/pin")
    def pin_setzen(zugang_id: str, body: PinIn, user: UserContext = Depends(current_user)):
        """PIN in den Vault (I-2) — ohne jedes Echo. Die Response bestätigt nur, DASS
        eine PIN hinterlegt ist, nie ihren Wert; das Audit trägt keine PIN."""
        row = speicher.zugang_row(user.user_id, zugang_id)
        if row is None:
            return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
        pin = (body.pin or "").strip()
        if not pin:
            return JSONResponse({"error": "PIN fehlt"}, status_code=400)
        vault.put(row["pin_vault_key"], pin)     # KEIN Rückgabewert, KEIN Log der PIN
        speicher.db.audit(user.user_id, "user", "elster_pin_gesetzt", {"zugang_id": zugang_id})
        return {"ok": True, "pin_gesetzt": True}

    @r.delete("/api/elster/zugaenge/{zugang_id}/pin")
    def pin_loeschen(zugang_id: str, user: UserContext = Depends(current_user)):
        row = speicher.zugang_row(user.user_id, zugang_id)
        if row is None:
            return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
        vault.delete(row["pin_vault_key"])
        speicher.db.audit(user.user_id, "user", "elster_pin_geloescht", {"zugang_id": zugang_id})
        return {"ok": True, "pin_gesetzt": False}

    @r.post("/api/elster/zugaenge/{zugang_id}/zertifikat")
    def zertifikat_importieren(zugang_id: str, body: ZertifikatIn,
                               user: UserContext = Depends(current_user)):
        """Importiert das .pfx atomar in die Daten-Wurzel (nie ins Repo, nie Echo der
        Bytes). Der Zugang gilt danach als ``zertifikat_importiert``; die DB trägt nur
        die Datei-REFERENZ (I-2)."""
        row = speicher.zugang_row(user.user_id, zugang_id)
        if row is None:
            return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
        try:
            daten = base64.b64decode(body.inhalt_b64 or "", validate=True)
        except (binascii.Error, ValueError):
            return JSONResponse({"error": "Zertifikat ist kein gültiges Base64"}, status_code=400)
        if not daten:
            return JSONResponse({"error": "Zertifikat ist leer"}, status_code=400)
        if len(daten) > MAX_PFX_BYTES:
            return JSONResponse({"error": "Zertifikat ist zu groß"}, status_code=400)
        cert_dir.mkdir(parents=True, exist_ok=True)
        ziel = cert_dir / f"{zugang_id}.pfx"
        io_safe.atomic_write_bytes(ziel, daten)
        speicher.zertifikat_setzen(user.user_id, zugang_id, str(ziel))
        return {"ok": True, "zertifikat_importiert": True}

    @r.post("/api/elster/zugaenge/{zugang_id}/scharf")
    def scharfschalten(zugang_id: str, user: UserContext = Depends(current_user)):
        """Scharf-Schlüssel 2 (§8): setzt ``bestaetigt_am`` — aber NUR mit Zertifikat
        UND PIN, sonst wäre „scharf" irreführend (fail-closed, 409). ``pruefe_scharf``
        geht danach durch (e2e-Akzeptanz M1-2)."""
        row = speicher.zugang_row(user.user_id, zugang_id)
        if row is None:
            return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
        if not row["zertifikat_importiert"] or vault.get(row["pin_vault_key"]) is None:
            return JSONResponse(
                {"error": "Erst Zertifikat importieren und PIN hinterlegen, dann "
                          "scharfschalten (Zwei-Schlüssel, docs/65 §8)."}, status_code=409)
        speicher.scharf_bestaetigen(user.user_id, zugang_id)
        schaltung = speicher.scharfschaltung(user.user_id, zugang_id)
        v.pruefe_scharf(schaltung)   # e2e: der Wächter muss jetzt durchgehen (fail-closed sonst)
        return {"ok": True, "scharf": True}

    @r.delete("/api/elster/zugaenge/{zugang_id}/scharf")
    def entschaerfen(zugang_id: str, user: UserContext = Depends(current_user)):
        """Scharf senken — immer ein einziger Klick, ohne Vorbedingung (§8)."""
        if not speicher.scharf_zuruecknehmen(user.user_id, zugang_id):
            return JSONResponse({"error": "Zugang unbekannt"}, status_code=404)
        return {"ok": True, "scharf": False}

    # Konnektor-Status (read-only, eigener Präfix /api/konnektoren) mit einhängen.
    r.include_router(connectors_router(reg))
    return r
