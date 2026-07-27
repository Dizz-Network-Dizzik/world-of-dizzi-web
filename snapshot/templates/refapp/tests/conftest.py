import sys
from pathlib import Path

# templates/refapp (Paket ``refapp``) und Repo-Wurzel (``appkit``) in den Pfad.
_refapp_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_refapp_dir))
sys.path.insert(0, str(_refapp_dir.parents[1]))
