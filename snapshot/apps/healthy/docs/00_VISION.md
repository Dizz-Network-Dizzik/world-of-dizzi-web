# Vision — Dizz Healthy — Health

Gesundheits-Watching: Vitalwerte, Gewohnheiten, Termine — der Gesundheits-Überblick.

**Datenschutz:** SENSIBLE App — Daten bleiben standardmäßig lokal, Zugriff nur bei verifizierter Verbindung.

## v1-Scope (entschieden Fragerunde 3, 11.06.)
- **KI-Interaktion + manuelle Dateneingabe**: Supplements, Verletzungen, Trainingsergebnisse, Gewicht,
  Schlaf, Ernährung u. Ä. — vom Nutzer eingegeben, **von der app-eigenen KI ausgewertet** (Trends,
  Belastung/Erholung, Hinweise — nur beobachten/vorschlagen, KEINE Diagnose).
- **Smartwatch/Wearable-Anbindung wird UMFANGREICH VORBEREITET** (Gesetz 5), aber in v1 nicht gebaut:
  `HealthSource`-Adapter-Interface, BLE-/GATT-Slot, FHIR-Datenschema, Mobile-Brücke (Tauri) als
  dokumentierte Andockpunkte. Details: [docs/RECHERCHE.md](RECHERCHE.md).

## Was die App leisten soll
- Vitalwerte/Gewohnheiten erfassen und auswerten (v1: manuell + KI-Auswertung)
- Termine/Erinnerungen (Arzt, Vorsorge)
- Trends + Dizzi-Beobachtung/Hinweise
- Gesundheitsdaten = HOCHSENSIBEL → strikt lokal
- *(vorbereitet)* Wearable/Smartwatch-Quellen via `HealthSource`-Adapter (HealthKit/Health Connect/
  Terra·Spike/BLE) — spätere Stufe

## Eigenständig + vernetzt
Diese App läuft eigenständig (eigenes Konto + Einstellungen, eigener Login als Rückfall) und ist
einzeln verkaufbar. Im Verbund meldet sie sich per Dizzi-ID an (Single-Sign-On), erscheint als
Panel in Dizzis Dashboard und ist über ihren MCP-Server für Dizzis KI ansprechbar.
