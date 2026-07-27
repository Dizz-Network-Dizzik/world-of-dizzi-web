from app.ai import websearch

SAMPLE = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fseite&amp;rut=x">Beispiel <b>Titel</b></a>
  <a class="result__snippet" href="#">Das ist der <b>Snippet</b>-Text.</a>
</div>
<div class="result">
  <a class="result__a" href="https://direkt.example.com/x">Zweiter Treffer</a>
  <div class="result__snippet">Noch ein Text.</div>
</div>
"""


def test_parse_ddg_html():
    res = websearch.parse_ddg_html(SAMPLE, max_results=5)
    assert len(res) == 2
    assert res[0]["title"] == "Beispiel Titel"
    assert res[0]["url"] == "https://example.org/seite"
    assert "Snippet" in res[0]["snippet"]
    assert res[1]["url"] == "https://direkt.example.com/x"


def test_parse_respects_max():
    assert len(websearch.parse_ddg_html(SAMPLE, max_results=1)) == 1


def test_format_results():
    out = websearch.format_results([{"title": "T", "url": "u", "snippet": "s"}])
    assert "[1] T" in out and "u" in out
    assert websearch.format_results([]) == "Keine Suchtreffer."
