# Recherche-Dossier — Dizz Healthy (Gesundheit)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> Zweck: Konnektoren, Standards und **jetzt vorzusehende** Verbindungs-Vorbereitungen (u. a. Smartwatch).
> HOCHSENSIBLE App → lokal-first, strikt.

## 1. Feature-Baseline (Marktstandard)
Aktivität/Schritte, Herzfrequenz/HRV, Schlaf, Workouts, Körpermaße/Gewicht, Ernährung, Achtsamkeit,
Zyklus, Blutdruck/Glukose; Medikamente & Erinnerungen; Labor-/Befund-Ablage; Trends + Tages-/
Wochen-Reports. Optional Verknüpfung mit Bürokratie (Arzttermine) und Plans (Routinen).

## 2. Standard-Datenquellen & Konnektoren
**Kernproblem:** Wearable-Daten sind fragmentiert. Zwei Wege:
- **Plattform-nativ (lokal, kostenlos):**
  - **Apple HealthKit (iOS):** **lokal-only, kein Backend-API** — eine native iOS-App liest mit
    Einwilligung und schickt selbst an den eigenen Dienst. Sehr breite Metriken inkl. Clinical Records
    (FHIR-nah).
  - **Google Health Connect (Android):** nativer Android-SDK (gleiches Modell wie HealthKit); Schritte,
    HF, Schlaf, Hauttemperatur, Routen, Achtsamkeit, **medizinische Daten als FHIR**.
- **Unified-Wearable-API (1 Integration für ~alle Geräte, kostenpflichtig):** **Terra** (500+ Geräte:
  Garmin, Oura, Fitbit, Apple, Google, Polar, Samsung, Whoop, Strava), **Spike** (300–500+ Geräte),
  **Vital**. Standardisiertes Datenmodell → spart das Pflegen vieler Einzel-SDKs.
- **Hersteller-direkt:** Fitbit-, Garmin-Health-, Oura-, Whoop-APIs (mehr Aufwand, volle Tiefe).
- **Interoperabilitäts-Standard:** **HL7 FHIR** (Apple Clinical Records & Google richten sich danach)
  → als internes Datenmodell für medizinische Records anstreben.

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **`HealthSource`-Adapter-Interface** mit geplanten Implementierungen: `AppleHealthSource`,
  `HealthConnectSource`, `UnifiedApiSource` (Terra/Spike), `ManualSource` (v1). **Smartwatch-Anbindung
  ist damit ein Stecker, kein Umbau.**
- **Wearable-Bridge / BLE-Slot** dokumentiert: spätere direkte **Bluetooth-LE**-Kopplung (Standard-
  GATT-Profile: Heart Rate, Battery) für Geräte ohne Cloud — als Vorbereitung beschrieben.
- **FHIR-konformes Datenschema** für medizinische Records (Befunde/Labor) von Anfang an.
- **Mobile-Brücke**: HealthKit/Health Connect brauchen eine native App → andockt an die später geplante
  **Tauri-Mobile-Schale** (Rust noch offen) — als Abhängigkeit notiert.

## 4. App-eigener KI-Wächter-Kern
Beobachtet/lernt: Schlaf-/HRV-Trends, Belastung vs. Erholung, Auffälligkeiten (Ruhepuls steigt),
Ziel-Fortschritt, Medikamenten-Adhärenz. **Nur beobachten + vorschlagen, KEINE Diagnose** — klarer
Disclaimer; sensible Auswertung ausschließlich lokal.

## 5. Sensible Daten & Sicherheit (lokal-first, strikt)
Gesundheitsdaten = höchste Sensibilität → **immer lokal**, **nie** Boost-/Cloud-Modell, Zugriff nur bei
**verifizierter Verbindung**. Verschlüsselung at-rest empfohlen. Datenexport/-löschung (DSGVO) als
Erstklasse-Funktion. Kein Teilen mit anderen Apps ohne explizite Freigabe.

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **FHIR** als internes Modell für klinische Daten; einheitliche Einheiten/Quantitäten (kein Wildwuchs).
- **Ein** `HealthSource`-Interface statt verstreuter SDK-Aufrufe; Unified-API nur falls Mehrkosten den
  0-€-Anspruch wert sind (sonst Apple/Google nativ + manuell).
- user-scoped + sync-ready; Zeitreihen sauber (UTC, Gerät als Quelle, Dedup über Geräte hinweg).

## 7. Entscheidungsfragen
**✅ ENTSCHIEDEN (Fragerunde 3, 11.06.):** v1 = KI-Interaktion + manuelle Dateneingabe (Supplements/
Verletzungen/Trainingsergebnisse/Gewicht/…) + KI-Auswertung. Wearable/Smartwatch wird **umfangreich
VORBEREITET** (HealthSource-Adapter, BLE-Slot, FHIR-Schema, Mobile-Brücke), aber in v1 nicht gebaut.
Lokal-first/0-€ gilt → native Apple/Google bevorzugt, Terra/Spike nur opt-in.

**Offen (Detail):**
1. Welche Geräte besitzt du konkret (Apple Watch / Garmin / Fitbit / Oura …)? → bestimmt späteren Adapter.
3. **Medizinische Records (FHIR)** schon in v1 vorsehen oder erst später?
4. Reicht **Desktop-first** (Dizzi läuft am PC), oder ist die Mobile-Schale für Health Voraussetzung
   (weil HealthKit/Health Connect mobil sind)?

## Quellen
- [Apple Health / Android Health Connect — Integrationsmodelle](https://mindsea.com/blog/apple-health-android-health-connect-integration-platforms-for-health-wellness-and-fitness/)
- [Was man mit HealthKit-Daten (nicht) tun kann](https://www.themomentum.ai/blog/what-you-can-and-cant-do-with-apple-healthkit-data)
- [Wearable-SDKs: Apple vs. Google vs. Fitbit vs. Garmin](https://www.mindbowser.com/wearable-device-sdks-comparison/)
- [Terra API — 500+ Wearables](https://tryterra.co/) · [Spike Health API](https://www.spikeapi.com/)
