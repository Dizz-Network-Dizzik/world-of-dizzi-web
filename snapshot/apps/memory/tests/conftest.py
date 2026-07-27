import sys
from pathlib import Path

_app_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_app_dir))           # Paket archivapp + vendiertes appkit
