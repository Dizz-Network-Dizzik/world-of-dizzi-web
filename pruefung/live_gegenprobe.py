"""live_gegenprobe.py - the delivery gate: is what is live exactly what HEAD built?

Every other gate in this folder checks the sources or the baked output before a
push. None of them looks at the site afterwards. Until 05.09.2026 that last step
was done by hand: fetch a few pages, compare by eye, note the byte difference.
A gate that is run by hand looks exactly like a gate that was skipped.

This script fetches every page that bake.py writes to dist/ from the live site
and compares it byte for byte with the local file. The host injects a small,
known kind of noise into HTML (an HTML comment plus meta tags); that noise is
stripped from both sides before comparing, and its size is reported, never
hidden. Anything else that differs is a drift and turns the gate red.

    python pruefung/live_gegenprobe.py                 # exit 0 = live == HEAD
    python pruefung/live_gegenprobe.py --base https://example.netlify.app
    python pruefung/live_gegenprobe.py --json          # machine-readable summary

exit 0 = every file matches (injection noted), 1 = drift, 2 = could not check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DEFAULT_BASE = "https://worldofdizzi.netlify.app"
TIMEOUT_S = 20

# Noise the host may add to HTML without changing what the reader sees.
_COMMENT = re.compile(rb"<!--.*?-->", re.S)
_META = re.compile(rb"<meta\b[^>]*>", re.I)


def _normalise(html: bytes) -> bytes:
    return _META.sub(b"", _COMMENT.sub(b"", html))


def _fetch(url: str) -> tuple[int | None, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "live-gegenprobe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, r.read(), ""
    except urllib.error.HTTPError as e:
        return e.code, b"", f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return None, b"", f"no contact: {e}"


def _targets() -> list[tuple[Path, str]]:
    """(local file, url path) for everything in dist/ that a browser can fetch."""
    out: list[tuple[Path, str]] = []
    for p in sorted(DIST.rglob("*")):
        if not p.is_file() or p.name.startswith("_"):
            continue
        rel = p.relative_to(DIST).as_posix()
        if rel.endswith("/index.html"):
            rel = rel[: -len("index.html")]
        elif rel == "index.html":
            rel = ""
        out.append((p, "/" + rel))
    return out


def run(base: str) -> tuple[int, dict]:
    if not DIST.is_dir():
        return 2, {"error": "dist/ missing - bake first"}
    rows, drift, unreachable, injected_total = [], 0, 0, 0
    for local, path in _targets():
        want = local.read_bytes()
        status, got, err = _fetch(base + path)
        if status != 200:
            unreachable += 1
            rows.append({"path": path, "status": status, "result": "UNREACHABLE", "note": err})
            continue
        if got == want:
            rows.append({"path": path, "status": 200, "result": "OK", "injected": 0})
            continue
        if local.suffix == ".html" and _normalise(got) == _normalise(want):
            delta = len(got) - len(want)
            injected_total += max(delta, 0)
            rows.append({"path": path, "status": 200, "result": "OK", "injected": delta})
            continue
        drift += 1
        rows.append({"path": path, "status": 200, "result": "DRIFT",
                     "local_bytes": len(want), "live_bytes": len(got)})
    code = 2 if unreachable else (1 if drift else 0)
    return code, {"base": base, "files": len(rows), "drift": drift, "unreachable": unreachable,
                  "injected_bytes": injected_total, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=DEFAULT_BASE, help="site origin, no trailing slash")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    a = ap.parse_args(argv)
    code, summary = run(a.base.rstrip("/"))
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if "error" in summary:
            print("live_gegenprobe:", summary["error"])
        else:
            for r in summary["rows"]:
                if r["result"] != "OK" or r.get("injected"):
                    extra = f"+{r['injected']} B injected" if r.get("injected") else r.get("note", "")
                    print(f"  {r['result']:11} {r['path']:22} {extra}")
            print(f"live_gegenprobe: {summary['files']} files against {summary['base']} - "
                  f"drift {summary['drift']}, unreachable {summary['unreachable']}, "
                  f"host injection {summary['injected_bytes']} B in total")
        print({0: "LIVE == HEAD", 1: "DRIFT - live differs from HEAD", 2: "COULD NOT CHECK"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
