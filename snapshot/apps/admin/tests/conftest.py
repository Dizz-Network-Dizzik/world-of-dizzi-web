import sys
from pathlib import Path

# admin-Wurzel auf den Pfad: Paket ``adminapp`` + vendiertes ``appkit``.
_app_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_app_dir))
