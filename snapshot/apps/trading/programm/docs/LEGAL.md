# Rechtliche & steuerliche Einordnung (Deutschland / Bayern)

> **Wichtiger Hinweis:** Dies ist **kein Rechts- oder Steuerrat**, sondern eine
> Orientierung nach eigener Recherche (Stand Juni 2026). Vor einer Skalierung
> mit nennenswertem Echtgeld unbedingt einen **Steuerberater** und im Zweifel
> die **BaFin** konsultieren. Quellen am Ende.

## 1. Braucht ein privater Trading-Bot eine BaFin-Erlaubnis?

Kurz: **Nein**, solange der Bot ausschließlich **dein eigenes Vermögen** auf
**deinem eigenen Konto** handelt. Die Erlaubnispflicht nach dem
Kreditwesengesetz (KWG) zielt auf das **Anbieten von Finanz- bzw.
Kryptowerte-Dienstleistungen gegenüber Dritten** ab.

Erlaubnispflichtig würde es insbesondere, wenn du:
- die Bot-/Signal-Leistung **anderen Personen anbietest** (Vermögensverwaltung,
  Anlageberatung, Copy-/Signal-Trading gegen Entgelt), oder
- echten **Hochfrequenzhandel** im aufsichtsrechtlichen Sinn an Handelsplätzen
  betreibst (§ 1 Abs. 1a KWG).

➡️ **Für dieses Projekt (rein privat, eigenes Geld): erlaubnisfrei.**

## 2. BaFin-Warnungen — relevant fürs Bewusstsein

Die BaFin veröffentlicht 2025/2026 laufend Warnungen vor kommerziellen
„KI-Trading-Bot"-Plattformen. Diese Angebote sind **überwiegend Betrug**
(unerlaubte Geschäfte, „garantierte" Renditen). Der hier gebaute Eigenbau ist
davon nicht betroffen — die Konsequenz fürs Projekt lautet jedoch:

- **Keine externen „Signal-", „Copy-" oder „KI-Renditen"-Dienste** anbinden.
- Keine fremden Gelder verwalten, kein Anbieten an Dritte.

## 3. Steuer (private Anleger, Krypto)

- Kryptowährungen gelten als **„sonstige Wirtschaftsgüter"** (§ 23 EStG).
- **Haltefrist:** Gewinne aus Verkauf/Tausch sind nach **mehr als 1 Jahr**
  Haltedauer **steuerfrei**.
- **Freigrenze:** Gewinne aus privaten Veräußerungsgeschäften bleiben bis
  **999,99 € pro Jahr** steuerfrei — wird die Grenze überschritten, ist der
  **gesamte** Betrag steuerpflichtig (Freigrenze, kein Freibetrag).
- **Steuersatz:** persönlicher Einkommensteuersatz (0–45 %).
- **Tausch zählt als Verkauf:** auch Krypto-zu-Krypto (z. B. BTC→ETH) löst ein
  Veräußerungsgeschäft aus.

## 4. Gewerblichkeits-Risiko (wichtig bei Bots!)

**Häufiges, automatisiertes Traden** kann vom Finanzamt als **gewerbliche
Tätigkeit** eingestuft werden. Folgen:
- Die **Haltefrist-Befreiung entfällt** (alle Gewinne steuerpflichtig).
- Mögliche **Gewerbesteuer**, Buchführungspflichten.

➡️ Mitigation im Projekt: **Trade-Frequenz bewusst begrenzen**
(Parameter „Max Trades/Tag"), Echtgeld klein halten, und vor Skalierung einen
Steuerberater einbinden.

## 5. DAC8 — EU-Meldepflicht ab 2026

Ab 2026 macht die EU-Richtlinie **DAC8** Krypto-Trades für die Finanzbehörden
EU-weit transparent. **Lückenlose Dokumentation aller Transaktionen und Trades
ist Pflicht**, nicht optional.

➡️ Deshalb sind im System ein **Audit-Log** und ein **Steuer-/CSV-Export**
von Anfang an Kern-Features (siehe `backend/app/audit.py`).

## 6. Zusammenfassung der Bau-Konsequenzen

| Rechtlicher Punkt | Umsetzung im Projekt |
|---|---|
| Erlaubnisfrei nur privat | Keine Drittnutzung, kein Anbieten |
| Gewerblichkeits-Risiko | Parameter „Max Trades/Tag", Echtgeld klein |
| DAC8 / Steuer | Audit-Log + CSV-/Steuer-Export ab Tag 1 |
| Betrugsschutz | Keine externen Signal-/Copy-Dienste |
| Kapitalschutz | Read-only-Keys zuerst, nie Withdraw-Rechte an Bots |

---

### Quellen

- BaFin – Algorithmischer/Hochfrequenzhandel:
  <https://www.bafin.de/DE/Aufsicht/BoersenMaerkte/Handel/Hochfrequenzhandel/high_frequency_trading_artikel.html>
- BaFin – Warnungen „KI-Trading-Bots":
  <https://www.bafin.de/SharedDocs/Veroeffentlichungen/DE/Verbrauchermitteilung/unerlaubte/2024/meldung_2024_12_17_ki_trading_bots.html>
- Krypto-Steuer DE 2026 (§ 23 EStG, Haltefrist, DAC8):
  <https://www.blockpit.io/de-de/steuer-guides/krypto-steuer-deutschland>
