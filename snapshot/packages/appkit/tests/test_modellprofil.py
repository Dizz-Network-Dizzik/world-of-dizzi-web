"""Vertrags-Tests für appkit/modellprofil.py (FP-3-Stub — docs/62 §3).

Der wichtigste Pin: **Stufe 0 == heutiges Live-Verhalten** — die Literale
spiegeln core ``providers.DEFAULT_LOCAL_MODEL``/``FAST_LOCAL_MODEL`` und
``archivapp.rag.EMBED_MODELL``/dim (appkit kann Apps nicht importieren, daher
Literal-Pins; C3 ergänzt Paritäts-Tests auf App-Seite gegen die Konstanten)."""

from __future__ import annotations

import pytest

from appkit import modellprofil as mp


def _stufe(n, *, frei=True, vram=0, embed=("bge-m3", 1024)):
    zu = {"chat": mp.ModellSlot("chat-m")}
    if embed:
        zu["embed"] = mp.ModellSlot(embed[0], mp.ModellFaehigkeiten(dim=embed[1]))
    return mp.ModellProfil(stufe=n, name=f"stufe-{n}", freigegeben=frei,
                           vram_min_bytes=vram, zuordnung=zu)


def test_task_klassen_kanon():
    assert mp.TASK_KLASSEN == ("chat", "schnell", "embed", "rerank", "vision", "voice")


def test_stufe0_spiegelt_heutige_konstanten():
    s = mp.STUFE_0
    assert s.freigegeben and s.vram_min_bytes == 0 and mp.STUFEN == (s,)
    assert s.modell_fuer("chat") == "qwen3:14b"      # providers.DEFAULT_LOCAL_MODEL
    assert s.modell_fuer("schnell") == "qwen3:4b"    # providers.FAST_LOCAL_MODEL
    assert s.modell_fuer("embed") == "bge-m3"        # rag.EMBED_MODELL
    assert s.slot("embed").faehigkeiten.dim == 1024  # rag.EMBED_MODELLE['bge-m3']
    for dormant in ("rerank", "vision", "voice"):    # heute nicht verdrahtet = ehrlich
        assert s.modell_fuer(dormant) is None


def test_aufloese_boden_und_hardware_gate():
    stufen = (_stufe(0), _stufe(1, vram=8 * 2**30), _stufe(2, frei=False, vram=0))
    assert mp.aufloese_stufe(None, stufen=stufen).stufe == 0        # Probe kaputt ⇒ Boden
    assert mp.aufloese_stufe(4 * 2**30, stufen=stufen).stufe == 0   # zu wenig VRAM
    assert mp.aufloese_stufe(16 * 2**30, stufen=stufen).stufe == 1  # höchste passende
    # Release-Gate: unfreigegebene Stufe 2 nie — weder auto noch per Pin.
    assert mp.aufloese_stufe(64 * 2**30, stufen=stufen).stufe == 1
    assert mp.aufloese_stufe(64 * 2**30, stufen=stufen, pin=2).stufe == 1
    assert mp.aufloese_stufe(0, stufen=stufen, pin=1).stufe == 1    # Pin gewinnt (frei)
    assert mp.aufloese_stufe(0, stufen=stufen, pin=99).stufe == 0   # Pin unbekannt ⇒ auto


def test_aufloese_ohne_boden_ist_programmierfehler():
    with pytest.raises(ValueError):
        mp.aufloese_stufe(0, stufen=(_stufe(1, vram=8 * 2**30),))


def test_wechsel_folgen_embed_diszipliniert():
    s0 = _stufe(0)
    assert mp.profil_wechsel_folgen(s0, _stufe(1)).reindex_noetig is False
    anders = mp.profil_wechsel_folgen(s0, _stufe(1, embed=("qwen3-embedding", 1024)))
    assert anders.embed_wechsel and anders.reindex_noetig and "Re-Index" in anders.hinweis
    assert mp.profil_wechsel_folgen(s0, _stufe(1, embed=("bge-m3", 768))).reindex_noetig
    assert mp.profil_wechsel_folgen(s0, _stufe(1, embed=None)).reindex_noetig
    ohne = _stufe(0, embed=None)
    assert mp.profil_wechsel_folgen(ohne, ohne).reindex_noetig is False


def test_vram_probe_failsafe_nie_wirft():
    # Echt ab C4/M9 — aber IMMER fail-safe: wirft nie; None (unbekannt) oder
    # Bytes ≥ 0. Hardware-unabhängig grün (mit wie ohne nvidia-smi).
    v = mp.vram_probe()
    assert v is None or (isinstance(v, int) and v >= 0)


def test_vram_probe_ohne_nvidia_smi(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert mp.vram_probe() is None            # nicht installiert ⇒ Boden


def test_vram_probe_schluckt_fehler(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: "nvidia-smi")

    def boom(*a, **k):
        raise OSError("nvidia-smi verschwunden")
    monkeypatch.setattr("subprocess.run", boom)
    assert mp.vram_probe() is None            # wirft NIE


def test_vram_probe_nonzero_exit_ist_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: "nvidia-smi")
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: type("R", (), {"returncode": 9, "stdout": ""})())
    assert mp.vram_probe() is None


def test_vram_probe_parst_mib_zu_bytes(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: "nvidia-smi")
    # zwei GPUs — die ERSTE Zeile zählt; 16384 MiB = 16 GiB.
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **k: type("R", (), {"returncode": 0,
                                                       "stdout": "16384\n8192\n"})())
    assert mp.vram_probe() == 16384 * 1024 * 1024
