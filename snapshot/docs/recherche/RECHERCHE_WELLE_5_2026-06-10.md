# Recherche-Protokoll — Welle 5 (10.06.2026)

> Themen: KI-Websuche, Handy→PC-Fernzugriff, Speicher-/Kompressionsstrategie,
> Tauri+Python-Bündelung. Je Thema eine KLARE Empfehlung (Nutzer-Vollmacht).

## 5.1 Websuche-Backend für die KI → **SearXNG** ✅
- Open Source (15k+ Stars), self-hosted Metasuche über 70+ Quellen (Google, Bing, DDG, …),
  **JSON-API**, kein Tracking, unbegrenzte Queries (eigene Infrastruktur).
- Direkt unterstützt von Ollama/Open WebUI, LangChain, LiteLLM — Standard im Self-hosted-Feld.
- Läuft als kleiner lokaler Dienst (Docker oder nativ Python); Linux-portabel.
- **Entscheidung: SearXNG lokal als Such-Backend der KI.** Keine ernsthafte Alternative
  in der 0-€-Klasse (Brave-API = limitiert/kommerziell).

## 5.2 Handy→Heim-PC vor der Server-Stufe → **Tailscale** ✅
- WireGuard-basiertes Mesh-VPN; Geräte sehen sich wie im LAN, **ohne Portfreigaben,
  ohne feste IP, funktioniert auch hinter CGNAT** (Mobilfunk/Glasfaser-Realität).
- Free-Tier deckt Heimgebrauch zu 100 % ab; Apps für iOS+Android; bei Bedarf später
  self-hosted Control-Plane via **Headscale** (Open Source) → bleibt 0-€- und
  Auslagerungs-kompatibel.
- Rohes WireGuard = schneller eingerichtet NUR mit fester IP + Portforwarding; bei CGNAT
  schlicht nicht möglich. **Entscheidung: Tailscale (Headscale-Option dokumentiert).**
- Konsequenz für Architektur: Core bindet an localhost + Tailscale-Interface; KEINE
  Port-Öffnung ins offene Internet vor Auth-Vollausbau.

## 5.3 „Intelligentes Speichersystem" → **hierarchische Verdichtung** ✅
State of the Art 2026 (deckt sich mit Mem0/Zep-Praxis):
- **Lebenszyklus-Prinzip**: Rohdaten (kurzfristig, voll) → periodische Verdichtung →
  kompakte Langzeit-Essenz. Junge Einträge wörtlich, alte zunehmend zusammengefasst
  („progressive summarization").
- Techniken: hierarchische Zusammenfassung, selektives Behalten (Relevanz-Score),
  Dedup über Embeddings, periodische Konsolidierung (z. B. nächtlicher „Schlaf-Job"
  der KI: Tages-Episoden verdichten, Widersprüche auflösen).
- Ehrliche Warnung aus den Quellen: das MANAGEMENT (Pruning/Konsolidierung) ist der
  schwere Teil — schlecht gemacht entsteht Rausch + Widerspruch. Darum: Konsolidierung
  als eigener, getesteter Core-Job, nicht als Nebenbei-Feature.
- **Entscheidung: 3-Stufen-Lebenszyklus (roh → verdichtet → Essenz) + nächtlicher
  Konsolidierungs-Job, ab KI-Kern v1 (Phase 2).**

## 5.4 Bündelung Tauri + Python-Core → **Sidecar-Pattern** ✅ (für SPÄTER, dokumentiert)
- Erprobtes Muster: PyInstaller packt FastAPI-Core in eine EXE, Tauri bündelt sie als
  „Sidecar" und startet/stoppt sie automatisch; Frontend spricht HTTP. Mehrere
  Produktions-Templates vorhanden (auch Tauri v2 + React + FastAPI).
- **Für UNS in Stufe 1: Entwicklung läuft mit getrenntem Core-Prozess** (wie Trading Bot,
  :Port lokal). Sidecar-Bündelung wird erst relevant, wenn das Produkt an Dritte geht
  (Ein-Klick-Installer) → vorbereiteter Anschluss, dokumentiert in Systemübersicht §4.

## Werkzeug-Inventur des Rechners (10.06.2026)
| Werkzeug | Status |
|---|---|
| git 2.54 | ✅ da |
| Python 3.12.10 | ✅ da |
| Node.js / npm / pnpm | ❌ fehlt (für React/Vite/Tauri nötig) |
| Rust (rustc/cargo) | ❌ fehlt (für Tauri-Schale nötig; + MSVC Build Tools) |
| Ollama | ❌ fehlt (für lokales LLM, Phase 2) |
→ Eingeplant als Teil A des Phase-1-Pakets (wenige UAC-Bestätigungen durch Nutzer nötig).

## Quellen
- SearXNG — https://searxng.org/ · https://docs.litellm.ai/docs/search/searxng · https://railway.com/deploy/searxng-search-api
- Tailscale vs WireGuard — https://tailscale.com/compare/wireguard · https://homelabstarter.com/tailscale-vs-wireguard-comparison/ · https://wiredhaus.com/wireguard-vs-tailscale-home-vpn-2026/
- Memory-Kompression — https://atlan.com/know/context-compression/ · https://engineersofai.com/docs/agentic-ai/agent-memory/memory-compression-and-summarization · https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/
- Tauri-Sidecar — https://v2.tauri.app/develop/sidecar/ · https://github.com/dieharders/example-tauri-v2-python-server-sidecar · https://aiechoes.substack.com/p/building-production-ready-desktop
