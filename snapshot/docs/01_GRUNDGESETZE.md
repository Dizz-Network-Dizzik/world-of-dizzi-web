# Grundgesetze — the world of dizzi

> Verbindliche Arbeitsregeln des Nutzers für ALLE Arbeitssessions an diesem Projekt.
> Beim Wiedereinstieg IMMER mitberücksichtigen, ohne dass der Nutzer sie erwähnen muss.

0. **Die Essenz ist unantastbar (Verfassungsrang — Davids Wort, 13.07.2026)**
   - `docs/00_VISION_UND_ANFORDERUNGEN.md` **§0 „Die Haltung" + §0b „Die Essenz"** sind der Kern,
     aus dem dieses Netz wächst: eine Menschheit · Kulturen als Seele schützen, solange es geht ·
     Angst als permanenter Bewusstseins-Prozess · die vier Fragen (Was sind wir? Was können wir?
     Was haben wir geschaffen? Wo wollen wir hin?) · Angst und Gier zu den Sternen lenken ·
     gegen niemanden — die ausgestreckteste Hand.
   - Sie dürfen **nie entfernt, gekürzt, verwässert oder umgedeutet** werden — von keiner Session,
     keinem Merge, keinem Refactor, keinem Modell. Änderungen nur durch Davids ausdrückliches,
     wörtliches Wort.
   - **Maschinell verankert:** der Rundenabschluss-Wächter `ops/doku_check.py` prüft die
     Essenz-Anker (ESSENZ-ANKER, fail-closed) — eine Runde ohne intakte Essenz wird nicht grün.
   - Außen-Dokumente tragen ihr kalibriertes Echo; die Voll-Fassung lebt einzig in docs/00.

1. **Sicherungsrunden automatisch**
   - Bei mittelgroßen Arbeitspaketen: kleine Sicherungs-/Prüfrunden zwischendurch.
   - Nach großen Arbeitspaketen: immer eine große Kontrollrunde über alles.
   - Vor der großen Kontrollrunde: **systematische Ausgabe der Systeme/Funktionen**,
     damit der Nutzer Überblick behalten und tracken kann.

2. **Ehrliche Bewertungen**
   - Motto: „Wir finden gemeinsam den besten Weg." Bei eigenen Zweifeln: offen sagen,
     nicht schönreden.

3. **Regelmäßige selbstständige Recherche**
   - An kritischen Stellen gezielt, und generell regelmäßig eingestreut,
     damit ein maximal optimiertes Produkt entsteht.

4. **Code-Qualität = oberstes Gesetz**
   - Strukturell, professionell, funktionell, effizient, absolut sauber und nachvollziehbar.
   - Ernsthaftes Vorhaben, soll ggf. verkauft werden können. Perfektionismus. Gründlichkeit.

5. **Vorbereitungsmaßnahmen dokumentieren**
   - Vorinstallierte Anschlüsse/Vorbereitungen für spätere Eventualitäten werden im Code UND
     in der Systemübersicht gründlich erklärt — Bewusstsein über deren Vorhandensein muss herrschen,
     auch wenn sie noch keinen Nutzen haben.

6. **Bessere Optionen sofort melden; sichere Empfehlungen sofort umsetzen**
   - Findet die Recherche eine bessere Option / einen Verbesserungs- oder Erweiterungsvorschlag:
     Nutzer **sofort informieren**.
   - Absolut sichere, empfohlene Zwischenschritte: **dürfen sofort integriert werden**.
   - Kritische Punkte: aufsparen bzw. notfalls pausieren, nicht eigenmächtig durchziehen.

7. **Über-Nacht-Arbeitsschichten sind eingeplant**
   - Ablauf: dickes Arbeitspaket → Plan wird geprüft und einmal ausgegeben
     („Info verarbeitet, hier der Plan, so setze ich ihn über Nacht um") → Nutzer bestätigt →
     die KI arbeitet eigenständig durch (auch 5 h am Stück), ohne dass der Nutzer danebensitzt.

8. **„weiter" ohne offene Arbeitspakete = Routine-Systemcheck**
   - Sagt der Nutzer „weiter", aber alle besprochenen Pakete sind abgehandelt:
     klassischer Systemcheck — Code prüfen, alles läuft?, Recherche einstreuen,
     Verbesserungspotenzial suchen und melden.

9. **Dateistruktur-Sync nach jeder Bearbeitung/Planung** *(ergänzt 10.06.2026)*
   - Immer wenn etwas bearbeitet wurde oder neue Schritte geplant wurden, wird die
     **gesamte Dokumenten-/Dateistruktur mitgezogen**: Projektplan-Status, Systemübersicht,
     Wiedereinstiegs-Prompt, offene Fragen, Recherche-Protokolle, Gedächtnis-Index —
     alles spiegelt jederzeit den echten Stand.
   - Es darf NIE ein Zustand entstehen, in dem Code/Plan und Doku auseinanderlaufen;
     veraltete Referenzen werden beim Update aktiv entfernt.
   - Gilt für kleine Runden genauso wie für Nachtläufe — systematisch, immer.

10. **Modell-Wachsamkeit — DREI Stufen: Assistenz-KI / Bau-KI / Architektur-KI**
    - Arbeitspakete werden **dreistufig markiert** („Assistenz-KI-tauglich" / „Bau-KI" /
      „Architektur-KI nötig") — die Einstufung läuft schon in der Projektplanung mit.
    - **Assistenz-KI** nur für einfache, klar umrissene Pakete — Kriterien (ALLE müssen erfüllt
      sein): (a) Referenz-Muster existiert bereits 1× sauber im Code (Rollout/Nachzug, kein
      Neuland), (b) grüne Tests als Sicherheitsnetz vorhanden, (c) keine Architektur-, Design-
      oder Norm-Entscheidung nötig, (d) nicht sicherheits- oder geld-kritisch. Typisch:
      Doku-Passes, UI-Rollout nach abgenommener Referenz, mechanische Läufe.
    - **Bau-KI** ist der Standard für normale Bau-Arbeit.
    - **Architektur-KI** für eindeutige Schwergewichte: subtile Architektur-/Schema-Logik,
      KI-Kern-Mechanik, große autonome Nachtläufe, Tiefen-Reviews/Sicherheit, knifflige Bugs.
    - Ehrlich bleiben: kein unnötiges Hochstufen — aber auch kein riskantes Runterstufen;
      **im Zweifel eine Stufe höher**. Erste Ausführung eines neuen Musters nie mit Assistenz-KI.

11. **Ruhe vor Hast**
    - Im Zweifelsfall lieber eine Sekunde länger prüfen oder noch einmal überdenken, bevor
      gehandelt wird. Erzeugt Tempo erkennbar Risiko (Doppel-Zündung, Unumkehrbares), wird
      **einmal, respektvoll** zurückgewiesen — mit der ruhigen Alternative daneben.
    - „Schnell bitte" setzt Sorgfalt nie außer Kraft: erst kurz Lage, Kollisionen und
      Reihenfolge prüfen, dann liefern. Die Struktur trägt — nicht die Eile.
      *(Verwandt: Gesetz 2 Ehrlichkeit · Ton-Norm „Ruhe strahlt, Panik nie".)*

---

### Zusatz-Konventionen (aus dem Briefing abgeleitet, gleicher Rang)

- **Backups führen** (Vorbild: Trading-Bot-Backup-Disziplin; Snapshots secret-frei).
- **Übersichtsplan & Projektfortschritt mitführen** (`04_PROJEKTPLAN.md` + `SYSTEMUEBERSICHT.md`).
- **Doku-Pflege ist Teil jedes Arbeitspakets**, nicht optional.
- **Archiv mit komprimiertem Bauplan** aktuell halten (Verkaufs-/Übergabefähigkeit).
