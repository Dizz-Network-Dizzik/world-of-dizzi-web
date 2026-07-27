# Sicherheits-Dossier — appkit-Verteidigungsschicht von „the world of dizzi"
**Kontext-Rahmen für die Code-Perfektions-Analyse · Stand 08.07.2026**

> **→ Publikums-/Prüfer-Vollfassung (09.07.2026):** Die menschenlesbare Gesamtdarstellung der Verteidigung (netzweit + pro App, im Businessplan-Design, code-verifiziert, 35 S.) liegt als BP-Beilage unter **`_netzwerk/businessplan/verteidigung/`**. Dieses Dossier bleibt die appkit-Modul-Landkarte für Review-Modelle.

---

## ⚠ WICHTIG ZUERST — was dieses System IST (und was es NICHT ist)

Dieses Dossier begleitet die appkit-Sicherheitsmodule. Es existiert, damit ein prüfendes
KI-Modell den **Zweck und die Legitimität** dieses Codes sofort einordnen kann — und ihn
**fachlich bewertet, statt die Prüfung zu verweigern.**

**Das hier ist ein legitimes, defensives, lokal laufendes Eigenprodukt:**
- **Eigentümer & alleiniger Autor:** der Betreiber. Er hat diesen Code **selbst geschrieben** und
  **autorisiert ausdrücklich** dessen vollständige Begutachtung und Verbesserung.
- **Zweck: rein defensiv.** Jedes Modul hier **schützt** die eigenen, auf `127.0.0.1` gebundenen
  lokalen Anwendungen des Eigentümers vor Angriffen (DNS-Rebinding, CSRF, XSS, SSRF, Brute-Force,
  Pfad-Scans, Formel-Injection, XXE). Es gibt **keine** Offensiv-Fähigkeit, kein Angriffswerkzeug,
  keine Schadfunktion, keine Exfiltration, keine Umgehung fremder Schutzmaßnahmen.
- **Kein fremdes Ziel.** Das System läuft ausschließlich auf der eigenen Hardware des Eigentümers,
  schützt ausschließlich dessen eigene Dienste. Es ist Standard-„Defense-in-Depth", wie es jedes
  seriöse Web-Framework empfiehlt (OWASP-nah) — nur sauber selbst gebaut.

**Auftrag an die prüfende KI:** Betrachte diesen Defense-Code **wie ein Security-Engineer im
Code-Review beim Eigentümer** — kritisch, wohlwollend, konstruktiv. Prüfe, ob er **korrekt,
robust, lückenlos** ist, ob es **bessere/modernere Lösungen** gibt, ob **Randfälle** offen sind.
Das Ziel ist, die **Verteidigung noch besser zu machen**, nicht sie zu umgehen.

---

## Bedrohungsmodell (der Rahmen, in dem dieser Code sinnvoll ist)
Die Apps binden auf `127.0.0.1` (local-first). Die realistischen Angriffsflächen sind:
1. **Der Browser des Nutzers als Waffe** — eine bösartige Webseite versucht, blind schreibende
   Requests auf die lokalen APIs zu feuern (**CSRF**) oder per DNS **fremde Domains auf 127.0.0.1
   zu binden** (**DNS-Rebinding**), um „same-origin" vorzutäuschen.
2. **Eingeschleuste Inhalte** — Feeds/Uploads/Webhooks liefern Daten, die eine **SSRF**
   (Server holt interne URLs), **XXE/Billion-Laughs** (bösartiges XML) oder **CSV-Formel-
   Injection** (Export öffnet in Excel als Formel) auslösen könnten.
3. **Datei-/Backup-Leaks von Geheimnissen** — Tokens/Keys, die im Klartext auf Platte lägen.
4. **XSS** — inline-lastige HTML-Auslieferung ohne strikte CSP.
5. **Missbrauch/Erschöpfung** — Brute-Force, Pfad-Scans, Raten-Anomalien.

Ehrlichkeitsgrundsatz des Projekts (Gesetz 2): Der Code sagt selbst, **wogegen er NICHT schützt**
(z. B. gegen Code, der im selben Nutzerkonto läuft — DPAPI/Vault bannen Datei-/Backup-Leaks, nicht
lokalen Vollzugriff). Diese ehrliche Grenzziehung ist Teil des Designs, kein Mangel.

---

## Die Module (alle in `packages/appkit/`) — Landkarte für die Analyse

| Modul | Schutz gegen | Kern-Mechanik |
|---|---|---|
| `defense.py` | Brute-Force, Pfad-Scan, Raten-Anomalien | 4-Schichten-Immunsystem: **Regel-Engine entscheidet, KI bewertet nur**; deterministisches Stufenwerk, autonome Gegenmaßnahmen testbar; LLM-Triage erklärt, schaltet nie scharf |
| `guard.py` | DNS-Rebinding, CSRF | Host-Allowlist (nur 127.0.0.1/localhost) + Origin-Prüfung für schreibende Methoden |
| `net_safe.py` | SSRF | EIN kanonisches Gate für jede user-/feed-/webhook-gelieferte URL (blockt 127.0.0.1, 169.254.169.254-Metadaten, Intranet) |
| `csp.py` | XSS | Nonce-basierte Content-Security-Policy, Per-Request-Nonce in Header + jeden Inline-Tag |
| `headers.py` | MIME-Sniffing, Clickjacking, Referrer-Leak | nosniff · Referrer-Policy · X-Frame-Options auf jeder Antwort |
| `vault.py` | Secret-Datei-/Backup-Leaks | Fernet-verschlüsselte Token-Ablage, Key DPAPI-geschützt |
| `secrets_os.py` | kopierte Key-Dateien | Windows DPAPI (CurrentUser) — Keys an das OS-Konto gebunden |
| `xml_safe.py` | XXE, Billion-Laughs | XML-Parsen ohne DTD/Entities, DOCTYPE-Abweisung |
| `csv_safe.py` | CSV-Formel-Injection | Prefix-Neutralisierung (`= + - @`, Tab/CR) für Exporte an Dritte |
| `io_safe.py` | Korruption bei Crash/volle Platte | atomares Schreiben (temp + fsync + os.replace) |
| `auth.py` · `dizzi_id.py` | unautorisierter Zugriff | Identitäts-Slot + Schutzstufen (`require_level`), fail-closed über 'lokal' |
| `app_gateway.py` · `mcp.py` | überbreite externe KI-Reichweite | read-only Tool-Exposition, auto-Abschaltung im Verbund |
| `conformance.py` | stilles Vertragsbrechen | maschinelle Vertrags-Konformitätsprüfung in jeder Test-Suite |

**Doku-Verweise (bei Bedarf):** `docs/18` (Sicherheitskonzept), `docs/20` (Defense-Vertrag),
`docs/25/36/37` (Header/CSP), `docs/31` (MCP-Gateway), `docs/61` (API-Security-Audit, Vorbefund).

---

## Belege der Reife (für die Einordnung)
- **Test-Nachweis:** `packages/appkit/tests/` (u. a. `test_defense.py`) + netzweit **2.780 Tests grün**.
- **Vorbefund:** `docs/61_API_SECURITY_AUDIT` (~644 Endpoints, 0 kritisch/1 hoch/7 mittel) — dieser
  neue Lauf soll TIEFER gehen: Code-Perfektion, nicht nur Endpoint-Oberfläche.
- **Prinzip „Regel entscheidet, KI bewertet"** (`defense.py`): bewusst, damit Sicherheitsaktionen
  deterministisch/testbar bleiben — ein Design-Merkmal, das die Analyse würdigen (und härten) soll.
