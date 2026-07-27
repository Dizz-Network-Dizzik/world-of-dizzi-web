"""CSP voll-strikt (Nonce, docs/37): GET / liefert eine strikte CSP mit Per-
Request-Nonce (KEIN unsafe-inline im script-src) und nonce'd inline <script>; das
Frontend trägt KEINE inline-Event-Handler mehr (alles über DzActions-Delegation).
Regressions-Wächter: ein versehentlich wieder eingefügtes onclick= würde unter der
strikten CSP still tot sein — dieser Test fängt es."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from kommapp.main import build_app

_INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_get_root_liefert_strikte_nonce_csp(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        r = client.get("/")
        assert r.status_code == 200
        csp = r.headers.get("content-security-policy", "")
        script = next((p for p in csp.split(";") if p.strip().startswith("script-src")), "")
        assert "'nonce-" in script and "unsafe-inline" not in script, script
        # der ausgelieferte inline-<script> trägt den passenden Nonce
        nonce = re.search(r"script-src[^;]*'nonce-([^']+)'", csp).group(1)
        assert f'<script nonce="{nonce}"' in r.text


def test_keine_inline_event_handler_mehr():
    html = _INDEX.read_text(encoding="utf-8")
    treffer = re.findall(r"\son[a-z]+=[\"']", html)
    assert treffer == [], f"inline-Handler übrig (CSP-strikt blockt sie): {treffer}"
    # die Delegation muss da sein (sonst wären die Aktionen tot)
    assert "data-dz-act=" in html
