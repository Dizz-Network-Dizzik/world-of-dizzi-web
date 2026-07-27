"""H-7 (appkit on_delete-Hook): die Konto-Löschung räumt Memorys EXTERNE
Artefakte mit — den RAG-Vektorindex + das Vault-Markdown-Verzeichnis des Nutzers
(DSGVO „weg = weg"; die DB-Soft-Delete-Konvention allein lässt beide liegen)."""

from __future__ import annotations

import hashlib
import math
import re
import time

from fastapi.testclient import TestClient

from appkit import auth
from appkit.auth import DEFAULT_USER_ID
from archivapp import main as am
from archivapp.rag import RagIndex
from archivapp.vault import MarkdownVault

_W = re.compile(r"\w+", re.UNICODE)
DIM = 64


def _fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * DIM
        for w in _W.findall((t or "").lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


def test_rag_remove_user_entfernt_nur_diesen_nutzer(tmp_path):
    rag = RagIndex(tmp_path / "rag.sqlite", embed_fn=_fake_embed, dim=DIM)
    rag.update_notiz("u1", "n1", "T1", "alpha bravo charlie")
    rag.update_notiz("u1", "n2", "T2", "delta echo foxtrot")
    rag.update_notiz("u2", "m1", "T3", "golf hotel india")
    assert rag.search("u1", "alpha")  # vorhanden

    n = rag.remove_user("u1")
    assert n >= 2
    assert rag.search("u1", "alpha") == []     # weg
    assert rag.search("u2", "golf")            # anderer Nutzer unberührt


def test_vault_purge_user_haert_und_ist_idempotent(tmp_path):
    v = MarkdownVault(tmp_path / "vault")
    v.write("u1", "Ordner/notiz__abc.md", {"id": "1", "titel": "X"}, "Body")
    v.write("u2", "andere__def.md", {"id": "2", "titel": "Y"}, "Body")
    assert v.user_root("u1").is_dir()

    assert v.purge_user("u1") is True
    assert not v.user_root("u1").exists()
    assert v.user_root("u2").is_dir()          # anderer Nutzer unberührt
    assert v.purge_user("u1") is False         # idempotent (nichts mehr da)


def test_account_loeschen_raeumt_vault_und_rag(tmp_path):
    """Integration: echte Konto-Löschung über den Vertrags-Endpoint feuert den
    on_delete-Hook ⇒ Vault-Verzeichnis + RAG-Vektoren des Nutzers sind danach weg."""
    auth.reset_identity_provider()
    app = am.build_app(data_dir=tmp_path, embed_fn=_fake_embed, rag_dim=DIM,
                       rag_autobuild=False, start_import_timer=False,
                       http_post=lambda url, json: None)
    try:
        with TestClient(app) as c:
            c.post("/api/notizen", json={"titel": "Geheim",
                   "inhalt": "vertraulicher Inhalt mit Findwort zebra."})
            vault = app.state.vault
            rag = app.state.rag
            assert vault.user_root(DEFAULT_USER_ID).is_dir()   # Vault-Datei da
            assert rag.search(DEFAULT_USER_ID, "zebra")        # RAG-Vektor da

            # Fresh-Stepup setzen, sonst ist /api/account/loeschen fail-closed (403)
            auth.set_identity_provider(lambda _r: auth.UserContext(
                DEFAULT_USER_ID, level="verifiziert", via="dizzi-id",
                auth_time=time.time() - 5))
            r = c.post("/api/account/loeschen").json()
            assert r["ok"] is True and r["artefakte_geraeumt"] is True

            assert not vault.user_root(DEFAULT_USER_ID).exists()  # Vault weg
            assert rag.search(DEFAULT_USER_ID, "zebra") == []     # RAG weg
    finally:
        auth.reset_identity_provider()


def test_account_loeschen_raeumt_notiz_links(tmp_path):
    """RA-3 (Recht-3.-Rotation, 28.06.): notiz_links (Wikilink-Graph; ``ziel_titel_norm``
    = die vom Nutzer verlinkten Notiz-Titel) hat KEIN deleted_at ⇒ soft_delete_user
    überspringt es. Der on_delete-Hook MUSS es hart räumen, sonst überlebt der
    personenbezogene Link-Graph die Konto-Löschung (gleiche Klasse wie archiv_regeln)."""
    auth.reset_identity_provider()
    app = am.build_app(data_dir=tmp_path, embed_fn=_fake_embed, rag_dim=DIM,
                       rag_autobuild=False, start_import_timer=False,
                       http_post=lambda url, json: None)
    db = app.state.db
    try:
        with TestClient(app) as c:
            # Notiz mit Wikilink ⇒ erzeugt eine notiz_links-Zeile (ziel_titel_norm).
            c.post("/api/notizen", json={"titel": "Quelle",
                   "inhalt": "Siehe [[Geheimes Zielthema]] fuer Details."})
            n = db.get_conn().execute(
                "SELECT COUNT(*) AS n FROM notiz_links").fetchone()["n"]
            assert n >= 1                                  # Link-Graph angelegt
            auth.set_identity_provider(lambda _r: auth.UserContext(
                DEFAULT_USER_ID, level="verifiziert", via="dizzi-id", auth_time=time.time() - 5))
            r = c.post("/api/account/loeschen").json()
            assert r["ok"] is True and r["artefakte_geraeumt"] is True
            n2 = db.get_conn().execute(
                "SELECT COUNT(*) AS n FROM notiz_links").fetchone()["n"]
            assert n2 == 0                                 # Link-Graph weg = weg
    finally:
        auth.reset_identity_provider()


def test_account_loeschen_raeumt_archiv_regeln(tmp_path):
    """DSGVO-Audit-Fund: archiv_regeln hat KEIN deleted_at ⇒ soft_delete_user überspringt
    es. Der on_delete-Hook muss die Archiv-Steuer-Regeln des Nutzers hart räumen."""
    auth.reset_identity_provider()
    app = am.build_app(data_dir=tmp_path, embed_fn=_fake_embed, rag_dim=DIM,
                       rag_autobuild=False, start_import_timer=False,
                       http_post=lambda url, json: None)
    db = app.state.db
    try:
        with TestClient(app) as c:
            c.put("/api/archiv-regeln", json={"app": "news", "strom": "x", "modus": "auto"})
            n = db.get_conn().execute("SELECT COUNT(*) AS n FROM archiv_regeln").fetchone()["n"]
            assert n >= 1
            auth.set_identity_provider(lambda _r: auth.UserContext(
                DEFAULT_USER_ID, level="verifiziert", via="dizzi-id", auth_time=time.time() - 5))
            r = c.post("/api/account/loeschen").json()
            assert r["ok"] is True and r["artefakte_geraeumt"] is True
            n2 = db.get_conn().execute("SELECT COUNT(*) AS n FROM archiv_regeln").fetchone()["n"]
            assert n2 == 0
    finally:
        auth.reset_identity_provider()
