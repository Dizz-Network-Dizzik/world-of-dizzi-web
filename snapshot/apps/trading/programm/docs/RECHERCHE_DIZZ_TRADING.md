# Recherche-Dossier — Dizz Trading (Trading)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> **Architektur-Nachtrag 14.06.2026:** appkit 1.6.0 vendort · MCP-Tools `tradingbot_*` (Namensraum-Norm ✅) ·
> Defense-Middleware (`install_defense()`) noch offen · K2.2/K2.4-Retrofit nächster Schritt. Kein inhaltlicher Änderungsbedarf.
> Sonderfall: **bereits gebaute, weit fortgeschrittene App** (Demo-Flotte, KI-Ebenen MasterMeta/
> Governor/HMM, Portfolio-Schicht, :8137). Dieses Dossier dient der **Angleichung ans Gesamtschema**
> (Dizzi-ID, App-Vertrag) und der **Echtgeld-Reife** — nicht dem Neubau.

## 1. Feature-Baseline (Stand vs. Markt)
Vorhanden: Demo-Flotte (Freqtrade-Engines), Strategie-Katalog, anchored Walk-Forward, MasterMeta-
Ensemble, Governor/Konzentration/Sizing, HMM-Regime, Fundamental-Overlay, Stats + read-only MCP, UI mit
Spin-Physik. Markt-Standard für **Echtgeld**: harte Risiko-Limits, Notfall-Stop, API-Key-Hygiene,
Backtest/Sim vor Live, Audit. → Dizz Trading ist hier bereits führend; Lücke ist v. a. **Echtgeld-Gate +
Identitäts-/Konto-Angleichung**.

## 2. Standard-Datenquellen & Konnektoren
- **Börsen/Broker: CCXT** (100+ Exchanges, einheitliches Interface, Python) ist der De-facto-Standard;
  bereits genutzt (Bitget u. a.). Unified-Layer hält Anbieter austauschbar.
- **Marktdaten/Fundamental:** FRED (Makro, bereits angebunden), On-Chain (blockchain.com), DVOL (Deribit)
  — schon vorhanden.
- **Nach Dizzi:** read-only **MCP** (MasterMeta/Governor) ist bereits da → wird zum App-Vertrags-konformen
  Tool-Set verallgemeinert (K4). **Vermögens-Posten** fließt nach **Dizz Money**.

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen / angleichen)
- **Dizzi-ID als Relying Party** (K1): TB akzeptiert das SSO-Ticket; lokaler Login als Fallback.
- **Echtgeld-Gate an Dizzi-ID-Hochsicherheit koppeln** (K6): Live-Trading nur hinter **Passkey/MFA** +
  „verifizierte Verbindung".
- **Account/Settings-Modul (K2)** nachrüsten (Konto/Sicherheit/KI/Vernetzung/Darstellung/Daten).
- **App-Vertrag formal**: Stats + MCP hat er → ergänzen um Dizzi-ID, Settings-Modul, Deep-Link,
  Vernetzungs-Manifest.

## 4. App-eigener KI-Wächter-Kern
Bereits realisiert (selbst-verbessernder Autopilot, Master-Ensemble, Regime-HMM, Recherchetool). Für die
Vernetzung: Ereignis-Push an Dizzi (z. B. Risiko-/Drawdown-Alerts) über das generalisierte K4-Protokoll.

## 5. Sensible Daten & Sicherheit (Echtgeld = härteste Stufe)
- **API-Keys: NIE Withdrawal-Rechte**, „trade-only", **IP-Whitelisting**, Rotation; Keys nur im
  Secret-Tresor (`.env` außerhalb Repo/OneDrive) — **nicht** in Code/Logs/Backups (Backup-Audit secret-frei).
- **Harte Risiko-Limits** (Stop-Loss `stoploss_on_exchange`, Max-Daily-Loss) — vorhanden, beibehalten.
- **Echtgeld-Aktion = Human-in-the-Loop + verifizierte Verbindung** (Dizzi darf lesen/vorschlagen, nicht
  eigenmächtig handeln).

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **CCXT-Unified-Layer** (kein Exchange-Lock-in); Decimal für Geld; idempotente Orders; Backtest/Sim-Gate
  vor Live (vorhanden: anchored Walk-Forward, OOS-Gates).
- Read-only-Trennung im MCP strikt halten; Aktions-Tools separat + gegated.

## 7. Entscheidungen (Fragerunde 3, 11.06.)
**✅ Festgelegt:** Echtgeld läuft über API-Keys + Echtgeld-Key-Freischaltung; **Login/Verifizierung ZUERST**
(Google-Login = K1, erster Sicherheitsschritt); Echtgeld zeitlich fern. Vermögensstand → Dizz Money (read-only).
**Marke „Dizz Trading"** = Produktname (Branding/Icons). Reihenfolge K6: erst Dizzi-ID, dann Echtgeld-Gate.

---

## R-B: Echtgeld-Sicherheit — Architektur-Recherche (11.06., für K1/K6 + Sicherheits-Konzept-Runde)

### A. Bitget-Mechanik passt EXAKT zur Nutzer-Vision (Sub-Account-pro-Bot)
- **Bot-Trading-Sub-Accounts (Bitget-nativ):** beim Bot-Start wird das investierte Kapital **automatisch vom
  Hauptkonto ins Sub-Konto transferiert**, beim Bot-Stop **zurück**. Genau das gewünschte „Echtgeld-
  Überweisungs-Management, dem konkreten Bot zugewiesen". Sub-Konten **isolieren** Positionen/Assets/Rechte
  → ein Bot-Risiko drainiert nie das Gesamtkapital. `Sub-Transfer`-API + eigene API-Keys je Sub-Konto.
- **Kapital-Zuweisung = bewusste, Bitget-bestätigte Aktion** (Haupt→Sub-Transfer mit 2FA) → erfüllt
  „Transaktion über Bitget bestätigen". Der Bot bekommt nur einen **trade-only-Key auf SEIN Sub-Konto**.

### B. API-Key-Hygiene (hart)
- **Keys: NIE Withdrawal** — `trade`-only; **IP-Whitelist** (Withdrawal nur über Whitelist-IP, von Bitget
  erzwungen); **2FA** für Key-Erstellung; **Rotation alle 90 Tage**; Keys nur im Secret-Tresor (`.env`
  außerhalb Repo/OneDrive). Je Bot/Sub-Konto eigener, eng berechtigter Key (max. 10/UID).
- **Withdrawal bleibt manuell + Hauptkonto + Whitelist + OTP/2FA** — nie über Bot/Automatik.

### C. Login-zuerst → Echtgeld-Gate (deckt sich mit K1)
- **Stufe 1 (jetzt): Google-Login** über Dizzi-ID (OIDC, Loopback+PKCE) — der erste Sicherheitsschritt.
- **Stufe 2 (vor Echtgeld): Step-up auf Passkey/WebAuthn (FIDO2)** + Fallback-MFA (TOTP/verifizierte
  E-Mail) für Wiederherstellung/Hochrisiko. „Verifizierte Verbindung" als Tor zu Echtgeld-Daten/-Aktionen.
- Modell „Passkey bevorzugt, MFA als Recovery/High-Risk" ist 2026-Standard → genau die K1/K1+-Auslegung.

### D. Staged Go-Live (Pflicht-Gates vor echtem Kapital)
Backtest → **Paper-Trading 2–4 Wochen** → **Live mit 10–25 % des Kapitals 2–4 Wochen** → erst dann skalieren.
(Dizz Trading hat anchored Walk-Forward + OOS-Gates bereits — passt; Echtgeld-Gate ergänzt die menschliche
Freigabe-Stufe.)

### E. Was K1/K6 + die Sicherheits-Konzept-Runde liefern müssen
1. **K1 Dizzi-ID**: Google-OIDC-Login (Stufe 1) + Passkey/MFA-Step-up (Stufe 2) + „verifizierte Verbindung".
2. **K6 Trading-Angleichung**: Echtgeld-Gate an Dizzi-ID-Hochsicherheit koppeln; Sub-Account-pro-Bot-Flow
   als „Echtgeld-Überweisungs-Management" abbilden (Haupt↔Sub-Transfer, Bitget-bestätigt); trade-only-Keys.
3. **MCP bleibt read-only**; Echtgeld-Aktionen sind separate, gegatete Aktions-Tools (Human-in-the-Loop).

## Quellen
- [CCXT — GitHub](https://github.com/ccxt/ccxt)
- [Bitget — Bot-Trading-Sub-Accounts](https://www.bitget.com/support/articles/12560603786834) · [Sub-Account-Guide](https://www.bitget.com/academy/bitget-sub-account-guide) · [Sub-Transfer-API](https://www.bitget.com/api-doc/spot/account/Sub-Transfer)
- [Bitget API — Quick Start / Key-Permissions](https://www.bitget.com/api-doc/common/quick-start)
- [Crypto-Bot-Security & API-Key-Management](https://origami.tech/articles/crypto-bot-security-and-api-key-management-for-safe-automated-trading) · [API-Key-Security](https://tradelink.pro/blog/how-to-secure-api-key/)
- [FIDO2/WebAuthn/Passkey — Architektur-Guide](https://medium.com/@navuluribalaji03/passwordless-login-explained-an-architects-guide-to-fido2-and-passkeys-d5c8af03d383) · [FIDO Alliance — Passkeys](https://fidoalliance.org/fido2/)
