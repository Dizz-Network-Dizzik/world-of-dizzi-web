"""Tests: TTL-Cache (Read-Pfad-Memoisierung der teuren Aggregationen)."""
import time

from backend.app import cache


def test_ttl_get_memoizes_within_ttl():
    cache.invalidate("t.key")
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return calls["n"]

    a = cache.ttl_get("t.key", 5.0, producer)
    b = cache.ttl_get("t.key", 5.0, producer)
    assert a == 1 and b == 1 and calls["n"] == 1  # producer nur einmal


def test_ttl_get_recomputes_after_expiry():
    cache.invalidate("t.exp")
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return calls["n"]

    cache.ttl_get("t.exp", 0.01, producer)
    time.sleep(0.02)
    second = cache.ttl_get("t.exp", 0.01, producer)
    assert second == 2 and calls["n"] == 2


def test_invalidate_forces_recompute():
    cache.invalidate("t.inv")
    calls = {"n": 0}
    cache.ttl_get("t.inv", 99.0, lambda: calls.__setitem__("n", calls["n"] + 1) or calls["n"])
    cache.invalidate("t.inv")
    cache.ttl_get("t.inv", 99.0, lambda: calls.__setitem__("n", calls["n"] + 1) or calls["n"])
    assert calls["n"] == 2


def test_invalidate_all():
    cache.ttl_get("t.a", 99.0, lambda: 1)
    cache.ttl_get("t.b", 99.0, lambda: 2)
    cache.invalidate()  # alles
    calls = {"n": 0}
    cache.ttl_get("t.a", 99.0, lambda: calls.__setitem__("n", calls["n"] + 1) or 9)
    assert calls["n"] == 1
