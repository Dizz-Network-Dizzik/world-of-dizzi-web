from app import panels

EXPECTED_IDS = {
    "tradingbot", "memory", "news", "finanzen",
    "admin", "management", "creator", "systeminfo", "health",
    "kommunikation",  # Dizz Communication (Nachtrag 12.06.)
    # Dizz Plans + Dizz Leading in Dizz Admin verschmolzen (docs/28), eigenständige
    # :8211/:8219-Apps abgewickelt (19.06.). Dizz Music in die Creating-Suite eingeschmolzen.
    # Seed-ids = Manifest-ids: archiv→memory · social-media→management · buerokratie/leading→admin
}


def test_all_soll_panels_registered():
    ids = {m.id for m in panels.manifests()}
    assert ids == EXPECTED_IDS


def test_panel_status_konsistent_mit_contract():
    """Eine Soll-App ist 'aktiv', sobald sie in DIZZI_CONTRACT_APPS gebunden ist,
    sonst 'platzhalter' (robust gegen die jeweilige .env). Dizz Leading wurde am
    16.06. v1 gebaut + gebunden (vorher der letzte reine Platzhalter)."""
    gebunden = panels.contract_apps()
    for m in panels.manifests():
        if m.id in ("systeminfo", "tradingbot"):
            continue   # eigene Mechanik (Live-Stats/Legacy-Mapper)
        soll = "aktiv" if m.id in gebunden else "platzhalter"
        assert m.status == soll, f"{m.id}: status={m.status}, erwartet {soll}"


def test_unknown_panel():
    assert panels.stats_for("gibtsnicht") is None


def test_dizzi_status_folded_into_systeminfo():
    stats = panels.stats_for("systeminfo")
    dz = stats["dizzi"]
    assert dz["db_ok"] is True
    assert dz["uptime_s"] >= 0
    # systeminfo + tradingbot + alle live angebundenen Vertrags-Apps (.env)
    assert dz["panels_active"] == 2 + len(panels.contract_apps())
    assert dz["panels_total"] == len(EXPECTED_IDS)
    assert dz["version"]


def test_tradingbot_summary_mapping():
    raw = {
        "bots": 51, "running": 51, "trades_open": 37, "trades_closed": 1232,
        "wins": 485, "profit_abs": -228.07, "profit_pct": -0.45,
        "groups": {"scalping": {"bots": 19, "running": 19, "profit_pct": -0.86, "profit_abs": -162.78}},
    }
    out = panels._map_tradingbot_summary(raw)
    assert out["online"] is True
    assert out["bots"] == 51 and out["running"] == 51
    assert out["win_rate"] == round(485 / 1232 * 100, 1)
    assert out["groups"][0]["name"] == "scalping"
    assert out["url"]


def test_tradingbot_offline_is_graceful(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kein Trading Bot")
    monkeypatch.setattr(panels.httpx, "get", boom)
    panels._tb_cache["data"] = None  # Cache umgehen
    panels._tb_cache["ts"] = 0.0
    stats = panels.stats_for("tradingbot")
    assert stats["status"] == "ok"
    assert stats["online"] is False
    assert stats["url"]


def test_systeminfo_live_stats():
    stats = panels.stats_for("systeminfo")
    assert stats["status"] == "ok"
    assert 0 <= stats["cpu_pct"] <= 100
    assert stats["ram_total_gb"] > 0
    assert stats["disk_total_gb"] > 0


def test_systeminfo_static_details():
    stats = panels.stats_for("systeminfo")
    assert stats["cpu_cores"] > 0
    assert stats["cpu_threads"] >= stats["cpu_cores"]
    assert stats["cpu_name"]
    assert stats["os"]
    assert stats["hostname"]
    assert stats["data_dir"]
    assert stats["machine_uptime_s"] >= 0
