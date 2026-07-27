# Konzept: Krypto-Strategie-Recherche-Tool (Ausbaustufe „maximal")

Ziel: Bei manueller Auslösung startet ein **umfangreicher Recherche-Prozess**,
der **validierte Quellen wiederholt** heranzieht **und gezielt neue Quellen
sucht**, um **klar definierte, qualitativ hochwertige Krypto-Trading-Strategien**
auszugeben — mit Kontext, klaren Regeln und strategie-spezifischen Parametern.

> Grundsatz (vom Nutzer mehrfach betont): **klarer Kontext + klar aufgestellte
> Regeln**, sodass ein Bot die Strategie eindeutig befolgen kann.

## 1. Geltungsbereich (Scope)
- **Nur Krypto.**
- **Zeit-Horizont:** Short-Term (Minutenbasis/Scalping) bis **Intraday/kurzer
  Swing ≤ 1 Tag**. **Alles über 1 Tag = Investment → ausgeschlossen.**
- **Markttyp:** **Spot** (Standard) **oder Futures (mit Hebel)** — pro Strategie
  klar deklariert. Futures nur, wenn in den Recherche-Einstellungen erlaubt.
- **Begrenzte Anzahl** (6–10) der besten Systeme, in zwei Gruppen:
  krypto-spezifisch / allgemein (krypto-tauglich).

## 2. Pro Strategie auszugeben (Datenfelder)
| Feld | Inhalt |
|---|---|
| `name`, `id`, `group` | Bezeichnung, Kennung, Gruppe (krypto/allgemein) |
| `context` | **Kontext/Idee**: warum/woran verdient die Strategie, Marktlogik |
| `entry_rules` / `exit_rules` | **Klare, eindeutige Regeln** für Ein-/Ausstieg |
| `params` | Liste je Parameter: `name`, **`role` (was bewirkt er)**, **`category`** (`indikator`/`volumen`/`risiko`/`session`/`krypto`), `min`, `max`, `default`, **`optional`** (bool, Feintuning → einklappbar). Es werden **nur relevante** Parameter gelistet; irrelevante Kategorien entfallen, müssen also nicht ausgefüllt werden. |
| `timeframe` | Basis-Zeitfenster (z. B. 1m, 5m, 15m, 1h) |
| `horizon` | `scalp` (Sek–Min), `intraday` (Std), `short_swing` (≤1 Tag) |
| `market_type` | `spot` oder `futures` |
| `leverage` | bei Futures: empfohlener Hebel (z. B. 1–3x), bei Spot „1x" |
| `session` | bevorzugte Handelszeit: `asia` / `eu` / `us` / `eu_us_overlap` / `beliebig` |
| `regime` | passende Marktphase: `trend` / `range` / `volatil` |
| `risk` | grobe Risikoeinstufung |
| `validated` | true, wenn aus validierter Quelle bestätigt |
| `sources` | konkrete Quellen (URL/Kanal/Video) |

## 3. Handelssessions (für `session`)
- **Asien** ~00:00–08:00 UTC: ruhiger, eher Range → gut für Mean-Reversion/Grid.
- **Europa** ~07:00–16:00 UTC: anziehende Aktivität.
- **USA** ~13:00–22:00 UTC: höchste Volatilität.
- **EU-US-Overlap** ~13:00–16:00 UTC: **größte Bewegungen** → gut für
  Breakout/Momentum.

## 4. Recherche-Prozess (bei „Recherche aktualisieren")
1. **Validierte Quellen zuerst** (Standard-Liste + eigene, z. B. YouTuber, der
   Strategien sauber backtestet) — werden bei jedem Lauf erneut ausgewertet.
2. **Neue Quellen suchen** (echte Web-Suche) und auf Eignung prüfen.
3. **Krypto-Anwendbarkeit prüfen** — Nicht-Krypto-taugliches verwerfen.
4. **Horizont-Filter** — nichts über 1 Tag.
5. **Strukturieren** in obige Felder; **angepinnte** Systeme bleiben erhalten.
6. Ergebnis als Katalog (`data/strategy_catalog.json`), Quelle `ai`.

**Technik:** Claude-API mit **`web_search`-Tool** (`web_search_20250305`),
`allowed_domains` aus den validierten Quellen, plus freie Suche; `max_uses`
begrenzt die Such-Tiefe/Kosten. Ohne Key / ohne Console-Freischaltung → Seed.

## 5. Validierte Standard-Quellen (Start)
- Freqtrade-Doku / freqtrade-strategies (Engine-/Strategie-Referenz)
- Daten-/Backtest-orientierte YouTuber (z. B. Benjamin Cowen) — **Nutzer ergänzt
  seinen bevorzugten Backtest-Kanal** (folgt).
> Quellen sind im Dashboard ein-/ausklappbar pflegbar (Name + URL).

## 6. Einstellungen (`data/research_config.json`)
- `allow_futures` (Default: false) — Futures-Strategien zulassen?
- `horizon_scope` (Default: `intraday`) — max. Horizont (`scalp`|`intraday`|`short_swing`).
- `max_systems` (Default: 8)

## 7. Sicherheit / Qualität
- Jede neue Strategie ist zunächst nur **Vorschlag**; bevor ein Bot sie nutzt:
  **Pflicht-Backtest + Demo-Run**. Eine eigene **Freqtrade-Vorlage** je System
  ist nötig, damit sie ausführbar wird (bislang: Trendfolge, Mean-Reversion,
  Momentum vorhanden; weitere folgen).
- **Invariante „keine Vorlagen-Leichen" (docs/47 §5, festgeschrieben 25.06.2026):**
  Eine Strategie gilt erst als **fertiges, anlegbares System**, wenn sie einen
  **lauffähigen Anlege-Pfad** hat:
  - **gerichtet** → eine **Freqtrade-Vorlage** (Engine) existiert ⇒ als Freqtrade-Bot anlegbar.
  - **markt-neutral** → eine **MN-Paper-Engine** (`csm`/`pairs`/`statarb`/`mm`) existiert ⇒
    als Demo-Paper-Bot anlegbar (`/api/mn-paper`). Freqtrade fährt ein Instrument pro Bot
    und kann gleichzeitig Long+Short auf korrelierten Paaren/Körben **bewusst nicht** abbilden —
    daher gibt es für diese Systeme **keine** Freqtrade-Vorlage, sondern den MN-Paper-Pfad.
  Hat sie **keinen** der beiden Pfade, bleibt sie im Katalog sichtbar als **„Vorschlag / in Arbeit"**
  — **nie** als top-bewertetes, aber nicht anlegbares System. So kann „existiert nur als Vorlage,
  aber nicht nutzbar" **nicht mehr** auftreten. (Im Frontend: markt-neutrale Katalog-Einträge tragen
  die Pill **⇄ MN-Paper-Bot** + den Knopf **→ MN-Paper-Bot** statt „Vorlage folgt".)
- Keine externen „Signal-/Copy-Dienste", keine Renditeversprechen (BaFin).

## 8. Offene To-dos (Implementierung)
- [ ] `web_search`-Tool in `_research_with_ai` aktiv (Groundwork steht).
- [ ] Anthropic-Console: Web-Suche freischalten (Org-Admin).
- [ ] YouTube-Quelle des Nutzers eintragen (folgt).
- [ ] Frontend: neue Felder (Kontext/Regeln/Session/Markttyp/Hebel) anzeigen.
- [ ] Weitere Freqtrade-Vorlagen für neu recherchierte Systeme.

---

## Upgrade „2.0" (2026-06-09) — Sicherheit & Effizienz als Kern-Scores
Zwei prominente, deterministisch berechnete **Entscheidungs-Scores (0–100)** je Strategie, in der UI
in den Fokus gerückt (Katalog-Tabelle Spalten 2–3 + Score-Pills auf den Karten, sortierbar):

- **🛡 Sicherheit** (`security_score`): aus `certainty` + Methode (OOS/Walk-Forward vs. in-sample) +
  `backtest_count` − Bias-Abzug (overfit/selection/look-ahead/survivorship). **Grounding:** wo das System
  eine EIGENE OOS-Validierung hat (`stats.strategy_validations`, gematcht per Template/Name), überschreibt
  die reale PF/Fenster-Zahl die LLM-Selbsteinschätzung (reproduzierbar) → `system_validated`-Flag (✓).
- **⚡ Effizienz** (`efficiency_score`): bevorzugt EIGENE Profit-Faktor-Evidenz (PF 0,8→5 … 1,5→50 …
  2,2→95, Overfit-Deckel 95), sonst KI-`efficiency`-Stufe ± Risiko. Best Practice: PF (≥1,5 viabel/≥2 stark,
  >3 = Overfit-Verdacht), Expectancy/CRV, Drawdown — kombiniert.

**Neue Felder:** `efficiency` (hoch/mittel/niedrig/unbekannt), `event_sensitivity` (Makro-Event-Exposure,
hoch/mittel/niedrig). **Prompt** erklärt dem Modell die neuen System-Fähigkeiten (HMM-Regime, Fundamental/
Event-Risiko, MN-Sockel, Deflated-Sharpe) und fordert `efficiency`/`event_sensitivity`/sauberen Regime-Fit;
„schöner In-sample-Backtest = Warnsignal". Scores werden **read-time** in `get_catalog` gegen die aktuelle
Eigen-Evidenz berechnet (`ai.attach_scores`). Funktionen rein/testbar (`tests/test_research_scoring.py`).
