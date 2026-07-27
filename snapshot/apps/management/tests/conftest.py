import sys
from pathlib import Path

# social-media-Wurzel auf den Pfad: Paket ``managementapp`` + vendiertes ``appkit``.
_app_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_app_dir))
