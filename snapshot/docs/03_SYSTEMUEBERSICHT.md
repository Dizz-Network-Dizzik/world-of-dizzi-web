# Systemübersicht — the world of dizzi

> Lebendes Standard-Dokument (Grundgesetz: wird regelmäßig gepflegt).
> Stand 10.06.2026 (abends): **Phase 1 Teil B GEBAUT** (Commit `a626dec`) — Core v0 + Dashboard v0
> laufen (Browser, :8200, 15 pytest, Preview-verifiziert). Tauri-Schale (Teil C) offen
> (Rust-Toolchain fehlt noch). KI-Schicht/MCP-Hub weiterhin Soll (Phase 2/4).

## 1. Schichtenmodell

```
╔═══════════════════════════════════════════════════════════════╗
║ SCHALEN-SCHICHT                                               ║
║  Desktop (Tauri, Win→Linux/macOS) · Mobile (Tauri 2) · Browser║
║  Dashboard: Panel-Grid, Mattglanz-Metall, Cyan/Magenta        ║
╠═══════════════════════════════════════════════════════════════╣
║ CORE-SERVICE (FastAPI, headless, lokal→Server)                ║
║                                                               ║
║  ┌─────────────┐ ┌──────────────┐ ┌────────────────────────┐  ║
║  │ KI-ORCHESTR.│ │ PANEL-       │ │ SYSTEM-DIENSTE         │  ║
║  │ Agent-Loop  │ │ REGISTRY     │ │ Settings · Auth-Slot   │  ║
║  │ Memory 3-Lg.│ │ Manifeste    │ │ Audit-Log · Scheduler  │  ║
║  │ RAG-Pipeline│ │ Platzhalter  │ │ Backup-Hooks           │  ║
║  │ Websuche    │ │ Lifecycle    │ │                        │  ║
║  └──────┬──────┘ └──────┬───────┘ └────────────────────────┘  ║
║         └───────┬───────┘                                     ║
║           MCP-HUB (Tool-Bus: KI ↔ Panels ↔ extern ↔ KI-Client) ║
╠═══════════════════════════════════════════════════════════════╣
║ DATEN-SCHICHT: SQLite (+sqlite-vec) · user-scoped · sync-ready║
╠═══════════════════════════════════════════════════════════════╣
║ MODELL-SCHICHT (eine Provider-Abstraktion, OpenAI-API-kompat.)║
║  LOKAL: Ollama (RTX 5070 Ti) · faster-whisper · Piper         ║
║         · openWakeWord (zuschaltbar)                          ║
║  BOOST (0 €, opt-in je Aufgabe): NVIDIA NIM → Groq →          ║
║         Cerebras → Google AI Studio (Fallback-Kette)          ║
║  REGEL: sensible Domänen (Finanzen/Bürokratie/Gesundheit/     ║
║         Notizen) standardmäßig NUR lokal                      ║
╚═══════════════════════════════════════════════════════════════╝
```

**Externe-Dienste-Prinzip (Nutzer-Entscheid 10.06.):** Alle Fremd-Anbindungen (Gmail,
Kalender, KI-Dienste, Social-Media-APIs, …) werden nur als **deaktivierte Konnektoren
vorbereitet** (Settings-Eintrag + Anschluss-Stelle im Code, dokumentiert in §4) —
angebunden wird erst auf Zuruf des Nutzers.

## 2. Die KI (Herzstück) — geplante Lern-Ebenen

| Ebene | Inhalt | Mechanik |
|---|---|---|
| L1 Profil | Wer ist dizzi: Präferenzen, Stil, Routinen | Memory-Extraktion aus Interaktionen (Mem0-Pattern), explizites „merk dir" |
| L2 Episoden | Was ist passiert: Gespräche, Entscheidungen, Aufgaben | Zusammenfassung + Embedding, zeitlich abrufbar |
| L3 Wissen | Projekte, Dokumente, Ordnerinhalte | RAG-Index (sqlite-vec) über freigegebene Ordner |
| L4 Tool-Feedback | Wie laufen die Tools, was hat die KI bewirkt | strukturierte Stats/Events der Panels via MCP; Vorschlags-Loop |

Feedback-Schleife: jede KI-Aktion + Nutzerreaktion wird bewertet → fließt in L1/L4 zurück.

## 3. Panel-Vertrag (Plugin-System)

Jedes Panel liefert ein **Manifest**:
- `id`, `name`, `icon`, `status` (aktiv | platzhalter)
- `stats()` → Kern-Kennzahlen fürs Dashboard-Kachel
- `details()` → ausklappbare Detail-Ansicht
- `actions[]` → Interaktionen/Deep-Links in die jeweilige App
- `mcp` → MCP-Server-Endpoint des Panels (Fähigkeiten für die KI)

**Platzhalter-Panel** = Manifest ohne Implementierung (Kachel sichtbar, „in Planung").

### Dashboard-Anzeige-Schema (Nutzer-Entscheid 11.06.2026)
- Das Dashboard zeigt **immer nur die obersten zwei Panels in voller Detail-Ansicht**
  (aufgeklappte „App-Ansicht").
- **Alle übrigen Panels = kompakte Übersichts-Kacheln** (klein, in der Größe der jetzigen
  „in Planung"-Kacheln).
- Der Nutzer **schiebt per Drag** die zwei Panels nach oben, die er gerade ausführlich sehen
  will → Position bestimmt die Detailtiefe (Top-2 = Detail, Rest = kompakt). Reihenfolge wird
  weiterhin als Setting `panel_order` user-scoped gespeichert.

### Panel = eigenes Unterprojekt (Muster, bestätigt 11.06.)
Jedes größere Panel ist ein **eigenständiges Projekt mit eigenem Ordner** (wie der Trading Bot),
das Dizzi nur **anbindet/vernetzt** — nicht in sich selbst implementiert. Anbindungs-Vertrag:
1. eigener Projektordner/-repo,
2. **read-only Stats-Endpoint** für die Panel-Kachel (Muster Trading Bot `:8137/api/summary`),
3. später **MCP-Server** für die KI-Interaktion (Dizzi ↔ Panel-KI, siehe §3b),
4. **Deep-Link** zur eigenständigen App.
Health, Archiv, News werden so als **separate Projekte** geführt und einzeln integriert.

### Panel-Liste (Soll)
| Panel | Status-Plan |
|---|---|
| Systeminfo | ✅ **AKTIV** (Phase 1/3): Hardware-Live + ausgeklappte System-App-Ansicht |
| Trading Bot | ✅ **AKTIV** (Phase 3): read-only `:8137`, Kategorie-Breakdown, Durchsprung |
| Health | ↩ **zurück auf „in Planung"** — eigenes Projekt (Gesundheits-Watching), noch kein Inhalt. Die jetzige Dizzi-System-Status-Anzeige (Version/Uptime/DB/Audit) zieht als Vorschlag in die Systeminfo-App-Ansicht („Dizzi-Status"-Abschnitt) |
| Archiv (Archiv+Notizen+Memory) | **eigenes Projekt** (eigener Ordner), nutzt Dizzis L1/L2-Memory mit; integriert später |
| News Compact | **eigenes Projekt** (eigener Ordner), `/news`-Skill als Quelle/Vorbild; integriert später |
| Projektübersicht/-verwaltung | mittel (Phase 5) |
| Finanzmanagement | mittel (Phase 5) |
| Bürokratie | mittel (Phase 5) |
| Social Media | später (Phase 5+) |
| Creator (Bild/Video) | Platzhalter, bis Nutzer-Projekt existiert |

## 3b. Dizzi ↔ Panel-KIs — Interaktion & Feedback (Soll, Phase 4)
> Nutzer-Wunsch 11.06.: Dizzi soll **Rücksprache** mit den system-eigenen KIs der Panels halten
> (z. B. Trading-Bot **MasterMeta** + **Governor**), wissen, was dort abgeht, und aus
> **Beobachtungen Feedback/Verbesserungsvorschläge** ableiten.

**Mechanik (über den MCP-Tool-Bus):**
1. Jedes Unterprojekt exponiert einen **MCP-Server** mit Lese-Tools — beim Trading Bot z. B.
   `master_status` (Ensemble-Gewichte/Fitness), `governor_state` (De-Risk-Stufe, Konzentration),
   `regime` (HMM-Zustand+Konfidenz), `fleet_health`.
2. Dizzi ist **MCP-Host**: Fragt der Nutzer „wie läuft der Trading Bot?" oder beim periodischen
   Beobachtungs-Tick, ruft Dizzi diese Tools, liest die internen KI-Zustände und fasst zusammen.
3. **Beobachtungs-Gedächtnis (Memory-Ebene L4)**: Dizzi protokolliert die abgefragten Zustände
   über die Zeit → erkennt Trends („Trefferquote Scalping fällt seit 3 Tagen", „Governor drosselt
   gehäuft bei Regime X") und kann sie dir melden.
4. **Feedback — zwei sichere Wege** (nie direkter Eingriff ins Trading):
   - **An dich**: Dizzi formuliert eine Beobachtung/Empfehlung als Hinweis.
   - **An das Projekt**: als *Vorschlag* in dessen eigene Lern-/Proposal-Schleife (der Trading Bot
     hat bereits einen proposal-only Optimierer mit OOS-Validierungs-Gates) — die bestehenden
     Gates/der Nutzer entscheiden, Dizzi schlägt nur vor.
5. **Gegenrichtung**: Das Projekt kann Events an Dizzi pushen (z. B. „MasterMeta-Regimewechsel",
   „Governor hat de-risk ausgelöst") → Dizzi notiert/alarmiert.

**Sicherheit (Systemübersicht §5, „Human in the Loop"):** Dizzi **beobachtet und schlägt vor**,
führt aber **keine Trading-/Geld-Aktionen** selbst aus. Vorschläge laufen über dich oder die
projekteigenen Validierungs-Gates.

**Modell-Hinweis (Gesetz 10):** Dieser Cross-KI-Aufbau (MCP-Server im Trading Bot + Host-Loop +
L4-Beobachtung + Vorschlagslogik) ist **Architektur-KI-Arbeit** und gehört in **Phase 4** (MCP-Hub).
Der read-only Stats-Teil läuft bereits (Trading-Bot-Panel).

## 4. Vorinstallierte Anschlüsse ohne aktuellen Nutzen (Grundgesetz 5)
> Diese Liste MUSS aktuell gehalten werden — Bewusstsein über „tote" Vorbereitungen.

| Anschluss | Zweck | Status |
|---|---|---|
| `user_id` in jedem Datensatz | Multi-User/Server-Stufe 3 | geplant ab erstem Schema |
| Auth-Middleware-Slot in FastAPI | später Authentik/Keycloak/Tokens | geplant ab API v1 |
| Sync-Felder (UUID, updated_at, deleted_at) | CRDT-Sync Stufe 3 | geplant ab erstem Schema |
| MCP-Remote-Transport (Streamable HTTP) | Server-Stufe, externe Agents | nach lokalem stdio |
| i18n DE/EN im Frontend | Nutzer-Entscheid: zweisprachig vorbereitet, Inhalte erst Deutsch | ab UI-Gerüst |
| Konnektor-Slots externe Dienste (Gmail, Kalender, KI-Dienste, …) | vorbereitet-deaktiviert, Aktivierung auf Zuruf | ab Settings-Modul |
| Wake-Word-Modul (openWakeWord) | Einstellung „immer lauschen", Standard Push-to-talk | Phase 4 |
| Boost-Provider-Slots (NIM/Groq/Cerebras/…) | Gratis-API-Kette, per Settings + Routing-Regel | ab KI-Kern v1 |
| Mandanten-/Settings-Namespace | Verkauf an Dritte | ab Settings-Modul |

## 5. Sicherheitskonzept (Kurzfassung, Vollausbau Stufe 3)
- Lokal: Daten außerhalb OneDrive, restic-Backups verschlüsselt (AES-256), Secrets nie im Repo.
- API: auch lokal nur an localhost binden; CORS strikt; Audit-Log für KI-Aktionen.
- Server-Stufe: OIDC/Authentik-Klasse, MFA default-an, Passkeys, Refresh-Rotation,
  user-scoped Daten von Tag 1 (kein Nachrüst-Schmerz).
- KI-Sicherheit: Aktionen mit Außenwirkung (Mail senden, Geld, Löschen) brauchen Bestätigung
  („Human in the Loop"-Stufen pro Tool definierbar).

## 6. Projektstruktur (Soll, Phase 1)
```
the world of dizzi/
├── docs/                  # diese Doku + Recherche + Archiv/Bauplan
├── core/                  # FastAPI-Service (Python)
│   ├── app/               #   Module: ai/, panels/, mcp/, data/, system/
│   └── tests/
├── shell/                 # Tauri-App (Desktop→Mobile)
│   └── src/               #   TypeScript-Frontend
├── panels/                # Panel-Plugins (je eigener Ordner, Manifest)
└── ops/                   # Backup-Skripte (restic), Start-Skripte, später Deploy
```
