"""Gesundheits-Quellen von Dizz Healthy — der austauschbare Wearable-Stecker.

═══════════════════════════════════════════════════════════════════════════════
GESETZ 5 — VORBEREITUNG, NICHT BAU. Dieses Modul ist bewusst ein Gerüst aus
dokumentierten Slots. v1 trägt seine Daten MANUELL ein (über den Domänen-Router);
Smartwatch/Wearable ist hier so weit vorbereitet, dass die spätere Anbindung ein
**Stecker** ist, kein Umbau. Bewusstsein über das Vorhandensein dieser Anschlüsse
ist ausdrücklich Teil des Auftrags (Gesetz 5) — sie stehen im Code UND in der
Systemübersicht (SYSTEMUEBERSICHT.md) + docs/04_WEARABLE_VORBEREITUNG.md.
═══════════════════════════════════════════════════════════════════════════════

Kernidee (docs/RECHERCHE §2–§3): Wearable-Daten sind fragmentiert. Die App spricht
deshalb NIE direkt mit einem konkreten Gerät/Anbieter, sondern gegen EIN Interface
``HealthSource``. Jeder Adapter normiert seine Rohdaten auf ``HealthSample`` (FHIR-
Observation-nah, siehe fhir.py) — ab da ist die Herkunft (Apple/Garmin/BLE/manuell)
für die Domäne unsichtbar.

Vorbereitete Adapter (dokumentierte Slots — v1 DORMANT, ehrlich „nicht verbunden"):

- ``ManualSource``         — v1 ECHT: Hülle um manuell/CSV gelieferte Proben
                             (symmetrisch zu künftigen Live-Quellen; die Domäne
                             ruft immer ``list_samples``).
- ``AppleHealthSource``    — Apple HealthKit. **Kein Cloud-Backend-API** (HealthKit
                             ist gerätelokal): braucht die native Mobile-Schale, die
                             mit Einwilligung liest und Proben an diesen Dienst
                             schickt. ⇒ hängt an der Mobile-Brücke (Tauri, s. u.).
- ``HealthConnectSource``  — Android Health Connect (gleiches gerätelokale Modell
                             wie HealthKit; medizinische Daten als FHIR). ⇒ Mobile-Brücke.
- ``UnifiedApiSource``     — EINE Integration für ~alle Geräte über Terra/Spike/Vital
                             (Garmin, Oura, Fitbit, Whoop, …). Cloud-API, Token-Tresor-
                             gated (wie Plans' Google-Adapter). Opt-in, kostet ⇒ nur
                             wenn der 0-€-Anspruch es wert ist (sonst Apple/Google nativ).
- ``BLEHeartRateSource``   — **BLE/GATT-Slot**: direkte Bluetooth-LE-Kopplung für
                             Geräte ohne Cloud (Standard-GATT-Profile: Heart Rate
                             0x180D, Battery 0x180F). Desktop-tauglich, sobald ein
                             BLE-Stack (z. B. ``bleak``) eingehängt wird.

Künftige Slots (gleiche Schnittstelle, kein Domänen-Umbau): ``GarminHealthSource``,
``OuraSource``, ``FitbitSource`` (Hersteller-direkt, volle Tiefe) — als ``HealthSource``.

── Mobile-Brücke (Abhängigkeit, dokumentiert) ────────────────────────────────────
HealthKit/Health Connect sind gerätelokal ⇒ es braucht eine native App. Geplant:
die **Tauri-2-Mobile-Schale** des Netzwerks (Rust-Kern offen). Sie liest mit
Einwilligung und POSTet normierte Proben an einen künftigen Endpunkt
``POST /api/samples/ingest`` (Slot, v1 nicht offen) hinter verifizierter Verbindung.
Bis dahin ist Health **Desktop-first** (Nutzer-Entscheid Fragerunde 3): manuelle
Eingabe am PC, Geräteanbindung kommt mit der Schale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Normiertes Austauschformat (was JEDER Adapter liefert) ────────────────────
@dataclass
class HealthSample:
    """Eine Mess-Probe aus einer (beliebigen) Quelle, normiert auf das Domänen-
    Modell und FHIR-Observation-nah (siehe fhir.py).

    ``art`` ist ein Schlüssel aus ``fhir.MESSWERT_ARTEN`` (gewicht/puls/…).
    ``extern_id`` ist der stabile Schlüssel der Quelle (HealthKit-UUID / Geräte-
    Reading-ID) — er trägt die Idempotenz des Imports (Dedupe) und später den
    Sync. ``geraet`` benennt die Quelle (Gerät/App). ``etag`` ist die Versionsmarke
    (Last-Modified) für den späteren Zwei-Wege-Sync.
    """

    art: str
    wert: float
    gemessen_am: str                  # ISO-8601 (UTC bevorzugt)
    einheit: str = ""                 # leer ⇒ Standard-Einheit aus dem Katalog
    quelle: str = "manuell"           # manuell|apple_health|health_connect|terra|ble|…
    extern_id: str = ""               # Fremd-ID (Dedupe + Sync)
    geraet: str = ""                  # Gerät/App-Name
    etag: str = ""                    # Versionsmarke (Slot)


# ── GPS-Routen-Slot (P3, Gesetz 5: VORBEREITET, nicht gebaut) ─────────────────
@dataclass
class RoutePunkt:
    """Ein GPS-Trackpunkt. Kommt später vom Handy-GPS bzw. HealthKit/Health Connect
    (Workout-Routen) über die Mobile-Brücke — Desktop-first v1 erfasst keine Routen."""

    lat: float
    lon: float
    zeit: str = ""                    # ISO-8601
    hoehe: float | None = None        # Meter
    tempo: float | None = None        # min/km (abgeleitet)


@dataclass
class GPSRoute:
    """Eine aufgezeichnete GPS-Route (Lauf/Rad/Wanderung) — **vorbereiteter Slot**.

    Andockpunkt wie die Proben: die native Mobile-Schale (Tauri) liest die Route mit
    Einwilligung und POSTet sie später an einen Ingest-Endpunkt (``/api/routen/ingest``,
    v1 NICHT offen) hinter verifizierter Verbindung. ``distanz_km``/``dauer_min`` füttern
    dann die Aktivitäts-Tagesbilanz (Distanz/aktive Minuten); GPS-Rohpunkte bleiben
    sensibel (Standortdaten ⇒ lokal, nie an Cloud-/Boost-Modelle).
    """

    extern_id: str
    art: str = "lauf"                 # lauf|rad|wanderung|…
    beginn: str = ""                  # ISO-8601
    distanz_km: float | None = None
    dauer_min: float | None = None
    punkte: list[RoutePunkt] = field(default_factory=list)
    quelle: str = "apple_health"      # Herkunft (Mobile-Brücke)


# ── Interface (der Vertrag, gegen den die Domäne arbeitet) ────────────────────
class HealthSource(ABC):
    """Quelle von Gesundheits-Proben. v1 read-only (Einzug); Schreiben zurück an
    das Gerät = späterer Slot. Adapter implementieren ``verfuegbar`` (ehrlich) +
    ``list_samples`` (normiert auf ``HealthSample``)."""

    name: str = "quelle"

    @abstractmethod
    def verfuegbar(self) -> bool:
        """True, wenn die Quelle nutzbar ist (Token vorhanden / Brücke verbunden /
        BLE-Stack da). Ehrlich statt optimistisch — ungenutzte Slots melden False."""

    @abstractmethod
    def list_samples(self, since: str = "", until: str = "") -> list[HealthSample]:
        """Proben im Zeitfenster ``[since, until]`` (ISO-Daten; leer = alle)."""

    def status(self) -> dict[str, Any]:
        """Für UI/MCP: was ist das, ist es verbunden, was fehlt zur Aktivierung?"""
        return {"name": self.name, "verbunden": self.verfuegbar()}


class QuelleNichtVerbunden(RuntimeError):
    """Adapter ist deklariert, aber (noch) nicht verbunden — ehrlich statt raten."""


# ── ManualSource (v1 ECHT) ────────────────────────────────────────────────────
class ManualSource(HealthSource):
    """``HealthSource`` über manuell/aus einer Datei gelieferten Proben.

    v1 ist die lokale DB die Wahrheit (Eingabe über den Router). ``ManualSource``
    erfüllt das Interface trotzdem, damit ein späterer Stapel-Import (CSV/JSON
    historischer Werte) denselben Pfad nimmt wie Live-Quellen — die Domäne ruft
    immer ``list_samples`` und dedupt über ``extern_id``.
    """

    name = "manuell"

    def __init__(self, samples: list[HealthSample] | None = None) -> None:
        self._samples = list(samples or [])

    def verfuegbar(self) -> bool:
        return True   # manuelle Eingabe ist immer „da"

    def list_samples(self, since: str = "", until: str = "") -> list[HealthSample]:
        out = self._samples
        if since:
            out = [s for s in out if s.gemessen_am >= since]
        if until:
            out = [s for s in out if s.gemessen_am <= until]
        return out

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "verbunden": True,
                "hinweis": "Manuelle Eingabe (v1-Standard). Stapel-Import (CSV/JSON) "
                           "läuft später über denselben Pfad."}


# ── Cloud-Unified (Terra/Spike/Vital) — Token-Tresor-gated, v1 DORMANT ─────────
class UnifiedApiSource(HealthSource):
    """EINE Integration für ~alle Geräte über einen Unified-Wearable-Anbieter
    (Terra/Spike/Vital, docs/RECHERCHE §2). Cloud-API ⇒ Token im Tresor nötig
    (wie der Google-Adapter in Dizz Plans), ausdrücklich opt-in und ggf.
    kostenpflichtig (verletzt den 0-€-Anspruch, daher nicht Default).

    ── Aktivierung (Gesetz 5: vorbereitet, nicht aktiv) ──────────────────────
    1. Konto beim Anbieter; Geräte des Nutzers dort verbinden (OAuth-Widget).
    2. API-Key/Webhook-Secret verschlüsselt in den App-Token-Tresor legen
       (appkit/vault.py, Name = ``token_name``) — NIE in app_settings.
    3. ``verfuegbar()`` wird True; ``list_samples`` ruft die Anbieter-API
       (``/v2/...``), normiert auf ``HealthSample`` (Felder identisch).
    """

    name = "terra"
    API_DOC = "https://docs.tryterra.co"   # Referenz für die spätere Aktivierung

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str = "terra_api_key", anbieter: str = "terra",
                 http_get: Callable[..., Any] | None = None) -> None:
        self._vault_get = vault_get or (lambda _n: None)
        self.token_name = token_name
        self.name = anbieter
        self._http_get = http_get

    def verfuegbar(self) -> bool:
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "token_name": self.token_name,
                "hinweis": "Unified-Wearable-API (Terra/Spike/Vital). API-Key im "
                           "Token-Tresor hinterlegen, dann read-only aktiv. Opt-in, "
                           "ggf. kostenpflichtig — Apple/Google nativ bleibt 0-€-Vorzug."}

    def list_samples(self, since: str = "", until: str = "") -> list[HealthSample]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                f"{self.name} nicht verbunden — API-Key fehlt im Token-Tresor "
                f"(erwarteter Name: {self.token_name!r}).")
        raise QuelleNichtVerbunden(
            "Unified-API-Live-Abruf ist in v1 noch nicht freigeschaltet "
            "(Adapter-Gerüst steht; Aktivierung = Tresor-Key + Freigabe).")


# ── Gerätelokale Plattform-Quellen (Apple/Google) — via Mobile-Brücke ─────────
class _MobilePlatformSource(HealthSource):
    """Gemeinsame Basis für gerätelokale Plattform-Quellen (HealthKit/Health
    Connect). Beide haben KEIN Cloud-Backend-API: eine native Mobile-App liest mit
    Einwilligung und schickt Proben an diesen Dienst. v1 ⇒ keine Brücke ⇒ dormant.
    """

    plattform = "mobile"

    def __init__(self, bridge_verbunden: Callable[[], bool] | None = None) -> None:
        # Die Mobile-Schale meldet ihre Verbindung; v1 gibt es sie nicht ⇒ False.
        self._bridge = bridge_verbunden or (lambda: False)

    def verfuegbar(self) -> bool:
        try:
            return bool(self._bridge())
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "hinweis": f"{self.name}: gerätelokal (kein Cloud-API) ⇒ braucht die "
                           "native Mobile-Schale (Tauri), die mit Einwilligung liest "
                           "und Proben an POST /api/samples/ingest schickt (Slot). "
                           "v1 ist Desktop-first ⇒ dormant."}

    def list_samples(self, since: str = "", until: str = "") -> list[HealthSample]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                f"{self.name} nicht verbunden — Mobile-Brücke fehlt (Desktop-first v1).")
        raise QuelleNichtVerbunden(
            f"{self.name}-Live-Abruf läuft über die Mobile-Schale (Push), nicht über "
            "Pull — der Ingest-Endpunkt ist in v1 noch nicht offen.")


class AppleHealthSource(_MobilePlatformSource):
    """Apple HealthKit (iOS). Sehr breite Metriken inkl. Clinical Records (FHIR-nah).
    Gerätelokal ⇒ Mobile-Brücke nötig (s. Modul-Docstring)."""

    name = "apple_health"
    plattform = "ios"


class HealthConnectSource(_MobilePlatformSource):
    """Android Health Connect. Schritte/HF/Schlaf/Hauttemperatur + medizinische
    Daten als FHIR. Gerätelokal ⇒ Mobile-Brücke nötig."""

    name = "health_connect"
    plattform = "android"


# ── BLE/GATT-Slot — direkte Bluetooth-LE-Kopplung (geräte-ohne-Cloud) ─────────
class BLEHeartRateSource(HealthSource):
    """Direkter **BLE/GATT-Slot** für Geräte ohne Cloud (Brustgurt, BLE-Pulsuhr,
    -Waage, -Blutdruckmessgerät). Nutzt die Standard-GATT-Profile statt
    Hersteller-Clouds — desktop-tauglich, sobald ein BLE-Stack eingehängt wird.

    ── Standard-GATT-Profile (für die spätere Aktivierung dokumentiert) ───────
    - Heart Rate Service       0x180D  → Measurement-Characteristic 0x2A37
    - Battery Service          0x180F  → Battery Level 0x2A19
    - Health Thermometer       0x1809  → Temperature Measurement 0x2A1C
    - Weight Scale             0x181D  → Weight Measurement 0x2A9D
    - Blood Pressure           0x1810  → Blood Pressure Measurement 0x2A35
    - Glucose                  0x1808  → Glucose Measurement 0x2A18

    ── Aktivierung (Gesetz 5: vorbereitet, nicht aktiv) ──────────────────────
    Einen BLE-Stack einhängen (z. B. ``bleak`` — plattformübergreifend, async),
    Gerät scannen/verbinden, Notifications der Measurement-Characteristic
    abonnieren und die GATT-Frames auf ``HealthSample`` normieren (art=puls/
    gewicht/…). v1 hat keinen BLE-Stack ⇒ ``verfuegbar()`` False.
    """

    name = "ble"
    GATT = {
        "heart_rate": ("0x180D", "0x2A37", "puls"),
        "battery": ("0x180F", "0x2A19", None),
        "thermometer": ("0x1809", "0x2A1C", "koerpertemperatur"),
        "weight": ("0x181D", "0x2A9D", "gewicht"),
        "blood_pressure": ("0x1810", "0x2A35", "blutdruck_sys"),
        "glucose": ("0x1808", "0x2A18", "glukose"),
    }

    def __init__(self, ble_adapter: Any | None = None) -> None:
        # Erwartet später z. B. einen bleak-Client; v1 = None ⇒ dormant.
        self._ble = ble_adapter

    def verfuegbar(self) -> bool:
        return self._ble is not None

    def status(self) -> dict[str, Any]:
        stack = ble_stack_verfuegbar()
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "stack_installiert": stack, "aktivierbar": stack,
                "profile": {k: {"service": v[0], "characteristic": v[1], "art": v[2]}
                            for k, v in self.GATT.items()},
                "hinweis": ("BLE/GATT lokal scharf (bleak installiert): Geräte scannen und "
                            "Herzfrequenz/Temperatur/Gewicht/Blutdruck lesen über die Koppeln-"
                            "Schaltfläche — alles lokal. Glucose ist angebunden (Parser folgt)."
                            if stack else
                            "BLE/GATT-Slot für Geräte ohne Cloud. Aktivierung = pip install "
                            "bleak (Standard-GATT-Profile sind dokumentiert).")}

    def list_samples(self, since: str = "", until: str = "") -> list[HealthSample]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                "Kein BLE-Stack eingehängt — direkter Geräte-Empfang ist v1 vorbereitet, "
                "aber nicht scharf (siehe GATT-Profile in status()).")
        raise QuelleNichtVerbunden("BLE-Empfang ist in v1 noch nicht freigeschaltet.")


# ── Live-BLE (optionaler Stack `bleak`) — lokale Direktkopplung, 0 Cloud ───────
# HOCHSENSIBEL: BLE-Frames werden LOKAL auf HealthSample normiert und nur in die
# lokale DB ingestet — nichts verlässt das Gerät. `bleak` ist OPTIONAL: fehlt es,
# bleibt der Slot ehrlich dormant (ble_stack_verfuegbar() False). Scanner/Client sind
# injizierbar ⇒ Tests laufen ohne Hardware/Stack.
try:                                  # pragma: no cover - optionaler Stack
    import bleak as _bleak
except Exception:
    _bleak = None


def ble_stack_verfuegbar() -> bool:
    """True, sobald der optionale BLE-Stack (`bleak`) installiert ist."""
    return _bleak is not None


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gatt_uuid(short: str) -> str:
    """16-bit-GATT-Kurz-UUID (z. B. ``0x2A37``) → volle 128-bit-Bluetooth-Base-UUID."""
    s = short.lower().replace("0x", "").zfill(4)
    return f"0000{s}-0000-1000-8000-00805f9b34fb"


def parse_heart_rate(data: bytes) -> int | None:
    """Heart-Rate-Measurement (0x2A37): Flags(1B) + HR (uint8 ODER uint16, LE).
    Bluetooth-SIG-standardisiert ⇒ herstellerübergreifend identisch."""
    if not data:
        return None
    flags = data[0]
    if flags & 0x01:                  # Bit0=1 ⇒ 16-bit-Wert
        return int.from_bytes(data[1:3], "little") if len(data) >= 3 else None
    return data[1] if len(data) >= 2 else None


# IEEE-11073 Fließkomma (BLE-Standard für Mess-Frames). SFLOAT=16-bit (12-bit-Mantisse
# signiert + 4-bit-Exponent signiert), FLOAT=32-bit (24-bit-Mantisse + 8-bit-Exponent).
def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def _ieee11073_sfloat(raw: int) -> float | None:
    mantisse = _signed(raw & 0x0FFF, 12)
    if mantisse in (0x07FF, 0x0800, 0x07FE, 0x0802):   # NaN/NRes/±INF (nach Vorzeichen)
        return None
    exponent = _signed((raw >> 12) & 0x0F, 4)
    return mantisse * (10.0 ** exponent)


def _ieee11073_float(raw: int) -> float | None:
    mantisse = _signed(raw & 0x00FFFFFF, 24)
    exponent = _signed((raw >> 24) & 0xFF, 8)
    return mantisse * (10.0 ** exponent)


def parse_temperature(data: bytes) -> float | None:
    """Temperature Measurement (0x2A1C): Flags(1B) + Temp (FLOAT 32-bit LE). Flags Bit0=1
    ⇒ Fahrenheit (auf °C umgerechnet). Liefert °C, auf 0,1 gerundet."""
    if not data or len(data) < 5:
        return None
    val = _ieee11073_float(int.from_bytes(data[1:5], "little"))
    if val is None:
        return None
    if data[0] & 0x01:                # Fahrenheit ⇒ Celsius
        val = (val - 32.0) * 5.0 / 9.0
    return round(val, 1)


def parse_weight(data: bytes) -> float | None:
    """Weight Measurement (0x2A9D): Flags(1B) + Gewicht (uint16 LE). Flags Bit0=0 ⇒ SI
    (kg, Auflösung 0,005), Bit0=1 ⇒ Imperial (lb, 0,01 → in kg umgerechnet). Liefert kg."""
    if not data or len(data) < 3:
        return None
    roh = int.from_bytes(data[1:3], "little")
    if data[0] & 0x01:                # Imperial (lb) ⇒ kg
        return round(roh * 0.01 * 0.45359237, 2)
    return round(roh * 0.005, 2)      # SI (kg)


def parse_blood_pressure(data: bytes) -> float | None:
    """Blood Pressure Measurement (0x2A35): Flags(1B) + Systolisch/Diastolisch/MAP
    (je SFLOAT 16-bit). Liefert den SYSTOLISCHEN Wert (mmHg; Bit0=1 wäre kPa)."""
    if not data or len(data) < 3:
        return None
    val = _ieee11073_sfloat(int.from_bytes(data[1:3], "little"))
    return None if val is None else round(val, 0)


# Profil → Frame-Parser. heart_rate/thermometer/weight/blood_pressure sind v1 scharf;
# glucose ist angebunden (GATT dokumentiert), sein mehrteiliger Frame-Parser folgt.
_BLE_PARSER = {
    "heart_rate": parse_heart_rate,
    "thermometer": parse_temperature,
    "weight": parse_weight,
    "blood_pressure": parse_blood_pressure,
}


async def ble_scan(timeout: float = 5.0, scanner: Any | None = None) -> list[dict[str, Any]]:
    """Scannt nahe BLE-Geräte (lokal). ``scanner`` injizierbar (Test ohne Hardware)."""
    sc = scanner or (_bleak.BleakScanner if _bleak is not None else None)
    if sc is None:
        raise QuelleNichtVerbunden("BLE-Stack nicht installiert — `pip install bleak`.")
    devs = await sc.discover(timeout=timeout)
    out: list[dict[str, Any]] = []
    for d in devs or []:
        out.append({"address": getattr(d, "address", "") or "",
                    "name": (getattr(d, "name", None) or "(unbenannt)"),
                    "rssi": getattr(d, "rssi", None)})
    return out


async def ble_lesen(address: str, profil: str = "heart_rate", dauer: float = 8.0,
                    client_factory: Any | None = None,
                    sleep: Callable | None = None) -> list[HealthSample]:
    """Koppelt ein BLE-Gerät, abonniert die Measurement-Characteristic des GATT-
    ``profil`` und normiert die Frames LOKAL auf ``HealthSample`` (Bluetooth-SIG-
    Standardparser). v1 scharf: ``heart_rate`` · ``thermometer`` · ``weight`` ·
    ``blood_pressure``; ``glucose`` ist angebunden, sein mehrteiliger Parser folgt
    (ehrlich). ``client_factory``/``sleep`` injizierbar (Test ohne Hardware). Wirft
    ``QuelleNichtVerbunden`` bei fehlendem Stack/Profil/Parser."""
    factory = client_factory or (_bleak.BleakClient if _bleak is not None else None)
    if factory is None:
        raise QuelleNichtVerbunden("BLE-Stack nicht installiert — `pip install bleak`.")
    prof = BLEHeartRateSource.GATT.get(profil)
    if not prof:
        raise QuelleNichtVerbunden(f"Unbekanntes GATT-Profil: {profil!r}.")
    art = prof[2]
    if not art:
        raise QuelleNichtVerbunden(f"Profil {profil!r} liefert keinen Messwert (z. B. Battery).")
    parser = _BLE_PARSER.get(profil)
    if parser is None:
        raise QuelleNichtVerbunden(
            f"Frame-Parser für {profil!r} folgt — scharf sind {', '.join(sorted(_BLE_PARSER))}.")
    import asyncio as _asyncio
    _sleep = sleep or _asyncio.sleep
    char = _gatt_uuid(prof[1])
    proben: list[HealthSample] = []
    zaehler = [0]

    def _cb(_handle, data: bytearray):
        wert = parser(bytes(data))
        if wert is not None:
            zaehler[0] += 1
            proben.append(HealthSample(
                art=art, wert=float(wert), gemessen_am=_iso_now(), quelle="ble",
                geraet=str(address), extern_id=f"ble:{address}:{art}:{zaehler[0]:04d}"))

    client = factory(address)
    if hasattr(client, "__aenter__"):
        async with client as c:
            await c.start_notify(char, _cb)
            await _sleep(dauer)
            await c.stop_notify(char)
    else:                              # Test-Fakes ohne Async-Context-Manager
        await client.start_notify(char, _cb)
        await _sleep(dauer)
        await client.stop_notify(char)
    return proben


# ── Registry: welche Quellen kennt die App, welche sind verbunden? ────────────
def quellen_status(vault_get: Callable[[str], str | None] | None = None) -> list[dict[str, Any]]:
    """Übersicht aller bekannten/vorbereiteten Quellen + ihr Verbindungsstatus —
    für UI (Wearable-Panel) und MCP. Macht die vorbereiteten Anschlüsse SICHTBAR
    (Gesetz 5: Bewusstsein über ihr Vorhandensein), ohne sie scharf zu schalten."""
    quellen: list[HealthSource] = [
        ManualSource(),
        AppleHealthSource(),
        HealthConnectSource(),
        UnifiedApiSource(vault_get=vault_get),
        BLEHeartRateSource(),
    ]
    out = []
    for q in quellen:
        s = q.status()
        s.setdefault("name", q.name)
        out.append(s)
    return out
