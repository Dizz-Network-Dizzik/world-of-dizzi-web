# 📚 docs/ — netzweite Normen & Specs (Index)

> Alles hier gilt **netzweit** (alle Apps). App-eigene Doku liegt unter `apps/<id>/docs/`.
> Die visuelle Gesamtsicht ist [`_netzwerk/SYSTEM_KARTE.html`](../_netzwerk/SYSTEM_KARTE.html)
> — im Browser öffnen, self-contained, keine externen Aufrufe.

## Fundament — zuerst lesen

| Dokument | Inhalt |
|---|---|
| [00_VISION_UND_ANFORDERUNGEN](00_VISION_UND_ANFORDERUNGEN.md) | Warum es das Netzwerk gibt: Vision, Anforderungen, Leitplanken |
| [01_GRUNDGESETZE](01_GRUNDGESETZE.md) | Die verbindlichen Arbeitsregeln — Ehrlichkeit, Sorgfalt, Reihenfolge |
| [03_SYSTEMUEBERSICHT](03_SYSTEMUEBERSICHT.md) | Die Schichten in einem Bild: Shell · Core · Apps · Daten |
| [11_GESAMTPLAN](11_GESAMTPLAN.md) | Der große Plan: Phasen, Ausbaustufen, Entscheidungen |
| [12_GESAMTVERSTAENDNIS](12_GESAMTVERSTAENDNIS.md) | Einstieg ohne Vorwissen — was hier gebaut wird und wie es zusammenhängt |
| [13_APP_GRUNDLAGEN](13_APP_GRUNDLAGEN.md) | Konzept & Anforderungen je Einzel-App |

## Architektur & Verträge

| Dokument | Inhalt |
|---|---|
| [16_APP_VERTRAG_SPEC](16_APP_VERTRAG_SPEC.md) | **Die Norm:** wie eine App ans Gesamtsystem andockt (Kernpaket K3) |
| [17_DIZZI_ID_K1](17_DIZZI_ID_K1.md) | Dizzi-ID — Identitäts-Dienst, Single-Sign-On über alle Apps |
| [26_QUERVERBINDUNGEN](26_QUERVERBINDUNGEN.md) | Übergabe-Verträge zwischen den Apps (V2–V16) |
| [34_A5_BEREICHS_QUERVERBINDUNGEN](34_A5_BEREICHS_QUERVERBINDUNGEN.md) | Bereichs-Querverbindungen V17–V19 |
| [31_MCP_GATEWAY](31_MCP_GATEWAY.md) | Remote-MCP-Gateway — eine Verbindung zu allen App-Werkzeugen |
| [38_META_KONNEKTOR](38_META_KONNEKTOR.md) | Meta-Konnektor (WhatsApp/Instagram) — Spec + Onboarding |
| [15_KONNEKTOREN_MATRIX](15_KONNEKTOREN_MATRIX.md) | Konnektoren- & Integrations-Matrix über alle Apps |
| [35_KONNEKTIVITAET_VISION](35_KONNEKTIVITAET_VISION.md) | Konnektivität als Kernziel |
| [49_BEREICH_TYP_MODELL](49_BEREICH_TYP_MODELL.md) | Bereich-Typ-Modell (kanonisch, Heimat: Dizz Admin) |
| [62_RUNTIME_VERTRAG](62_RUNTIME_VERTRAG.md) | LocalRuntime — austauschbare lokale Modell-Laufzeit |
| [63_AGENTEN_REGIE_VERTRAG](63_AGENTEN_REGIE_VERTRAG.md) | Agenten-Regie: Autonomie-Treppe T0–T3, Not-Aus, HITL |
| [66_APP_EXPORT_VERTRAG](66_APP_EXPORT_VERTRAG.md) | Einzel-App als self-contained, verkäufliches Bündel |
| [67_BEREICH_KANON_VERTRAG](67_BEREICH_KANON_VERTRAG.md) | Bereichs-Kanon (BER-1/2/3 + ME-1) |
| [52_ZUKUNFTSARCHITEKTUR_ROADMAP](52_ZUKUNFTSARCHITEKTUR_ROADMAP.md) | Zukunftsarchitektur & Roadmap: Modell-Flexibilität, Deployment-Modi, App-Builder |

## Fach-Verträge (Domänen)

| Dokument | Inhalt |
|---|---|
| [64_BANK_SYNC_VERTRAG](64_BANK_SYNC_VERTRAG.md) | Bank-Sync über FinTS/HBCI — **nur lesend** |
| [65_ELSTER_TRANSPORT_VERTRAG](65_ELSTER_TRANSPORT_VERTRAG.md) | ELSTER/ERiC-Transport für Dizz Money |
| [68_USTVA_VERTRAG](68_USTVA_VERTRAG.md) | UStVA, §19-Kleinunternehmer, Vorsteuer |
| [80_CHRONIK_VERTRAG](80_CHRONIK_VERTRAG.md) | DzChronik — Chronik-Kern, Chronist, Prüfkern |
| [69_TRADING_AI_VALIDIERUNG](69_TRADING_AI_VALIDIERUNG.md) | Struktur-Validierung der Trading-KI (read-only Review) |

## Oberfläche & Design

| Dokument | Inhalt |
|---|---|
| [06_DESIGN_SYSTEM](06_DESIGN_SYSTEM.md) | Design-System „Mattglanz-Metall" — Farben, Kanten, Glühen |
| [14_SPIN_PHYSIK_SPEC](14_SPIN_PHYSIK_SPEC.md) | Spin-Physik: greifbare, schleuderbare Panels (kanonisch für alle Apps) |
| [19_SETTINGS_ACCOUNT_LEITFADEN](19_SETTINGS_ACCOUNT_LEITFADEN.md) | Einstellungs- & Account-Knopf — Fenster-Norm |
| [39_UI_KIT_VEREINHEITLICHUNG](39_UI_KIT_VEREINHEITLICHUNG.md) | UI-Kit-Vereinheitlichung + Panel-Bautool |
| [70_UX_KONSOLIDIERUNG_VERTRAG](70_UX_KONSOLIDIERUNG_VERTRAG.md) | UX-Konsolidierung — Design-System-Vertrag |
| [37_CSP_STRIKT_RECIPE](37_CSP_STRIKT_RECIPE.md) | CSP voll-strikt je App (Inline-Handler → Event-Delegation) |

## Sicherheit & Betrieb

| Dokument | Inhalt |
|---|---|
| [18_SICHERHEITSKONZEPT](18_SICHERHEITSKONZEPT.md) | Gesamtsystemisches Sicherheitskonzept |
| [32_KERN_DAUERSCHLEIFE](32_KERN_DAUERSCHLEIFE.md) | Die Kern-Dauerschleife: Durchleuchten, Funktions-Beweis, Verbesserungs-Recherche |

## Recherche-Protokolle

| Dokument | Inhalt |
|---|---|
| [recherche/RECHERCHE_WELLE_1-3](recherche/RECHERCHE_WELLE_1-3_2026-06-10.md) | Recherche-Protokoll Wellen 1–3 |
| [recherche/RECHERCHE_WELLE_5](recherche/RECHERCHE_WELLE_5_2026-06-10.md) | Recherche-Protokoll Welle 5 |

---

*Kuratierter öffentlicher Auszug der Netz-Doku — einzelne Dokumente sind bewusst nicht enthalten.*
