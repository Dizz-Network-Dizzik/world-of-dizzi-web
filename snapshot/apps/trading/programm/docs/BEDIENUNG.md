# Kurzanleitung: Bots im Demo-/Paper-Modus bedienen

> **Paper-Modus = Spielgeld auf echten Live-Kursen.** Es wird **kein echtes Geld** bewegt — alle Bots
> laufen `dry_run`. Erkennbar oben im Dashboard am Badge **„PAPER (dry-run)"**. Echtgeld ist ein
> separates, gesichertes Gate (`RUNBOOK_ECHTGELD.md`).

## 1. App starten
- Autostart-Task **`DizzTrading-Autostart`** (Login) startet Backend + Flotte automatisch, **oder**
- manuell:
  ```powershell
  cd "C:\Dizzik\code\dizz-network\apps\trading\programm"
  .\scripts\launch.ps1        # startet DizzTrading-Server.exe + Auto-Resume der Bots
  ```
- Dashboard: <http://127.0.0.1:8137> — oben sollte stehen: 🟢 Status ok · **PAPER (dry-run)** · Engine ✓.

> ⚠️ **Die laufende Flotte NIE eigenmächtig neu starten** (Geld-System). Restart/Bot-CRUD nur gegated
> (Nutzer-Go + Backup-first). Andere Chats arbeiten read-only.

## 2. Bot anlegen
1. Bereich **„Bots"** → Bot-Name eingeben → **Strategie** wählen (Markt Spot/Futures + Hebel + Timeframe
   werden aus der Strategie abgeleitet, im Anlage-Popup übersteuerbar).
2. Demokapital/Detailfelder im Popup bestätigen → Bot erscheint in der Liste (Status *created*).
   (Echtgeld-Anlage ist hart gegated: unvalidierte Strategie → HTTP 400.)

## 3. Bot starten / beobachten / stoppen
- **Start** → Status **🟢 läuft**; der Bot handelt mit Spielgeld auf Live-Bitget-Daten.
- **Logs** (Heartbeat/Signale/Trades) · **Stats** (Kennzahlen) · **Analyse** (Trade-Auswertung) ·
  **Equity** (ROI-Kurve mit High-Water + Underwater-Drawdown).
- **Stop** → sauberer Prozess-Kill (Status *stopped*).
- ⚠️ **„Kill" ist ein SOFT-Schalter** (nur Status + Audit, kein Prozess-Kill). Einen hängenden Bot
  heilt man mit **Stop → Start**, nicht mit Kill → Start.

## 4. Lernen & Optimieren (Lern-Tab)
- **Regime/Empfehlung:** aktuelles Markt-Regime (HMM) + empfohlene Strategien (empirisch → regelbasiert).
- **Optimierungs-Loop:** Strategie wählen → „Loop ausführen" (Anchored-Walk-Forward, `windows=2`) →
  Gewinner wird persistiert; „Gewinner anwenden" (Demo-Bot/-Flotte, mit Neustart) oder „↺ zurücksetzen".
- **Reife/Ranking:** Daten-Reife-Balken, Strategie-Ranking, „bereit 🚀"-Echtgeld-Reife je Demo-Bot
  (aktiviert sich mit wachsender Historie).
- **Markt-neutraler Sockel:** CSM/Pairs/StatArb/Market-Making-Panels (KPIs + Equity + „Lern-Loop
  optimieren"). Rein simuliert, 0 Risiko.

## 5. Risiko & Portfolio (automatisch)
- **Governor:** überwacht Gesamt-Drawdown/Tagesverlust/Anomalien → warnt bzw. de-riskt (schlechteste
  Demo-Bots pausieren). Echtgeld-Bots + MasterMeta sind geschützt.
- **Concentration:** meldet Klumpen (Asset-/Cluster-Exposure, HHI) als Frühwarnung + Streuungs-Hinweis.
- **Sizing:** empfiehlt Stakes (Vol-Targeting + optional Kelly-Tilt) — proposal-only; Anwenden nur per
  Aktion (Stake setzen + gegateter Neustart). FP-2-Klemmkette/Bridge: `KELLY_SIZING_SPEC.md`.

## Gut zu wissen
- **Konto/Wallet** zeigt echte Bitget-Salden (read-only) — im Paper-Modus **nicht** angefasst.
- Backend-Änderungen (`.py`) wirken erst nach `:8137`-Neustart; das Dashboard (`index.html`) wird pro
  Request frisch ausgeliefert → nur Seite neu laden.
- Laufende Paper-Bots laufen im Hintergrund weiter, bis sie gestoppt werden oder der PC neu startet
  (dann greift der Autostart-Task).
