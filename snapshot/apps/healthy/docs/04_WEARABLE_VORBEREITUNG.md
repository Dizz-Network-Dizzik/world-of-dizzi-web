# Wearable-/Mobile-Vorbereitung — Dizz Healthy (Gesetz 5)

> **★ AKTUALISIERUNG 26.06.2026 — TEILWEISE SCHARF GESCHALTET (Nutzer-Auftrag):**
> - **BLE/GATT lokal SCHARF** über den optionalen Stack `bleak` (`pip install bleak`):
>   `sources.ble_scan()` (Geräte scannen) + `sources.ble_lesen()` (koppeln, Notify, Frames
>   → `HealthSample`). v1 scharf = **Herzfrequenz · Temperatur · Gewicht · Blutdruck** (GATT
>   0x2A37/0x2A1C/0x2A9D/0x2A35, Bluetooth-SIG-Standardparser inkl. IEEE-11073 SFLOAT/FLOAT);
>   **Glucose** (0x2A18) ist angebunden, sein mehrteiliger Frame-Parser folgt (ehrlich).
>   Endpunkte `GET /api/ble/scan` · `POST /api/ble/lesen`. Fehlt `bleak` ⇒ Slot bleibt
>   **ehrlich dormant** (`ble_stack_verfuegbar()` False). Alles strikt lokal, 0 Cloud.
> - **Ingest-Slot OFFEN:** `POST /api/samples/ingest` (auth-gegatet) nimmt normierte FHIR-nahe
>   Proben — der **Andockpunkt für die Mobile-Brücke** (Apple Health/Health Connect über die
>   künftige Handy-Schale; die Handy-App selbst bleibt eigene Baustelle). Dedupe über
>   `(user, quelle, extern_id)`; gemeinsame Normierung `domain._ingest_samples`.
> - **Terra/UnifiedApi bleibt bewusst DORMANT** — Cloud-Routing ist unvereinbar mit
>   `sensitivity=hoechst`/`lokal_only`. Apple/HealthConnect-PULL bleibt dormant (gerätelokal
>   ⇒ Mobile-Brücke), kommt über den Ingest-PUSH-Slot.
>
> Der Rest dieses Dokuments beschreibt die ursprüngliche Vorbereitung (weiter gültig).

> **Stand 15.06.2026.** Dies ist die **Bewusstseins-Doku** zu allen Anschlüssen, die v1
> VORBEREITET, aber bewusst NICHT scharf geschaltet hat (Gesetz 5: „Vorinstallierte
> Anschlüsse für spätere Eventualitäten werden im Code UND in der Systemübersicht
> gründlich erklärt — Bewusstsein über deren Vorhandensein muss herrschen, auch wenn
> sie noch keinen Nutzen haben.").
>
> Kurzfassung: **v1 ist Desktop-first + manuelle Eingabe.** Smartwatch/Wearable ist so
> weit vorbereitet, dass die spätere Anbindung ein **Stecker** ist, kein Umbau. Code:
> [`healthapp/sources.py`](../healthapp/sources.py) + [`healthapp/fhir.py`](../healthapp/fhir.py).
> Recherche-Grundlage: [`docs/RECHERCHE.md`](RECHERCHE.md).

---

## 1. Das Prinzip: EIN Interface statt verstreuter SDK-Aufrufe

Wearable-Daten sind fragmentiert (jedes Gerät/jede Plattform eigener Weg). Die App
spricht deshalb **nie** direkt mit einem Gerät, sondern gegen **ein** Interface
`HealthSource` (`sources.py`). Jeder Adapter normiert seine Rohdaten auf das
einheitliche Austauschformat **`HealthSample`** (FHIR-Observation-nah). Ab da ist die
Herkunft (Apple/Garmin/BLE/manuell) für die Domäne unsichtbar — sie ruft immer
`list_samples()` und dedupt über `extern_id`.

```
   Apple HealthKit ─┐
   Health Connect ──┤
   Terra/Spike ─────┼──►  HealthSource.list_samples()  ──►  HealthSample  ──►  Domäne (messwerte)
   BLE/GATT ────────┤        (ein Vertrag)                  (FHIR-nah)         quelle/extern_id/etag
   Manuell (v1) ────┘
```

**Sync-ready im Datenmodell schon da** (`domain.SCHEMA`, Tabelle `messwerte`):
`quelle` (Herkunft) · `extern_id` (stabiler Fremd-Schlüssel = Dedupe + Zwei-Wege-Sync)
· `etag` (Versionsmarke/Last-Modified = Konfliktauflösung). v1 füllt `quelle='manuell'`.

---

## 2. Die vorbereiteten Adapter (alle v1 DORMANT, ehrlich „nicht verbunden")

| Adapter | Klasse | Status v1 | Aktivierung |
|---|---|---|---|
| **Manuell** | `ManualSource` | **ECHT** | immer verfügbar (Eingabe über Router; Stapel-Import CSV/JSON läuft später über denselben Pfad) |
| **Apple HealthKit** | `AppleHealthSource` | dormant | Mobile-Brücke (kein Cloud-API, s. §4) |
| **Android Health Connect** | `HealthConnectSource` | dormant | Mobile-Brücke (kein Cloud-API, s. §4) |
| **Unified (Terra/Spike/Vital)** | `UnifiedApiSource` | dormant | API-Key im **Token-Tresor** (`appkit/vault.py`); opt-in, ggf. kostenpflichtig |
| **BLE/GATT direkt** | `BLEHeartRateSource` | dormant | BLE-Stack (z. B. `bleak`) einhängen (s. §3) |

`GET /api/quellen` macht diese Liste **live sichtbar** (UI-Panel „Wearable-Quellen" +
MCP) — Bewusstsein über die Anschlüsse, ohne dass v1 sie scharf schaltet. Jeder
dormante Adapter wirft bei `list_samples()` ein ehrliches `QuelleNichtVerbunden`
statt zu raten.

**Reihenfolge-Empfehlung (0-€-Prämisse, docs/RECHERCHE §6):** zuerst Apple/Google
nativ (gerätelokal, kostenlos) + BLE (Geräte ohne Cloud); Terra/Spike nur, wenn der
Komfort (500+ Geräte über EINE Integration) die Mehrkosten wert ist.

---

## 3. BLE/GATT-Slot (Geräte ohne Cloud)

Direkte Bluetooth-LE-Kopplung für Brustgurte, BLE-Pulsuhren, -Waagen,
-Blutdruck-/Glukosemessgeräte — über die **Standard-GATT-Profile** statt
Hersteller-Clouds. Desktop-tauglich, sobald ein BLE-Stack eingehängt wird.

Dokumentierte Standard-Profile (`BLEHeartRateSource.GATT`, in `status()` live abrufbar):

| Profil | Service-UUID | Measurement-Characteristic | → Messwert-Art |
|---|---|---|---|
| Heart Rate | `0x180D` | `0x2A37` | `puls` |
| Battery | `0x180F` | `0x2A19` | — |
| Health Thermometer | `0x1809` | `0x2A1C` | `koerpertemperatur` |
| Weight Scale | `0x181D` | `0x2A9D` | `gewicht` |
| Blood Pressure | `0x1810` | `0x2A35` | `blutdruck_sys` |
| Glucose | `0x1808` | `0x2A18` | `glukose` |

**Aktivierung:** `bleak` (plattformübergreifend, async) als optionale Abhängigkeit
ergänzen → Gerät scannen/verbinden → Notifications der Measurement-Characteristic
abonnieren → GATT-Frames auf `HealthSample` normieren. v1 hat keinen Stack ⇒
`verfuegbar()` ist `False`.

---

## 4. FHIR-Datenschema (medizinische Interoperabilität)

Apple Clinical Records und Google Health Connect liefern medizinische Daten als
**HL7 FHIR**. Wer von Anfang an FHIR-nah modelliert, zieht später Wearable-/Klinik-
Daten **ohne Schema-Umbau** ein. Umsetzung: [`healthapp/fhir.py`](../healthapp/fhir.py).

- **`MESSWERT_ARTEN`** — kanonischer Katalog: jede Vital-/Körpergröße mit
  **LOINC-Code** (FHIR `Observation.code`), **UCUM-Einheit** (FHIR `valueQuantity`)
  und einem **orientierenden** Referenzbereich (NUR sanfte Einordnung, keine Diagnose).
- **`to_fhir_observation(...)`** — baut aus einem Messwert eine FHIR-R4-`Observation`
  (Profil `vital-signs`). v1 nutzt das für Export/Doku (`GET /api/messwerte/{id}/fhir`);
  die spätere Wearable-/Klinik-Anbindung spricht dasselbe Format (kein Mapping-Wildwuchs).

FHIR ist bewusst die **Austauschsicht**, nicht der Speicher — die App speichert intern
schlank (`messwerte`: art/wert/einheit/…), damit v1 einfach bleibt und der Anschluss
trotzdem bereit ist.

---

## 5. Mobile-Brücke (Abhängigkeit, dokumentiert)

HealthKit/Health Connect sind **gerätelokal** (kein Cloud-Backend-API): es braucht
eine native App, die mit Einwilligung liest und Proben an diesen Dienst schickt.

- **Geplant:** die **Tauri-2-Mobile-Schale** des Netzwerks (Rust-Kern noch offen,
  netzwerkweite Abhängigkeit — siehe `the world of dizzi` Mobile-Schalen-Plan).
- **Andockpunkt (Slot, v1 NICHT offen):** `POST /api/samples/ingest` — die Schale
  POSTet normierte `HealthSample`-Proben hinter **verifizierter Verbindung**
  (hochsensibel). Implementierung = spätere Stufe; das Datenmodell (`messwerte` mit
  `quelle/extern_id/etag`) und der Dedupe-Pfad sind bereits dafür ausgelegt.
- **Bis dahin:** Health ist **Desktop-first** (Nutzer-Entscheid Fragerunde 3) —
  manuelle Eingabe am PC; die Geräteanbindung kommt mit der Schale.

---

## 6. Sicherheit (gilt für JEDE künftige Quelle)

Gesundheitsdaten = **höchste Sensibilität** (Manifest `sensitivity='hoechst'`):
- KI strikt **lokal** (`ki_routing=lokal_only`) — Inhalte NIE an Boost-/Cloud-Modelle.
- Externe Quellen-Tokens **nur** im verschlüsselten Token-Tresor (`appkit/vault.py`),
  nie in `app_settings`.
- Sensible Aktionen (Ingest, Live-Abruf) **nur bei verifizierter Verbindung**.
- Datenexport/-löschung (DSGVO) ist Erstklasse-Funktion (appkit-Vertrag 1.3,
  Re-Auth-pflichtig).

---

## 7. Was zu tun ist, um eine Quelle scharf zu schalten (Checkliste)

1. Adapter in `sources.py` implementieren (`verfuegbar()` + `list_samples()` → `HealthSample`).
2. Ggf. Abhängigkeit ergänzen (`bleak` für BLE; Anbieter-SDK/HTTP für Terra).
3. Token/Consent in den Token-Tresor (nie in Settings).
4. Ingest-/Sync-Pfad: Dedupe über `(quelle, extern_id)`, `etag` für Konfliktauflösung
   (Muster: der idempotente iCal-Import in Dizz Plans, `plansapp/domain.py`).
5. Sensible Routen mit `Depends(require_level("verifiziert"))` schützen.
6. `GET /api/quellen` zeigt den neuen Status automatisch (Registry in `quellen_status`).
