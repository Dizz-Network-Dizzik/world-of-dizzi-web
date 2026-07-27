"""Pytest-Setup: macht das `backend`-Paket importierbar (programm/ auf sys.path)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test-Isolation: verhindert, dass der App-Lifespan (z. B. test_vertrag `with TestClient(main.app)`)
# reale Seiteneffekte auf das LAUFENDE Backend auslöst — Config-Migrationen, ensure_master_bot,
# runner.start, Resume-/Watchdog-Threads + backend_started-Spam in der echten audit.sqlite.
os.environ.setdefault("TBT_NO_STARTUP", "1")


@pytest.fixture(autouse=True)
def _clear_ttl_cache():
    """Leert den prozessglobalen TTL-Memo vor jedem Test — gecachte Aggregationen (z. B.
    master._collect_mn_raw) würden sonst Monkeypatches des Vortests überdauern."""
    from backend.app import cache
    cache.invalidate()
    yield
