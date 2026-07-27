# 34 · A5 — Bereichs-Querverbindungen V17 / V18 / V19 (Design / „entwerfen")

> **Zweck:** die drei Querverbindungen entwerfen, die die **Bereichs-/Kategorie-Achse** von Dizz Admin
> (`adminapp/bereiche.py`) an **Money · Management · Memory** anbinden — damit ein Bereich („Studium X",
> „Geschäft Y") seine **Finanzspur**, seine **Social-Aktivität** und sein **Wissen** systematisch zeigt.
> Entworfen 20.06. (World-Admin-Chat). **Reine Spec** — Bau gestaffelt (s. §5), Verträge werden beim Bau
> in docs/26 (Querverbindungs-Registry) gefaltet.

## 1 · Ausgangslage — das Modell ist VORGESLOTTET
`bereiche` (docs/_archiv/28 §2) trägt bereits die Andockpunkte: **`money_kontext`** (Schlüssel der per-Bereich-
Finanzspur = V17) und **`memory_ref`** (gespiegelte Memory-Kategorie = V19). Für V18 kommt analog ein
**`management_kontext`** (gleiche Mechanik) dazu. `bereich.id` ist der stabile Default-Schlüssel, falls der
Nutzer keinen sprechenden Kontext setzt. ⇒ A5 = die Verträge, die diese Slots NUTZEN.

## 2 · Designprinzipien (wie V14–V16, bewährt)
- **Daten bleiben bei der Quelle.** Admin **liest** read-only über den **Core-Relay** (Drehscheibe + Audit);
  es dupliziert nichts. Money/Management/Memory bleiben die Eigentümer ihrer Daten (Ledger = Sorgfaltskern).
- **Additiv, Vertrag bleibt 1.5.** Neue Core-Relays + appkit-Helfer; keine Schema-Brüche.
- **Best-effort / wirft nie.** Core/Ziel offline ⇒ leere Sicht + Hinweis, die fragende App läuft weiter.
- **Schreiben/Außenwirkung bleibt App-HITL.** Querverbindungen sind read-only-Lesepfade; Buchen/Posten/
  Veröffentlichen läuft NIE hierüber (K4 in der jeweiligen App).
- **Idempotente Zuordnung über den `kontext`/`ordner`-Tag** — eine App taggt ihre Entität optional mit dem
  Bereichs-Schlüssel; die Aggregation ist eine reine GROUP-BY-Lese-Operation.

## 3 · Die drei Verträge

### V17 · Money ↔ Admin — Bereichs-Finanzspur (`bereich.money_kontext`)
- **Money-Seite:** Buchungen/Konten tragen optional einen `kontext`-Tag (= `money_kontext` eines Bereichs).
  Money aggregiert je kontext read-only: Einnahmen / Ausgaben / Saldo / Top-Kategorien / offene Posten
  (Minor-Units, pro Währung). Neuer Endpoint `GET /api/bereich/finanzspur?kontext=&jahr=`.
- **Relay:** `GET /api/querverbindung/finanzen/finanzspur?kontext=&jahr=` → Money-Aggregat (Muster: V16 `/euer`).
- **Admin-Seite:** das Bereichs-Cockpit zeigt die Finanzspur des Bereichs (best-effort).
- **Richtung:** Admin liest aus Money; **kein Schreiben**. (Buchen bleibt Money-HITL.)

### V18 · Management ↔ Admin — Bereichs-Social (neuer Slot `bereich.management_kontext`)
- **Management-Seite:** Posts/Social-Bots tragen optional einen `kontext`-Tag. Aggregat je kontext read-only:
  geplante/veröffentlichte Posts, aktive Bots, nächster Zeitplan-Slot, Plattform-Verteilung.
  Endpoint `GET /api/bereich/social?kontext=`.
  - **Update 26.06. (Management-Bereich-Achse):** Management führt jetzt eine eigene `bereiche`-Tabelle
    (Muster Admin/Money) mit `bereich_id`-FK an Kanälen/Bots/Posts + einem `kontext`-Slot
    (= `bereich.management_kontext`). `Domain.social(kontext)` löst `kontext` **zuerst über die lokale
    `bereiche.kontext` auf** (Aggregat je `bereich_id`); findet sich kein Bereich, greift der
    **rückwärtskompatible Fallback** auf den Social-Bot-Namen (Alt-Mechanik) ⇒ das Admin-Cockpit bleibt
    grün, bis Bereiche+`kontext` gepflegt sind. Keine Vertrags-/Relay-Änderung.
- **Relay:** `GET /api/querverbindung/management/bereich-social?kontext=` → Management-Aggregat.
- **Admin-Seite:** Bereichs-Cockpit zeigt die Social-Aktivität des Bereichs.
- **Veröffentlichen** bleibt strikt Management-HITL (`verifiziert`), nie über die Querverbindung.

### V19 · Memory ↔ Admin — Bereichs-Kategorie/Wissen (`bereich.memory_ref`)
- **Memory-Seite:** `memory_ref` = ein Memory-Ordner/Kategorie. Memory liefert die Notizen dieses Ordners
  (RÜCK-LESE). Erweiterung des bestehenden `memory_suche` um einen **Ordner-Filter** ODER Relay
  `GET /api/querverbindung/memory/kategorie?ordner=&limit=`.
- **Spiegelung (der Clou):** wenn Admin-Module nach Memory archivieren (V6-artig), setzen sie `ordner=memory_ref`
  ⇒ der Inhalt landet in der Bereichs-Kategorie ⇒ erscheint automatisch in der Bereichs-Wissenssicht.
- **Admin-Seite:** Bereichs-Cockpit zeigt „Wissen dieses Bereichs" (die Notizen der Kategorie, klickbar → Memory).
- **Richtung:** Admin liest aus Memory (RÜCK-LESE), Memory bleibt Eigentümer.

## 4 · Was der World-Chat baut vs. was delegierbar ist
- **World-Chat (appkit + Core):** die **3 Core-Relays** (`/finanzspur`, `/bereich-social`, `/kategorie`,
  Muster der bestehenden `/euer`/`/belege`/`/suche`-Relays) + appkit-Querverbindungs-Helfer
  (`finanzspur_holen` / `bereich_social_holen` / `kategorie_holen`, best-effort) + `management_kontext`-Slot
  an `bereiche` (mini-Migration). Additiv, +Tests.
- **App-Chats (je Quelle, delegierbar):** die read-only **Aggregations-Endpunkte** (Money `/api/bereich/finanzspur`,
  Management `/api/bereich/social`, Memory Ordner-Filter) + das optionale **`kontext`-Tagging** beim Schreiben.
- **Admin (§5d, mit Nutzer):** die **Bereichs-Cockpit-Anzeige** (Finanzspur/Social/Wissen je Bereich) — UI-Phase.

## 5 · Baureihenfolge (gestaffelt, je Schritt grün + committet)
1. **World-Chat:** ✅ **Die 3 Core-Relays GEBAUT (20.06., Core 163 grün):** `GET …/{ziel}/finanzspur` (V17) ·
   `…/bereich-social` (V18) · `…/kategorie` (V19) in `core/app/main.py` — read-only Drehscheiben (Muster `/euer`//
   `/belege`), best-effort/zentral-auditiert, 404 wenn Ziel nicht angedockt; +7 Tests. **✅ appkit-Helfer GEBAUT**
   (20.06., appkit **1.21.0**, appkit 107 grün): `finanzspur_holen` (V17) · `bereich_social_holen` (V18) ·
   `kategorie_holen` (V19) in `appkit/querverbindung.py` (Muster `memory_suche`/`belege_holen`, best-effort/wirft nie),
   +6 Tests. **⇒ die appkit+Core-Seite von A5 ist KOMPLETT.**
   **✅ A5-PHASE-2 ANGELAUFEN (20.06., World-Admin-Chat, Repos frei):** (a) **appkit 1.21 netzwerkweit vendort** (8 Live-
   Repos, `--check` byte-identisch, alle Suiten grün) ✅ · (b) **`management_kontext`-Slot an `bereiche` gebaut** (admin/
   `bereiche.py`: Schema + idempotente Nachtopf-Migration + Modelle/CRUD + 2 Tests, 160 grün) ✅.
   **✅ (c) die 3 App-Aggregations-Endpunkte GEBAUT (20.06., World-Admin-Chat inline, je read-only + Tests + committet):**
   **Money** `GET /api/bereich/finanzspur?kontext=&jahr=` (finanzen `66a49b8`, 335 grün; je Währung getrennt, `kontext`→
   Kategorie-Name) · **Management** `GET /api/bereich/social?kontext=` (social-media `b5e1f2b`, 128 grün; `kontext`→Social-Bot-
   Name, Kanäle/Posts/nächste) · **Memory** `GET /api/kategorie?ordner=&limit=` (archiv `b902139`, 169 grün; `ordner`→Ordner-
   Name, sensibel ohne Auszug). **⇒ A5 a–c KOMPLETT.** **✅ (d) BACKEND GEBAUT (20.06., admin `f2c2ae1`):** `GET
   /api/bereiche/{bid}/cockpit` + `aggregat.bereich_spuren()` bündelt die 3 Spuren je Bereich über die appkit-1.21-Helfer
   (read-only/best-effort, wirft nie; tests/ 163 grün). **✅ (d) VISUELLES COCKPIT GEBAUT + LIVE (admin `34390de`, Variante A
   „3 Spalten"):** `bereichCockpit` rendert je Bereich einen „Querverbindungen"-Block (Finanzspur/Social/Wissen) async aus
   dem Cockpit-Endpoint; Browser-verifiziert (3 Spur-Boxen, 0 Konsolenfehler), live :8222 serviert es. **⇒ A5 KOMPLETT (a–d).**
2. **App-Chats:** ✅ erledigt (inline gebaut 20.06., s. (c) oben).
3. **Admin/§5d:** ✅ Cockpit-Backend + visuelles Cockpit (Variante A) LIVE. **A5 ABGESCHLOSSEN** — nur Feinschliff/Feel-Check 👤 offen.

> Sicherheits-Hinweis: Money/Health-artige Sensibilität — die Aggregate liefern KENNZAHLEN, nicht Rohdaten
> (Money: Summen/Kategorien, keine Einzel-Beträge nötig fürs Cockpit). Memory bleibt sensibel-lokal. Alle drei
> sind read-only; jede Außenwirkung bleibt in der Quell-App hinter deren HITL-Freigabe.
