# 37 · CSP VOLL-STRIKT — Recipe je App (Inline-Handler → Event-Delegation)

> **★ STATUS 21.06.: ✅ NETZWERKWEIT KOMPLETT + LIVE (alle 8 Apps).** Alle App-Chats haben ihre
> Inline-Handler einheitlich auf `data-dz-act` (DzActions) umgestellt (0 echte Inline-Event-Attribute,
> Kit/appkit überall = master, kein Sonderweg). Bereinigt durch den World-Chat: (a) 3 Apps (news/finanzen/
> creator) hatten `csp_strikt=False` stehen lassen → auf `True` geflippt; (b) **appkit-Bug behoben (1.24.1):**
> `build_csp` ließ im Strikt-Modus `style-src` auf Nonce laufen → blockierte inline `style="…"`-Attribute →
> Layout-Bruch (vom finanzen-Chat empirisch belegt + korrekt-vorsichtig auf Baseline geblieben). **Fix:
> style-src behält IMMER `'unsafe-inline'`; nur script-src ist nonce-strikt** (Google-strict-csp-Muster).
> Alle 8 auf appkit 1.24.1, alle Suiten grün, alle neu gestartet → script-src nonce, style-src unsafe-inline,
> Health-Watch 10/10. archiv/admin/finanzen browser-verifiziert (0 CSP-Verstöße, inline-styles greifen).


> **Ziel:** von der Baseline-CSP (`script-src 'self' 'unsafe-inline'`) auf **voll-strikt**
> (`script-src 'self' 'nonce-…'` OHNE `unsafe-inline`) — der Browser führt dann nur noch
> Skripte mit dem Server-Nonce aus, **inline-Event-Handler (`onclick=…`) werden blockiert**.
> Darum müssen sie vorher auf Event-Delegation umgestellt werden.
>
> **Referenz/Beweis:** `archiv` (Dizz Memory) ist komplett umgestellt + live verifiziert
> (`02dd159`): 0 `onclick`, 4 `data-dz-act`, 0 CSP-Verstöße, 192 Tests grün. Genau diesem
> Muster folgen. **World-Chat-Vorarbeit ist erledigt** (steht in jeder App bereit):
> appkit **1.24.0** (`csp.serve_html_mit_csp` + `create_app(csp_strikt=…)`) + **DzActions**
> im Kit (`collapse.js`, netzwerkweit vendort, 0 Drift).

## Trading Bot (Dizz Trading) — Sonderfall, eigener Stack
TB ist KEIN appkit-`create_app` (eigenes `backend.app.main:app`, appkit 1.20.0 ohne csp.py,
monolithische `index.html` mit **104 inline-Handlern, teils komplex** [`event.preventDefault();…`,
Bedingungen], lädt **Google-Fonts extern**). **✅ STUFE 1 (Baseline) LIVE 21.06.** (`52721c0`): TB-native
Security-Header + Baseline-CSP-Middleware in `main.py` (gleiche Policy wie das Netzwerk + `style-src`/
`font-src` für `fonts.googleapis.com`/`gstatic.com`). TB hatte zuvor GAR keine Header. 343 Tests grün,
Browser 0 CSP-Verstöße, Flotte 51/51 nach Neustart. **OFFEN: Voll-strikt** = 104 Handler (viele komplex,
ohne DzActions-Kit) → Delegation/Dispatcher + Nonce; großer, sorgfältiger Einzelschritt (Finanz-Dashboard).

## Was zu tun ist (pro App, im EIGENEN App-Repo)
1. **Inventar:** `grep -noiE 'on(click|change|input|keydown|submit|mouseover|mousedown)=' static/index.html`
   (auch die in JS-Template-Strings erzeugten zählen — alle).
2. **Jeden Inline-Handler auf `data-dz-act` umstellen** (DzActions-Delegation, schon im Kit):
   - `onclick="fn('x')"`  →  `data-dz-act="fn" data-dz-arg="x"`
   - `onchange="fn(v)"`   →  `data-dz-act="fn" data-dz-on="change" data-dz-arg="…"`
   - **Kein Arg:** `onclick="fn()"` → `data-dz-act="fn"`.
   - Die Funktion bleibt global (`window.fn`) ⇒ der Dispatcher ruft sie als `fn(arg, el, event)`.
   - **Mehr-Argument-/komplexe Handler:** entweder einen kleinen Wrapper global definieren und den
     aufrufen, ODER `DzControls.registerAction("name", (arg,el,ev)=>{…})` registrieren und mehrere
     `data-*`-Attribute am Element lesen (`el.dataset.…`). NICHT `data-dz-arg` mit JS-Code füllen
     (kein eval — das verfehlt den CSP-Zweck).
   - `javascript:`-URLs (`href="javascript:…"`) ebenfalls entfernen (→ Button + data-dz-act).
   - **Inline `style="…"` darf bleiben** — style-src behält `unsafe-inline` (Stil-Attribute sind
     kein Skript-Vektor; voll-strikt meint script-src).
3. **`GET /`-Route auf Nonce-Auslieferung:** `from fastapi import Request` (falls fehlt) +
   ```python
   @router.get("/", include_in_schema=False)
   def startseite(request: Request):
       from appkit.csp import serve_html_mit_csp
       return serve_html_mit_csp(request, <pfad-zur-index.html>)
   ```
   (ersetzt das `FileResponse(index.html)`; injiziert den Nonce in inline `<script>`/`<style>`).
4. **`create_app(...)`:** `csp_strikt=False` → **`csp_strikt=True`** (csp_mode bleibt `"enforce"`).
5. **Verifizieren (Scratch-Port, Live nie stören):**
   - HTTP: `script-src 'self' 'nonce-…'` (KEIN `unsafe-inline`); inline `<script nonce="…">`;
     **0 verbleibende `onclick=`**.
   - Browser (preview_eval/_console_logs): **0 CSP-Verstöße**, Nonce-Skripte laufen, und **JEDE
     Interaktion durchklicken** (alle ehemaligen Handler!) — nichts darf tot sein.
   - **venv-pytest grün.**
6. **Commit** im App-Repo. Der **gegatete Live-Neustart** läuft über den World-Chat (Nutzer-Go).

## Leitplanken
- `appkit/` + `ui-kit/` (inkl. `collapse.js`/DzActions) sind **READ-ONLY** — NICHT ändern; sie sind
  schon vendort. Nur `static/index.html` + die `GET /`-Route + den `create_app`-Aufruf anfassen.
- venv `C:\Dizzik\data\tools\venv`; Scratch-Port + temp Daten-Dir; preview_snapshot/_eval.
- Sorgfalt vor Tempo: **jede** ehemalige Inline-Aktion muss nachweislich noch funktionieren
  („dass keine Scheiße passiert").

## Handler-Umfang je App (Stand 20.06., Orientierung)
finanzen ~82 · admin ~77 · kommunikation ~74 · creator ~72 · health ~47 · news ~44 · social-media ~42.
(archiv = 4 ✅ erledigt/Referenz.) Je höher die Zahl, desto eher lohnt Container-Event-Delegation
für dynamische Listen (ein `data-dz-act` am Button in der Zeile + `data-dz-arg`/`data-*` für die ID).
