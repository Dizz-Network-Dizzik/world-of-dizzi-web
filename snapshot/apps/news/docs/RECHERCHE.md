# Recherche-Dossier — Dizz News (News)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> Zweck: Konnektoren, Standards und **jetzt vorzusehende** Verbindungs-Vorbereitungen.
> Provisorischer Markenname „Dizz News" — bei Gelegenheit bestätigen.

## 1. Feature-Baseline (Marktstandard)
Feed-Aggregation (Abos), Ordner/Kategorien, Lesestatus/Favoriten/Later, Volltextsuche, **KI-Zusammen-
fassung + Kategorisierung**, Digests/Alerts, Entrauschen (Dedup/Cluster). Vorbilder (OSS, self-host):
**FreshRSS** (1 Mio+ Artikel, 50k+ Feeds, WebSub-Push, XPath-Scraping für Seiten ohne Feed),
**Miniflux** (minimalistisch). Bereits im Dizzi-Kosmos vorhanden: ein **News-Skill** + sehr seriöse
Fixquellen (sektor-gegliederter Report) — Dizz News ist die ausgebaute, eigenständige App dazu.

## 2. Standard-Datenquellen & Konnektoren
- **Offene Feed-Standards: RSS / Atom / JSON Feed**, **WebSub** (Echtzeit-Push), **OPML** (Abo-Import/
  -Export), **XPath/CSS-Scraping** als Fallback für quellenseitig fehlende Feeds.
- **Aggregator-APIs** (optional, teils kostenpflichtig): NewsAPI u. a. — eher Ergänzung; RSS/Atom ist
  der 0-€-Kern.
- **KI-Anreicherung:** lokale LLMs (Ollama) für Zusammenfassung/Kategorisierung + Boost-Fallback;
  regelbasierter Fallback (wie der bestehende News-Skill).
- **Querverbindung:** interessante Artikel → **Dizz Knowledge** (Clip/Highlight), Markt-/Sektor-News →
  **Dizz Trading**-Kontext.

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **`FeedSource`-Interface**: `RssAtom`, `JsonFeed`, `WebSubPush`, `Scrape(XPath)` — Stecker.
- **OPML-Import/-Export** ab v1 (schmerzfreier Umzug von/zu anderen Readern).
- **Anreicherungs-Pipeline** (Fetch→Dedup/Cluster→KI-Summary/Tag→Index) modular; KI-Schritt optional
  und anbieter-austauschbar.
- **Brücke zu Dizz Knowledge** (Artikel als Markdown-Clip) als dokumentierter Slot.

## 4. App-eigener KI-Wächter-Kern
Themen-Interessen lernen (was wird gelesen/geklickt), **Rausch-Reduktion** (Cluster gleicher Story),
Sektor-Digests, Eil-Alerts zu Beobachtungsthemen, Sentiment/Trend. Passt zu Dizzis proaktivem Analyst.

## 5. Sensible Daten & Sicherheit
Wenig sensibel (öffentliche Inhalte) → Boost-KI für Summaries i. d. R. unproblematisch. Lesehistorie/
Interessen sind aber persönlich → lokal halten. Quellen-Seriosität bewusst kuratieren (Fixquellen-Prinzip).

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **RSS/Atom/JSON Feed + OPML + WebSub** statt Eigenbau; konditionelle Requests (ETag/If-Modified-Since)
  gegen Last; Dedup über Content-Hash.
- Anreicherung als austauschbare Stufe (regelbasiert ↔ LLM), nicht fest verdrahtet.
- Zeitzonen/Quellen sauber; Rate-Limits/Backoff je Quelle.

## 7. Offene Entscheidungsfragen → Fragerunde
0. **✅ ENTSCHIEDEN (F-Q1, Architektur-KI 11.06., docs/11 §6b): eigener schlanker Feed-Kern** (feedparser-Pipeline
   + OPML ab v1) — FreshRSS/Miniflux nur als Konzept-Blaupause (FreshRSS = AGPL-3.0 + PHP; Maschine ohne
   PHP/Docker). Kleinster der vier Eigen-Kerne.
1. **Dizz News = Ausbau des bestehenden News-Skills** (gleiche Fixquellen-Logik, sektor-gegliedert) — so gewollt?
2. **Reiner RSS/Atom-Kern (0 €)** ausreichend, oder kostenpflichtige Aggregatoren (NewsAPI) ergänzen?
3. KI-Summaries **lokal (Ollama)** bevorzugt — ok? (spart Kosten, Lesehistorie bleibt privat)
4. Markenname „Dizz News" bestätigen?

## Quellen
- [FreshRSS — self-hosted Aggregator](https://freshrss.org/index.html) · [GitHub](https://github.com/FreshRSS/FreshRSS)
- [Self-hosted RSS-Reader (Übersicht)](https://selfh.st/alternatives/rss-readers/)
- [AI-enhanced RSS/Atom-Aggregator (Beispiel)](https://github.com/tony-stark-eth/news-aggregator)
