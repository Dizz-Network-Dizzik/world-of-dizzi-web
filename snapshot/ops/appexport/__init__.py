"""appexport — Produkt-Export-Werkzeug (C-1, docs/66 = Bau-Spec).

**Status: VERTRAG (C1-0, 04.07.2026).** Dieses Paket hält die normativen Schemata,
Regelwerke und Datenmodelle des App-Export-Vertrags; die Bau-Teile (AST-Scan,
Lizenz-Generator, Bundle-Builder) baut Bau-KI per docs/66 §10 und werfen bis dahin
``NichtGebaut``. Die puren Regelwerke (Hüllen-Abschluss, Ampel, Editions-Freigaben,
Nullzustands-Muster, Manifest-Validierung) sind bereits real und getestet.

Zwei-Schienen-Klarstellung (docs/66 §0): ``ops/mirror_export.py`` = interner
Voll-Spiegel (Backup, bleibt unverändert); DIESES Paket = verkäufliches Bündel
(gecarvt, lizenz-geprüft, editions-geschnitten, null-zuständig, updatebar).

Invariante I-11: appexport importiert NIEMALS appkit — es analysiert Quelltext
statt zu importieren (läuft ohne PYTHONPATH, keine Seiteneffekte).
"""

from __future__ import annotations


class NichtGebaut(NotImplementedError):
    """Vertrags-Stub: dieser Teil wird per docs/66 §10 (C1-1…C1-7) von Bau-KI gebaut."""
