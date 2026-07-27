"""Defense-in-Depth: der MarkdownVault lässt KEIN Datei-I/O die Nutzer-Wurzel
verlassen — auch wenn ein Aufrufer (heute alle sanitisiert via rel_path_for/
_pfad_ok) je einen rohen ``..``-Pfad durchreichte. Spiegel der Tresor-
``is_relative_to``-Wache (Kern-Dauerschleife R2, Angreifer-Linse 23.06.2026)."""
from __future__ import annotations

import pytest

from archivapp.vault import MarkdownVault

U = "dizzi"


def test_write_verweigert_traversal(tmp_path):
    v = MarkdownVault(tmp_path / "vault")
    with pytest.raises(ValueError):
        v.write(U, "../../evil.md", {"id": "x"}, "boom")
    # Datei darf NICHT außerhalb der Nutzer-Wurzel entstanden sein
    assert not (tmp_path / "evil.md").exists()


def test_read_verweigert_traversal(tmp_path):
    v = MarkdownVault(tmp_path / "vault")
    with pytest.raises(ValueError):
        v.read(U, "../../secret.md")


def test_trash_und_entfernen_verweigern_traversal(tmp_path):
    v = MarkdownVault(tmp_path / "vault")
    with pytest.raises(ValueError):
        v.trash(U, "../../../etc/passwd")
    with pytest.raises(ValueError):
        v._entfernen(U, "../escape.md")


def test_normaler_pfad_funktioniert_weiter(tmp_path):
    v = MarkdownVault(tmp_path / "vault")
    rel = v.rel_path_for("Projekte/2026", "Meine Idee", "1a2b3c4d5e")
    v.write(U, rel, {"id": "1a2b3c4d5e", "titel": "Meine Idee"}, "Inhalt")
    gelesen = v.read(U, rel)
    assert gelesen is not None
    fm, body = gelesen
    assert body.strip() == "Inhalt"
    assert fm.get("titel") == "Meine Idee"
    assert (v.user_root(U) / rel).is_file()
