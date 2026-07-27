"""Übergabe-Helfer (Phase 2, docs/26): App → Core-Relay.
Korrekter Umschlag, richtige Ziel-URL, best-effort (wirft nie)."""

from __future__ import annotations

from appkit import querverbindung


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}

    def json(self):
        return self._p


def test_archiviere_baut_umschlag_und_ruft_core():
    erfasst = {}

    def fake_post(url, json):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "archiviert", "id": "n1"})

    out = querverbindung.archiviere(
        "news", "EZB hält Zinsen", "Body", quelle="https://news/ezb",
        tags=["finanzen"], ref="news:1", strom="wochenbericht", explizit=True,
        core_url="http://core", http_post=fake_post)

    assert out == {"ok": True, "status": "archiviert", "id": "n1"}
    assert erfasst["url"] == "http://core/api/querverbindung/memory"
    j = erfasst["json"]
    assert j["app"] == "news" and j["titel"] == "EZB hält Zinsen"
    assert j["quelle"] == "https://news/ezb" and j["ref"] == "news:1"
    assert j["tags"] == ["finanzen"] and j["sensibel"] is False
    assert j["strom"] == "wochenbericht" and j["explizit"] is True


def test_archiviere_sensibel_und_anderes_ziel():
    erfasst = {}

    def fake_post(url, json):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True})

    querverbindung.archiviere("health", "Blutdruck", "…", ziel="memory",
                              sensibel=True, core_url="http://core", http_post=fake_post)
    assert erfasst["url"].endswith("/api/querverbindung/memory")
    assert erfasst["json"]["sensibel"] is True


def test_archiviere_best_effort_wirft_nie():
    def boom(url, json):
        raise RuntimeError("kein Core")

    out = querverbindung.archiviere("news", "t", "i", core_url="http://core", http_post=boom)
    assert out["ok"] is False and "fehler" in out


def test_archiviere_relay_fehlerstatus():
    out = querverbindung.archiviere("news", "t", "i", core_url="http://core",
                                    http_post=lambda url, json: _Resp(503, {}))
    assert out["ok"] is False and "503" in out["fehler"]


# ===================== V5: sende_termin (zweiter Vertragstyp, Kalender) ===========
def test_sende_termin_baut_umschlag_und_ruft_kalender_relay():
    erfasst = {}

    def fake_post(url, json):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "eingetragen", "id": "t1"})

    out = querverbindung.sende_termin(
        "kommunikation", "Kickoff", "2026-07-01T15:00", ende="2026-07-01T16:00",
        ort="Jitsi", beschreibung="Agenda", quelle="komm:konv:42", ref="komm:termin:42",
        core_url="http://core", http_post=fake_post)

    assert out == {"ok": True, "status": "eingetragen", "id": "t1"}
    assert erfasst["url"] == "http://core/api/querverbindung/admin/kalender"  # Default-Ziel Admin (Merge docs/28/29)
    j = erfasst["json"]
    assert j["app"] == "kommunikation" and j["titel"] == "Kickoff"
    assert j["beginn"] == "2026-07-01T15:00" and j["ende"] == "2026-07-01T16:00"
    assert j["ort"] == "Jitsi" and j["ref"] == "komm:termin:42" and j["quelle"] == "komm:konv:42"


def test_sende_termin_best_effort_wirft_nie():
    def boom(url, json):
        raise RuntimeError("kein Core")

    out = querverbindung.sende_termin("kommunikation", "t", "2026-07-01T10:00",
                                      core_url="http://core", http_post=boom)
    assert out["ok"] is False and "fehler" in out


# ===================== Rück-Lese: memory_suche (das „↔", docs/26 §10.1) ===========
def test_memory_suche_baut_relay_url_und_params():
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "treffer": [{"titel": "EZB", "auszug": "…"}],
                           "anzahl": 1})

    out = querverbindung.memory_suche("ezb zinsen", limit=5,
                                      core_url="http://core", http_get=fake_get)
    assert out["ok"] is True and out["anzahl"] == 1
    assert erfasst["url"] == "http://core/api/querverbindung/memory/suche"
    assert erfasst["params"] == {"q": "ezb zinsen", "semantisch": "0", "limit": 5}


def test_memory_suche_semantisch_schaltet_um():
    erfasst = {}

    def fake_get(url, params):
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "treffer": [], "anzahl": 0})

    querverbindung.memory_suche("geldanlage", semantisch=True,
                                core_url="http://core", http_get=fake_get)
    assert erfasst["params"]["semantisch"] == "1"


def test_memory_suche_best_effort_leere_treffer():
    def boom(url, params):
        raise RuntimeError("kein Core")

    out = querverbindung.memory_suche("x", core_url="http://core", http_get=boom)
    assert out["ok"] is False and out["treffer"] == [] and "fehler" in out


def test_memory_suche_relay_fehlerstatus_leer():
    out = querverbindung.memory_suche("x", core_url="http://core",
                                      http_get=lambda url, params: _Resp(503, {}))
    assert out["ok"] is False and out["treffer"] == [] and "503" in out["fehler"]


def test_verknuepfe_baut_umschlag_und_ruft_core():
    erfasst = {}

    def fake_post(url, json):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "verknuepft", "id": "v1"})

    out = querverbindung.verknuepfe(
        "finanzen", "finanzen:buchung:42", "REWE 12,30", "admin:dokument:7",
        notiz="Beleg", core_url="http://core", http_post=fake_post)
    assert out["ok"] is True and out["status"] == "verknuepft"
    assert erfasst["url"] == "http://core/api/querverbindung/admin/verknuepfung"
    assert erfasst["json"]["von_ref"] == "finanzen:buchung:42"
    assert erfasst["json"]["ziel_ref"] == "admin:dokument:7"
    assert erfasst["json"]["von_app"] == "finanzen" and erfasst["json"]["notiz"] == "Beleg"


# ===================== A5: Bereichs-Querverbindungs-Helfer (docs/34) ================
def test_finanzspur_holen_baut_relay_und_params():
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "finanzspur": {"saldo": 38000}})

    out = querverbindung.finanzspur_holen("geschaeft-x", jahr=2026,
                                          core_url="http://core", http_get=fake_get)
    assert out["ok"] is True and out["finanzspur"]["saldo"] == 38000
    assert erfasst["url"] == "http://core/api/querverbindung/finanzen/finanzspur"
    assert erfasst["params"] == {"kontext": "geschaeft-x", "jahr": 2026}


def test_finanzspur_holen_best_effort_wirft_nie():
    def boom(url, params):
        raise RuntimeError("kein Core")

    out = querverbindung.finanzspur_holen("x", core_url="http://core", http_get=boom)
    assert out["ok"] is False and out["finanzspur"] == {} and "fehler" in out


def test_bereich_social_holen_baut_relay_und_params():
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "social": {"geplant": 3}})

    out = querverbindung.bereich_social_holen("geschaeft-x",
                                              core_url="http://core", http_get=fake_get)
    assert out["ok"] is True and out["social"]["geplant"] == 3
    assert erfasst["url"] == "http://core/api/querverbindung/management/bereich-social"
    assert erfasst["params"] == {"kontext": "geschaeft-x"}


def test_bereich_social_holen_fehlerstatus_leer():
    out = querverbindung.bereich_social_holen(
        "x", core_url="http://core", http_get=lambda url, params: _Resp(503, {}))
    assert out["ok"] is False and out["social"] == {} and "503" in out["fehler"]


def test_kategorie_holen_baut_relay_und_params():
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "notizen": [{"titel": "Vorlesung 1"}], "anzahl": 1})

    out = querverbindung.kategorie_holen("Studium Informatik", limit=5,
                                         core_url="http://core", http_get=fake_get)
    assert out["ok"] is True and out["anzahl"] == 1
    assert erfasst["url"] == "http://core/api/querverbindung/memory/kategorie"
    assert erfasst["params"] == {"ordner": "Studium Informatik", "limit": 5}


def test_kategorie_holen_best_effort_wirft_nie():
    def boom(url, params):
        raise RuntimeError("kein Core")

    out = querverbindung.kategorie_holen("x", core_url="http://core", http_get=boom)
    assert out["ok"] is False and out["notizen"] == [] and "fehler" in out


# ===================== BER-1: kanon-Durchreichung (docs/67 §3.3) ===================
def test_finanzspur_holen_reicht_kanon_zusaetzlich_durch():
    """Gesetzt ⇒ ``kanon`` zusätzlich zu ``kontext``; leer ⇒ Param entfällt (byte-gleich
    zum kontext-only-Verhalten — additiv/rückwärtskompatibel)."""
    erfasst = {}

    def fake_get(url, params):
        erfasst["params"] = dict(params)
        return _Resp(200, {"ok": True, "finanzspur": {}})

    querverbindung.finanzspur_holen("nagelfabrik", jahr=2026, kanon="K-1",
                                    core_url="http://core", http_get=fake_get)
    assert erfasst["params"] == {"kontext": "nagelfabrik", "jahr": 2026, "kanon": "K-1"}
    querverbindung.finanzspur_holen("nagelfabrik", jahr=2026,
                                    core_url="http://core", http_get=fake_get)
    assert "kanon" not in erfasst["params"]              # leer ⇒ unverändert


def test_bereich_social_holen_reicht_kanon_durch():
    erfasst = {}

    def fake_get(url, params):
        erfasst["params"] = dict(params)
        return _Resp(200, {"ok": True, "social": {}})

    querverbindung.bereich_social_holen("uni-bot", kanon="K-2",
                                        core_url="http://core", http_get=fake_get)
    assert erfasst["params"] == {"kontext": "uni-bot", "kanon": "K-2"}
    querverbindung.bereich_social_holen("uni-bot", core_url="http://core", http_get=fake_get)
    assert erfasst["params"] == {"kontext": "uni-bot"}   # kein kanon-Param


def test_kategorie_holen_reicht_kanon_durch():
    erfasst = {}

    def fake_get(url, params):
        erfasst["params"] = dict(params)
        return _Resp(200, {"ok": True, "notizen": [], "anzahl": 0})

    querverbindung.kategorie_holen("Studium Info", limit=5, kanon="K-3",
                                   core_url="http://core", http_get=fake_get)
    assert erfasst["params"] == {"ordner": "Studium Info", "limit": 5, "kanon": "K-3"}
    querverbindung.kategorie_holen("Studium Info", limit=5,
                                   core_url="http://core", http_get=fake_get)
    assert "kanon" not in erfasst["params"]


def test_kanon_status_holen_baut_relay_und_feed():
    """Wächter-Feed (docs/67 §3.3): richtige Ziel-URL, Feed 1:1 durchgereicht."""
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        return _Resp(200, {"ok": True, "bereiche": [{"id": "b1", "kanon_id": "K-1"}],
                           "anker_extra": {"ordner": ["Logs"]}})

    out = querverbindung.kanon_status_holen("memory", core_url="http://core", http_get=fake_get)
    assert erfasst["url"] == "http://core/api/querverbindung/memory/kanon-status"
    assert out["ok"] is True and out["bereiche"][0]["kanon_id"] == "K-1"
    assert out["anker_extra"]["ordner"] == ["Logs"]


def test_kanon_status_holen_best_effort_leer():
    """Offline ODER Relay (noch) nicht registriert (404) ⇒ ok=False, leere bereiche —
    der Wächter meldet die Kante dann 'unbekannt' (I-6), wirft nie."""
    out = querverbindung.kanon_status_holen(
        "finanzen", core_url="http://core",
        http_get=lambda url, params: (_ for _ in ()).throw(RuntimeError("weg")))
    assert out["ok"] is False and out["bereiche"] == [] and "fehler" in out
    out2 = querverbindung.kanon_status_holen(
        "management", core_url="http://core", http_get=lambda url, params: _Resp(404, {}))
    assert out2["ok"] is False and out2["bereiche"] == []


def test_verknuepfe_best_effort_wirft_nie():
    def boom(url, json):
        raise RuntimeError("kein Core")

    out = querverbindung.verknuepfe("finanzen", "a", "t", "b",
                                    core_url="http://core", http_post=boom)
    assert out["ok"] is False and "fehler" in out


def test_belege_holen_baut_relay_url_und_params():
    erfasst = {}

    def fake_get(url, params):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"ok": True, "belege": [{"ref": "admin:dokument:7"}]})

    out = querverbindung.belege_holen("admin", q="rech", limit=20,
                                      core_url="http://core", http_get=fake_get)
    assert out["ok"] is True and out["belege"][0]["ref"] == "admin:dokument:7"
    assert erfasst["url"] == "http://core/api/querverbindung/admin/belege"
    assert erfasst["params"] == {"q": "rech", "limit": 20}


def test_belege_holen_best_effort_leer():
    out = querverbindung.belege_holen("admin", core_url="http://core",
                                      http_get=lambda url, params: _Resp(503, {}))
    assert out["ok"] is False and out["belege"] == [] and "fehler" in out


def test_verknuepfe_sendet_aktion_anlegen():
    erfasst = {}

    def fake_post(url, json):
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "verknuepft"})

    querverbindung.verknuepfe("finanzen", "finanzen:buchung:1", "t", "admin:dokument:7",
                              core_url="http://core", http_post=fake_post)
    assert erfasst["json"]["aktion"] == "anlegen"


def test_loese_verknuepfung_sendet_aktion_loesen():
    erfasst = {}

    def fake_post(url, json):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "geloest", "anzahl": 1})

    out = querverbindung.loese_verknuepfung("finanzen", "finanzen:buchung:1",
                                            "admin:dokument:7", core_url="http://core",
                                            http_post=fake_post)
    assert out["status"] == "geloest"
    assert erfasst["url"] == "http://core/api/querverbindung/admin/verknuepfung"
    assert erfasst["json"]["aktion"] == "loesen"
    assert erfasst["json"]["von_ref"] == "finanzen:buchung:1"
    assert erfasst["json"]["ziel_ref"] == "admin:dokument:7"


def test_loese_verknuepfung_best_effort():
    out = querverbindung.loese_verknuepfung("finanzen", "a", "b", core_url="http://core",
                                            http_post=lambda url, json: (_ for _ in ()).throw(RuntimeError()))
    assert out["ok"] is False and "fehler" in out


def test_memory_suche_timeout_wird_durchgereicht(monkeypatch):
    """H-Scan 17.06.: der Rück-Lese-Pfad ruft mit kurzem Timeout (2,5 s);
    der Default-Getter muss den Wert an httpx.get weiterreichen."""
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["timeout"] = timeout
        return _Resp(200, {"ok": True, "treffer": [], "anzahl": 0})

    monkeypatch.setattr(querverbindung.httpx, "get", fake_get)
    querverbindung.memory_suche("x", timeout=2.5, core_url="http://core")
    assert erfasst["timeout"] == 2.5
    # Default bleibt 5,0 s für explizite Suchen
    querverbindung.memory_suche("x", core_url="http://core")
    assert erfasst["timeout"] == 5.0


def test_belege_holen_sonderpraegung_ziel_nicht_erreichbar():
    """DRY-Kern P2.3: belege_holen behält bewusst die „Ziel nicht erreichbar"-
    Fehlerprägung (statt „Core …") — anders als die übrigen Relays. Diese
    Nicht-Uniformität muss der _relay_get-Refactor (fehler_prefix) erhalten."""
    def boom(url, params):
        raise OSError("weg")
    out = querverbindung.belege_holen("admin", core_url="http://core", http_get=boom)
    assert out["ok"] is False and out["belege"] == []
    assert "Ziel nicht erreichbar" in out["fehler"] and "Core" not in out["fehler"]


def test_post_helfer_timeout_wird_durchgereicht(monkeypatch):
    """Audit-Runde 4 / H-18: die POST-Helfer reichen ``timeout`` an httpx.post weiter
    (Default 5,0 s; der Storno-Pfad ruft loese_verknuepfung mit 2,5 s, damit ein OFFLINE
    Ziel die Antwort nicht verzögert)."""
    erfasst = {}

    def fake_post(url, json, timeout):
        erfasst["timeout"] = timeout
        return _Resp(200, {"ok": True, "status": "geloest", "anzahl": 0})

    monkeypatch.setattr(querverbindung.httpx, "post", fake_post)
    querverbindung.loese_verknuepfung("finanzen", "a", "admin:dokument:7",
                                      timeout=2.5, core_url="http://core")
    assert erfasst["timeout"] == 2.5
    # Default 5,0 s über alle vier POST-Helfer
    querverbindung.archiviere("news", "t", "i", core_url="http://core")
    assert erfasst["timeout"] == 5.0
    querverbindung.verknuepfe("finanzen", "a", "t", "admin:dokument:7", core_url="http://core")
    assert erfasst["timeout"] == 5.0
    querverbindung.sende_termin("kommunikation", "t", "2026-07-01T10:00", core_url="http://core")
    assert erfasst["timeout"] == 5.0
