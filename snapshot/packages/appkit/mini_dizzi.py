"""Mini-Dizzi — die Sprach-/KI-Brücke jeder App (Vertrag 1.5, Nutzer-Auftrag 12.06.).

Kein eigenes Gehirn: Mini-Dizzi VERMITTELT nur. Es nimmt eine Frage (getippt
oder per Weckwort/Sprache) entgegen und reicht sie an die **app-eigene KI**
weiter — die App registriert dazu ihre Antwort-Funktion über ``set_app_ki``.
Hat eine App (noch) keine eigene KI, antwortet ein generischer lokaler
Ollama-Fallback mit App-Kontext (Manifest + Kachel-KPIs); ohne Ollama gibt es
einen EHRLICHEN Hinweis statt einer erfundenen Antwort.

**„Es lauscht immer nur EINER"** (Nutzer-Prinzip + löst den Mikrofon-Konflikt:
mehrere Prozesse können dasselbe Mikro nicht gleichzeitig öffnen):
- **Standalone** (App ohne Dizzi-Netzwerk): das Mini-Dizzi der App lauscht
  selbst (Weckwort „hey_dizzi") → STT → App-KI → Antwort.
- **Im Verbund** (Dizzi-ID aktiv): die App-Mini-Dizzis schalten ihr Mikro AUS;
  nur das zentrale „the world of dizzi" lauscht und leitet Anfragen über
  ``POST /api/ki/frage`` an die jeweilige App-KI weiter.
``lauscht_lokal()`` entscheidet das (Setting ``voice_modus`` auto|lokal|aus).

Das eigentliche Per-App-Mikrofon-Lauschen ist ein **vorbereiteter Slot**
(Gesetz 5): dieselbe Wake-Bridge wie im Core (`core/app/ai/wakeword.py`) wird
beim App-Frontend-Bau eingehängt — nur scharf, wenn ``lauscht_lokal()``. Die
Schnittstelle (App-KI-Slot + /api/ki + Verbund-Gating) steht hier schon ganz.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel

from .auth import DEFAULT_USER_ID
from .db import Database
from .manifest import AppManifest


class _FrageIn(BaseModel):
    # Modul-Ebene zwingend (PEP-563: lokale Modelle werden mit
    # `from __future__ import annotations` still zum Query-Parameter ⇒ 422).
    frage: str

# Eine App-KI bekommt die Frage (+ optionalen Kontext) und liefert Klartext
# ODER ein dict mit mindestens {"antwort": str}.
AppKi = Callable[[str], "str | dict[str, Any]"]

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_WORT = "hey_dizzi"

# JSON-Schema-Pflicht (Live-Lehre 12.06.: bloßes "json" wich bei großem Input
# auf fremde Formen aus → Grammatik erzwingen).
_FALLBACK_FORMAT = {
    "type": "object",
    "properties": {"antwort": {"type": "string"}},
    "required": ["antwort"],
}


class MiniDizzi:
    """Die Vermittlungs-Instanz einer App. Kennt die App (Manifest), ihre DB
    (für Settings) und — sobald registriert — ihre KI-Antwortfunktion."""

    def __init__(self, manifest: AppManifest, db: Database,
                 summary_fn: Callable[[], Any] | None = None,
                 ollama_url: str = OLLAMA_URL,
                 http_post: Callable[..., Any] | None = None,
                 memory_get: Callable[..., Any] | None = None) -> None:
        self.manifest = manifest
        self.db = db
        self.summary_fn = summary_fn
        self.ollama_url = ollama_url
        self._http_post = http_post
        self._memory_get = memory_get   # Rück-Lese-Injektion (Tests); None = echter Core-Relay
        self._app_ki: AppKi | None = None

    # --- App-KI-Slot (die App registriert hier ihr eigenes Gehirn) ----------
    def set_app_ki(self, fn: AppKi) -> None:
        self._app_ki = fn

    @property
    def app_ki_registriert(self) -> bool:
        return self._app_ki is not None

    # --- Vermittlung --------------------------------------------------------
    def frage(self, text: str) -> dict[str, Any]:
        """Frage → Antwort. App-KI bevorzugt; sonst lokaler Ollama-Fallback.
        Wirft NIE — eine kaputte KI darf die App nicht stören (ehrlicher Hinweis)."""
        text = (text or "").strip()
        if not text:
            return {"antwort": "Keine Frage erhalten.", "quelle": "leer"}
        if self._app_ki is not None:
            try:
                ergebnis = self._app_ki(text)
                if isinstance(ergebnis, dict):
                    antwort = str(ergebnis.get("antwort", "")).strip()
                else:
                    antwort = str(ergebnis).strip()
                if antwort:
                    return {"antwort": antwort, "quelle": "app_ki"}
            except Exception as e:  # App-KI defekt ⇒ Fallback statt Absturz
                return self._fallback(text, hinweis=f"App-KI-Fehler: {type(e).__name__}")
        return self._fallback(text)

    def _fallback(self, text: str, hinweis: str = "") -> dict[str, Any]:
        """Generische lokale Antwort (Ollama) mit App-Kontext. Ohne Ollama:
        ehrlicher Hinweis statt Halluzination."""
        kpis = []
        if self.summary_fn is not None:
            try:
                roh = self.summary_fn()
                kpis = roh if isinstance(roh, list) else getattr(roh, "kpis", []) or []
            except Exception:
                kpis = []
        def _kv(k: Any) -> str:
            if isinstance(k, dict):
                return f"{k.get('label', '?')}={k.get('value', '?')}"
            return f"{getattr(k, 'label', '?')}={getattr(k, 'value', '?')}"
        kontext = "; ".join(_kv(k) for k in kpis[:6]) or "keine Kennzahlen verfügbar"
        wissen = self._rueck_lese(text)   # Rück-Lese (docs/26 §4c): app-übergreifendes Memory-Wissen
        system = (
            f"Du bist Mini-Dizzi, die KI-Stimme der App '{self.manifest.brand}' "
            f"({self.manifest.name}). Antworte knapp und ehrlich auf Deutsch. "
            f"Aktuelle Kennzahlen der App: {kontext}.{wissen} "
            "Kennst du etwas nicht, sage das offen — nichts erfinden. "
            'Antworte NUR als JSON: {"antwort":"..."}.')
        out = self._ollama(system, text)
        if out is None:
            return {"antwort": "Meine lokale KI ist gerade nicht erreichbar "
                               "(Ollama). Frag es später erneut.",
                    "quelle": "kein_ollama"}
        antwort = str(out.get("antwort", "")).strip() or "(keine Antwort)"
        return {"antwort": antwort, "quelle": "fallback_ollama",
                **({"hinweis": hinweis} if hinweis else {})}

    def _rueck_lese(self, frage: str) -> str:
        """RÜCK-LESE (docs/26 §4c, „↔"): app-übergreifendes Wissen aus dem zentralen
        Archiv (Dizz Memory) für den Fallback-Prompt ergänzen — best-effort über den
        Core-Relay (``querverbindung.memory_suche``), **wirft NIE**. Gated per Setting
        ``ki_wissen_rueck_lese`` (Default an); Core/Memory offline ⇒ leer (die App
        antwortet ungestört aus ihrem eigenen Bestand). Liefert einen Prompt-Zusatz
        (führendes Leerzeichen) oder ``""``."""
        if not self.db.setting_get(DEFAULT_USER_ID, "ki_wissen_rueck_lese", True):
            return ""
        try:
            from .querverbindung import memory_suche
            # kurzer Timeout (2,5 s statt 5 s): ein träger Core/Memory darf die
            # KI-Antwort nicht hängen lassen — degradiert sauber zu leer (H-Scan 17.06.).
            res = memory_suche((frage or "").strip(), semantisch=False, limit=4,
                               timeout=2.5, http_get=self._memory_get)
            treffer = (res.get("treffer") or []) if res.get("ok") else []
        except Exception:
            treffer = []
        zeilen: list[str] = []
        for t in treffer[:4]:
            titel = str(t.get("titel") or t.get("name") or "Notiz").strip()
            auszug = str(t.get("auszug") or t.get("snippet") or t.get("inhalt") or "").strip()
            if titel:
                zeilen.append(f"{titel}: {auszug[:160]}" if auszug else titel)
        if not zeilen:
            return ""
        return (" Ergänzendes Wissen aus dem zentralen Archiv (Dizz Memory, app-übergreifend; "
                "nur verwenden, wenn zur Frage passend): " + " | ".join(zeilen) + ".")

    def _ollama(self, system: str, nutzer: str,
                modell: str = "qwen3:4b") -> dict[str, Any] | None:
        try:
            poster = self._http_post or (
                lambda url, json: __import__("httpx").post(url, json=json, timeout=90.0))
            r = poster(f"{self.ollama_url}/api/chat", json={
                "model": modell, "stream": False, "format": _FALLBACK_FORMAT,
                "options": {"temperature": 0.2},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": nutzer}]})
            if getattr(r, "status_code", 0) != 200:
                return None
            return json.loads((r.json().get("message") or {}).get("content", ""))
        except Exception:
            return None

    # --- Verbund-Gating („wer lauscht?") ------------------------------------
    def lauscht_lokal(self) -> bool:
        """Soll DIESE App selbst per Mikrofon lauschen?
        ``voice_modus``: auto (Standard) | lokal | aus.
        - aus  → nie.
        - lokal→ immer (auch im Verbund; bewusst-Override).
        - auto → nur STANDALONE: im Verbund (Dizzi-ID aktiv) lauscht das
                 zentrale „the world of dizzi", die App schweigt mikrofonseitig."""
        modus = str(self.db.setting_get(DEFAULT_USER_ID, "voice_modus", "auto"))
        if modus == "aus":
            return False
        if modus == "lokal":
            return True
        return self.manifest.auth.status != "aktiv"   # auto

    def wort(self) -> str:
        return str(self.db.setting_get(DEFAULT_USER_ID, "voice_wort", DEFAULT_WORT))

    def status(self) -> dict[str, Any]:
        return {
            "app": self.manifest.id,
            "app_ki_registriert": self.app_ki_registriert,
            "lauscht_lokal": self.lauscht_lokal(),
            "modus": str(self.db.setting_get(DEFAULT_USER_ID, "voice_modus", "auto")),
            "wort": self.wort(),
            "im_verbund": self.manifest.auth.status == "aktiv",
        }


def mini_dizzi_settings() -> list[Any]:
    """K2-Settings von Mini-Dizzi (Kategorie KI + Vernetzung)."""
    from .settings_core import SettingDef
    return [
        SettingDef(key="mini_dizzi_aktiv", category="ki", type="bool", default=True,
                   label="Mini-Dizzi (KI-Stimme der App)",
                   description="Sprach-/KI-Brücke: Fragen an die App-eigene KI (lokal, 0 €)"),
        SettingDef(key="ki_wissen_rueck_lese", category="ki", type="bool", default=True,
                   label="KI zieht Wissen aus dem Netzwerk (Memory)",
                   description="Rück-Lese (docs/26): Mini-Dizzi ergänzt Antworten um passende "
                               "Treffer aus dem zentralen Archiv (Dizz Memory). Aus = nur App-Bestand."),
        SettingDef(key="voice_modus", category="vernetzung", type="choice",
                   choices=["auto", "lokal", "aus"], default="auto",
                   label="Sprach-Lauschen dieser App",
                   description="auto = nur standalone selbst lauschen; im Verbund lauscht das zentrale Dizzi · lokal = immer selbst · aus"),
        SettingDef(key="voice_wort", category="vernetzung", type="str",
                   default=DEFAULT_WORT, label="Weckwort",
                   description="Aktivierungswort (Standard: hey_dizzi)"),
    ]


def mini_dizzi_router(mini: MiniDizzi) -> Any:
    """Endpoints der Sprach-/KI-Brücke. ``frage`` ist harmlos (nur lesen/
    antworten) ⇒ Stufe 'lokal' reicht; Wirkungs-Aktionen bleiben K4/HITL."""
    from fastapi import APIRouter, Depends
    from .auth import UserContext, current_user

    r = APIRouter(tags=["mini_dizzi"])

    @r.get("/api/ki/status")
    def ki_status(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return mini.status()

    @r.post("/api/ki/frage")
    def ki_frage(body: _FrageIn,
                 user: UserContext = Depends(current_user)) -> dict[str, Any]:
        if not mini.db.setting_get(DEFAULT_USER_ID, "mini_dizzi_aktiv", True):
            return {"antwort": "Mini-Dizzi ist in den Einstellungen deaktiviert.",
                    "quelle": "aus"}
        antwort = mini.frage(body.frage)
        mini.db.audit(user.user_id, "ki", "mini_dizzi_frage",
                      {"quelle": antwort.get("quelle")})
        return antwort

    return r
