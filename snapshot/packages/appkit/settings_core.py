"""Account- & Settings-Core (Kernpaket K2) — typisiert, versioniert, 6 Kategorien.

Jede App bettet DASSELBE Muster ein (Föderation): ein deklariertes Schema aus
``SettingDef``-Einträgen in den sechs Kategorien (Fragerunde 2, docs/11 §6):
  konto · sicherheit · ki · vernetzung · darstellung · daten
Die Basis-Definitionen unten gelten für ALLE Apps; jede App ergänzt ihre
Domänen-Settings. Das Schema ist die Quelle für UI (Settings-Panel rendert
generisch aus /api/settings/schema) UND Validierung (PUT prüft Typ/Choice).

Regeln (Vertrag v1.1):
- Bekannte Schlüssel werden STRIKT validiert (Typ, Choices, Grenzen).
- Freier Namensraum ``x_…`` bleibt unvalidiert (interne/experimentelle Werte).
- Unbekannte Schlüssel außerhalb ``x_`` ⇒ 400 (Tippfehler-Schutz).
- ``sensitive=True``-Werte werden beim Lesen MASKIERT (write-only; echte
  Geheimnisse gehören in den Token-Tresor, appkit/vault.py).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Category = Literal["konto", "sicherheit", "ki", "vernetzung", "darstellung", "daten"]
CATEGORIES: tuple[str, ...] = ("konto", "sicherheit", "ki", "vernetzung",
                               "darstellung", "daten")
MASK = "•••"


class SettingDef(BaseModel):
    key: str
    category: Category
    type: Literal["bool", "int", "float", "str", "choice"]
    default: Any = None
    label: str = ""
    description: str = ""
    choices: list[str] | None = None     # Pflicht bei type='choice'
    min: float | None = None             # für int/float
    max: float | None = None
    sensitive: bool = False              # beim Lesen maskiert (write-only)

    def validate_value(self, value: Any) -> Any:
        """Prüft/normalisiert einen Wert; ValueError bei Verstoß."""
        t = self.type
        if t == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.key}: bool erwartet")
        elif t == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{self.key}: int erwartet")
        elif t == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{self.key}: Zahl erwartet")
            value = float(value)
        elif t == "str":
            if not isinstance(value, str):
                raise ValueError(f"{self.key}: str erwartet")
        elif t == "choice":
            if value not in (self.choices or []):
                raise ValueError(f"{self.key}: erlaubt sind {self.choices}")
        if t in ("int", "float"):
            if self.min is not None and value < self.min:
                raise ValueError(f"{self.key}: min {self.min}")
            if self.max is not None and value > self.max:
                raise ValueError(f"{self.key}: max {self.max}")
        return value


class SettingsSchema(BaseModel):
    """Versioniertes Gesamtschema einer App (Basis + Domänen-Ergänzungen)."""

    version: int = 1
    defs: list[SettingDef] = []

    def by_key(self) -> dict[str, SettingDef]:
        return {d.key: d for d in self.defs}

    def grouped(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
        for d in self.defs:
            out[d.category].append(d.model_dump())
        return out


def base_schema(sensitivity: str = "normal") -> list[SettingDef]:
    """Basis-Settings JEDER App (6 Kategorien). Sensible Apps (hoch/hoechst)
    starten mit KI-Routing 'lokal_only' — die lokal-first-Prämisse als Default."""
    ki_default = "lokal_only" if sensitivity in ("hoch", "hoechst") else "lokal_boost"
    return [
        SettingDef(key="anzeigename", category="konto", type="str", default="dizzi",
                   label="Anzeigename"),
        SettingDef(key="avatar_farbe", category="konto", type="choice",
                   choices=["cyan", "magenta", "gruen", "amber"], default="cyan",
                   label="Avatar-Farbe"),
        SettingDef(key="auto_logout_min", category="sicherheit", type="int",
                   default=720, min=5, max=10080, label="Auto-Logout (Minuten)"),
        SettingDef(key="stufe_sensibles", category="sicherheit", type="choice",
                   choices=["verifiziert", "hochsicher"], default="verifiziert",
                   label="Schutzstufe für sensible Bereiche"),
        SettingDef(key="reauth_sensibel", category="sicherheit", type="bool",
                   default=True, label="Re-Auth vor sensiblen Aktionen",
                   description="MFA erneut vor Export/Löschen/Echtgeld — auch in aktiver Session (docs/19 §3)"),
        SettingDef(key="login_benachrichtigung", category="sicherheit", type="bool",
                   default=True, label="Bei Anmeldungen benachrichtigen"),
        SettingDef(key="ki_routing", category="ki", type="choice",
                   choices=["lokal_only", "lokal_boost"], default=ki_default,
                   label="KI-Routing", description="lokal_only = nie Cloud-Boost"),
        SettingDef(key="ki_vorschlaege_aktiv", category="ki", type="bool",
                   default=True, label="KI-Vorschläge (HITL) aktiv"),
        SettingDef(key="dizzi_id_aktiv", category="vernetzung", type="bool",
                   default=True, label="Dizzi-ID-Anmeldung (SSO) aktiv"),
        SettingDef(key="event_push", category="vernetzung", type="bool",
                   default=False, label="Ereignisse an Dizzi melden (K4)"),
        SettingDef(key="mcp_freigegeben", category="vernetzung", type="bool",
                   default=True, label="MCP-Tools für Dizzi freigegeben"),
        SettingDef(key="cross_app_zugriff", category="vernetzung", type="choice",
                   choices=["fragen", "erlauben", "aus"], default="fragen",
                   label="Zugriff anderer Apps", description="A3: geregelter Cross-Zugriff"),
        # Per-App-MCP-Gateway (docs/31 §7) — in JEDER App im Einstellungsfenster steuerbar.
        # Die laufende App liest diese Schlüssel in appkit/app_gateway.py (build_app_gateway).
        SettingDef(key="mcp_gateway_mode", category="vernetzung", type="choice",
                   choices=["auto", "an", "aus"], default="auto",
                   label="MCP-Gate (eigener KI-Zugang)",
                   description="auto = nur im Standalone-Betrieb aktiv (im Verbund führt der "
                               "Core das zentrale Gateway) · an = immer · aus = nie. Externe "
                               "KI (Claude) erreicht darüber read-only die App-Werkzeuge."),
        SettingDef(key="mcp_gateway_freigabe_hochsicher", category="vernetzung", type="bool",
                   default=False, label="MCP: Hochsicher-Inhalte freigeben",
                   description="AUS (Standard): hochsicher-eingestufte Inhalte (verschlüsselte "
                               "Tresor-Dokumente, Echtgeld) sind für externe KI gesperrt. AN: "
                               "explizit freigegeben. Befristete Freigabe via POST /mcp/freigabe-hochsicher."),
        SettingDef(key="theme", category="darstellung", type="choice",
                   choices=["neon_dunkel", "neon_hell"], default="neon_dunkel",
                   label="Erscheinungsbild",
                   description="Legacy Hell/Dunkel-Schalter; orthogonal zu den K2.2-Design-Achsen unten"),
        # K2.2 — Übergreifendes Design-System (zwei GETRENNTE Achsen, docs/19 §2).
        # Werte sind 1:1 die <html>-Attribute des Token-Vertrags (ui-kit/tokens.css):
        # html[data-design] bzw. html[data-farbe] — KEINE Mapping-Schicht nötig.
        # Apps tragen die Wahl bisher über die freien x_design_vorlage/x_farb_schema;
        # ab appkit 1.3.0 hängen sie nur die Schlüssel auf diese typisierten Defs um.
        SettingDef(key="design_vorlage", category="darstellung", type="choice",
                   choices=["metall", "neon", "flach", "tag", "carbon", "pergament",
                            "synthwave", "lagune", "inferno", "kobalt"],
                   default="metall", label="Design-Vorlage",
                   description="K2.2 Achse 1 (Material/Form, 10): metall=Mattstahl (Default) · neon=Glas/Neon · flach=minimal-dunkel · tag=hell-kühl · carbon=OLED-Schwarz · pergament=hell-warm · synthwave/lagune/inferno/kobalt=farbige Grunddesigns. Token-Master: shared/dizz-tokens.css html[data-design]"),
        SettingDef(key="farb_schema", category="darstellung", type="choice",
                   choices=["cyan-magenta", "smaragd-gold", "violett-eis", "bernstein", "arktis",
                            "koralle", "limette", "feuer", "toxic", "voltage"],
                   default="cyan-magenta", label="Farbschema",
                   description="K2.2 Achse 2 (Palette, 10, unabhängig vom Design): cyan-magenta (Default) · smaragd-gold · violett-eis · bernstein · arktis · koralle · limette · feuer · toxic/voltage (Maximal-Intensität). Token-Master: shared/dizz-tokens.css html[data-farbe]"),
        SettingDef(key="sprache", category="darstellung", type="choice",
                   choices=["de", "en"], default="de", label="Sprache"),
        SettingDef(key="dichte", category="darstellung", type="choice",
                   choices=["kompakt", "normal"], default="normal",
                   label="Darstellungs-Dichte"),
        SettingDef(key="reduzierte_bewegung", category="darstellung", type="bool",
                   default=False, label="Reduzierte Bewegung",
                   description="Schaltet Spin-Physik/Drift ab (Zugänglichkeit)"),
        SettingDef(key="backup_aktiv", category="daten", type="bool", default=False,
                   label="Backups aktiv"),
        SettingDef(key="backup_verschluesselt", category="daten", type="bool",
                   default=False, label="Backups verschlüsseln (H8)"),
        SettingDef(key="aufbewahrung_tage", category="daten", type="int",
                   default=365, min=1, label="Aufbewahrung (Tage)"),
        SettingDef(key="export_format", category="daten", type="choice",
                   choices=["json", "csv"], default="json",
                   label="Daten-Export-Format (DSGVO)"),
    ]


def make_schema(extra: list[SettingDef] | None = None,
                sensitivity: str = "normal", version: int = 1) -> SettingsSchema:
    """Komplett-Schema einer App: Basis (nach Sensibilität) + Domänen-Defs."""
    defs = base_schema(sensitivity) + list(extra or [])
    keys = [d.key for d in defs]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(f"Doppelte Setting-Schlüssel: {sorted(dupes)}")
    return SettingsSchema(version=version, defs=defs)
