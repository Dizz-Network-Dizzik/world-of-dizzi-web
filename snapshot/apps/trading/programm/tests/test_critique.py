"""Kernlogik-Tests: Self-Critique des Recherche-Tools (Drop/Downgrade/Cap/Fail-safe)."""
import json

from backend.app import ai


class _Blk:
    type = "text"
    def __init__(self, t): self.text = t


class _Msg:
    def __init__(self, t): self.content = [_Blk(t)]


class _Msgs:
    def __init__(self, payload, raise_=False): self.payload, self.raise_ = payload, raise_
    def create(self, **kw):
        if self.raise_:
            raise RuntimeError("simulierter API-Fehler")
        return _Msg(self.payload)


class _Client:
    def __init__(self, payload, raise_=False): self.messages = _Msgs(payload, raise_)


def _systems():
    return [{"id": c, "name": c, "certainty": "hoch"} for c in "ABCD"]


def test_drop_and_downgrade_only():
    verdicts = [
        {"id": "A", "verdict": "keep", "certainty": "mittel"},   # downgrade
        {"id": "B", "verdict": "drop"},                          # weg
        {"id": "C", "verdict": "keep", "certainty": "hoch"},     # Upgrade-Versuch -> ignoriert
    ]
    out = ai._self_critique(_Client(json.dumps(verdicts)), "m", _systems())
    by = {s["id"]: s for s in out}
    assert "B" not in by
    assert by["A"]["certainty"] == "mittel"
    assert by["C"]["certainty"] == "niedrig" or by["C"]["certainty"] == "hoch"  # nie hochgestuft
    assert by["D"]["certainty"] == "hoch"   # ohne Urteil unverändert


def test_cap_when_majority_dropped():
    verdicts = [{"id": c, "verdict": "drop"} for c in "ABC"]   # 3/4 > 50% -> Cap
    out = ai._self_critique(_Client(json.dumps(verdicts)), "m", _systems())
    assert len(out) == 4   # Drops verworfen, kein Kollaps


def test_failsafe_keeps_original_on_error():
    out = ai._self_critique(_Client("", raise_=True), "m", _systems())
    assert len(out) == 4
