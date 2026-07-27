import sys
from pathlib import Path

_APPKIT = Path(__file__).resolve().parents[1]   # …/appkit

# Repo-Wurzel in den Pfad: `import appkit` (als Paket) funktioniert unabhängig
# vom pytest-Aufrufort (kanonische Quelle; vendierte Kopien haben eigene Pfade).
sys.path.insert(0, str(_APPKIT.parent))

# WICHTIG: Wird `python -m pytest` AUS dem appkit-Ordner gestartet, liegt dieser
# Ordner (als cwd "") auf sys.path — dann schattet appkit/mcp.py das installierte
# `mcp`-SDK, das fastmcp importiert ("ModuleNotFoundError: mcp.types"). In Produktion
# tritt das nie auf (appkit wird als Paket `appkit.mcp` geladen). Hier den Schatten
# entfernen, damit `import mcp` das echte SDK trifft.
sys.path[:] = [p for p in sys.path
               if p not in ("", ".") and Path(p or ".").resolve() != _APPKIT]
