"""appexport-Tests: ops/ in den Import-Pfad legen (kein Install, kein PYTHONPATH nötig — I-11)."""
import sys
from pathlib import Path

OPS = Path(__file__).resolve().parents[2]
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))
