"""KI-Kern (Phase 2).

Zweistufige Strategie (docs/02): LOKAL (Ollama) als Standard und Boden,
GRATIS-BOOST (NVIDIA NIM → Groq → Cerebras) als optionale Kette für schwere,
unkritische Aufgaben. Routing-Regel: sensible Anfragen verlassen den PC NIE.
"""
