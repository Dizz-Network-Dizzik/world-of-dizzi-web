import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.ai import rag  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Jeder Test bekommt frische SQLite-Dateien — nie die echten Daten-DBs."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db.reset_thread_conn()
    rag.reset_thread_conn()
    yield
    db.reset_thread_conn()
    rag.reset_thread_conn()
