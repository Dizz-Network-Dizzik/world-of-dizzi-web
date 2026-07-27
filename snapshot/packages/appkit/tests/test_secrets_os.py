"""H2: DPAPI-Schutz der Schlüsseldateien — Roundtrip, Bestands-Migration,
Vault-Integration."""

from __future__ import annotations

import sys

import pytest

from appkit import secrets_os
from appkit.vault import Vault

_windows = pytest.mark.skipif(sys.platform != "win32",
                              reason="DPAPI ist Windows-spezifisch")


@_windows
def test_roundtrip_geschuetzt(tmp_path):
    pfad = tmp_path / "geheim.bin"
    secrets_os.schreibe_geheim(pfad, b"streng geheim")
    assert pfad.read_bytes().startswith(secrets_os.MAGIC)
    assert b"streng geheim" not in pfad.read_bytes()
    assert secrets_os.lese_geheim(pfad) == b"streng geheim"


@_windows
def test_klartext_bestand_migriert(tmp_path):
    pfad = tmp_path / "alt.key"
    pfad.write_bytes(b"alter-klartext-schluessel")
    assert secrets_os.lese_geheim(pfad) == b"alter-klartext-schluessel"
    # Nach dem ersten Lesen liegt die Datei geschützt vor …
    assert pfad.read_bytes().startswith(secrets_os.MAGIC)
    # … und liefert weiterhin denselben Inhalt.
    assert secrets_os.lese_geheim(pfad) == b"alter-klartext-schluessel"


def test_fehlende_datei():
    from pathlib import Path
    assert secrets_os.lese_geheim(Path("C:/gibt/es/nicht.key")) is None


@_windows
def test_vault_key_geschuetzt_und_migration(tmp_path):
    v1 = Vault(tmp_path)
    v1.put("api_key", "wert-123")
    keyfile = tmp_path / "vault.key"
    assert keyfile.read_bytes().startswith(secrets_os.MAGIC)

    # Zweite Instanz liest denselben Schlüssel (DPAPI-Pfad)
    assert Vault(tmp_path).get("api_key") == "wert-123"

    # Bestands-Migration: Klartext-Schlüssel (Vor-H2-Stand) wird beim ersten
    # Laden geschützt, der Tresor bleibt lesbar.
    klartext = secrets_os.lese_geheim(keyfile)
    keyfile.write_bytes(klartext)
    v3 = Vault(tmp_path)
    assert v3.get("api_key") == "wert-123"
    assert keyfile.read_bytes().startswith(secrets_os.MAGIC)
