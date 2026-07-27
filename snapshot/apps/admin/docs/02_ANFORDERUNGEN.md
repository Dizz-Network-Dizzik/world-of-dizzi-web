# Anforderungsliste — Dizz Leading — Geschäftsführung

> Kern-Umfang. EXKLUSIV-App (nicht verkaufbar). Bau-Position: nach Admin/Money/Communication.

## Kern (Muss)
- [ ] Geschäfts-Schema: Kunde, Produkt (=Dizz-App), Lizenz/Abo, Angebot/Rechnung (GoBD-Archiv,
      Append-only), Frist, Support-Vorgang
- [ ] Rechnungen: erstellen/nummerieren/archivieren; **E-Rechnung empfangen** (XRechnung/ZUGFeRD-Parser)
- [ ] EÜR-Sicht + Steuerberater-Export (CSV/DATEV-Slot)
- [ ] Interne Vernetzung: MCP-Konsum aus Admin/Money/Communication + Zuweisungs-Muster „geschäftlich"
- [ ] Geschäfts-KPIs-Kachel; Lern-KI-Beobachtung (Fristen/Anomalien, HITL)
- [ ] MCP-Tools (read-only): geschaefts_kpis, offene_rechnungen, naechste_fristen

## Quer (App-Vertrag, gilt für alle)
- [ ] `/api/summary` · MCP-Server · Dizzi-ID (SSO) + Standalone-Login · K2-Settings/Tresor ·
      user-scoped+sync-ready · Tests + Doku-Sync (Gesetz 9)

## Entschieden (bei Anlage, 12.06.)
- **Marke:** Dizz Leading · Port **8219** · sensitivity **hoch** · exklusiv beim Nutzer
- Aggregator-Prinzip: Schwestern KONSUMIEREN statt doppeln

## Offen (Fragerunde vor Bau)
- [ ] Rechtsform/Kleinunternehmer-Regelung? · Steuerberater (DATEV?) · Zahlungsanbieter/MoR ·
      Lizenz-Modell der verkauften Apps (Keys? Abo?) · Umfang Kunden-CRM v1
