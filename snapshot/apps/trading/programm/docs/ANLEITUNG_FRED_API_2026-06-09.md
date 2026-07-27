# 📘 Anleitung: FRED-API-Key einrichten (echte Makro-Werte)

Ziel: Statt des aktuellen key-freien Proxys (Kalender-Surprise + Krypto-Risk) **echte Makro-Zeitreihen**
(CPI, Fed-Funds-Rate, Arbeitslosigkeit, …) direkt von der **St. Louis Fed (FRED)** nutzen. FRED ist
**kostenlos**, der Key kommt **sofort**. Quelle: <https://fred.stlouisfed.org/docs/api/api_key.html>.

## Teil A — Was DU tust (5 Minuten, einmalig)
1. **Konto anlegen:** <https://fredaccount.stlouisfed.org/login/secure/> → „Register" (E-Mail + Passwort).
2. **API-Key anfordern:** eingeloggt auf <https://fredaccount.stlouisfed.org/apikeys> → „Request API Key",
   kurzen Verwendungszweck eintragen (z. B. „personal research / trading dashboard") → **Key wird sofort
   angezeigt** (32-stelliger Klein-Buchstaben/Ziffern-String, z. B. `abcd1234…`).
3. **Key mir/dem System geben** — auf eine von zwei Arten (NICHT in Git committen!):
   - **Empfohlen:** in die bestehende, gitignorierte Key-Datei legen (wie der Anthropic-Key), oder
   - als **Umgebungsvariable** `FRED_API_KEY` setzen, bevor :8137 startet:
     PowerShell: `$env:FRED_API_KEY = "deinkey"` (im selben Fenster, aus dem uvicorn gestartet wird).
4. Mir Bescheid geben → ich baue die Anbindung (Teil B) und teste sie live.

## Teil B — Was ICH dann baue (kein Aufwand für dich)
- Neues Modul-Stück in `fundamental.py`: `fred_series(series_id)` holt die jüngsten Werte über
  `https://api.stlouisfed.org/fred/series/observations?series_id=...&api_key=...&file_type=json`
  (stdlib `urllib`, gecacht wie Kalender/CoinGecko, defensiv mit Fallback → bei fehlendem Key bleibt
  einfach der heutige Proxy aktiv, **nichts bricht**).
- Relevante Serien (Beispiele):
  | Serie | FRED series_id | Nutzen |
  |---|---|---|
  | Verbraucherpreise (CPI) | `CPIAUCSL` | Inflations-Trend |
  | Kern-PCE (Fed-Lieblingsmaß) | `PCEPILFE` | Inflations-Tilt |
  | Fed-Funds-Zielrate | `DFEDTARU` / `FEDFUNDS` | Liquiditäts-Regime (easing/tightening) |
  | Arbeitslosenquote | `UNRATE` | Konjunktur |
  | 10J-Treasury-Rendite | `DGS10` | Realzins/Risk-Tilt |
  | Financial Conditions | `NFCI` | Risk-on/off (sehr gut für BTC) |
- Daraus eine **echte Makro-Stance** (easing/tightening, lockere/straffe Finanzbedingungen) statt des
  Proxys → ersetzt/ergänzt den `macro_stance`-Teil im Master-Overlay. Tests + Live-Verifikation.

## Wichtig / Sicherheit
- **Key NIE in Git.** Die `.gitignore` deckt `*.key` / `1 API Key/` / `.env` bereits ab — dort ablegen.
- Rate-Limit großzügig (120 Req/min); wir cachen ohnehin (≥6 h) → unkritisch.
- Rein **lesend**, 0 Risiko, proposal-only — wie alle anderen Datenquellen.
- **Optional.** Ohne Key läuft alles weiter (key-freier Proxy). Der Key macht die Makro-Stance nur „echt".
