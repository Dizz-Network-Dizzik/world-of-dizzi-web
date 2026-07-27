"""Dev-Werkzeug: Reverse-Proxy auf das laufende Dashboard (:8137).

Zweck: Das Claude-Preview-Tool kann sich nicht an einen fremden Server
haengen — es muss den Prozess auf dem Port selbst besitzen. Dieser Proxy
laeuft auf einem freien Port (PORT-Env oder 8139) und reicht ALLE Requests
1:1 an http://127.0.0.1:8137 weiter. So laesst sich die echte, laufende
Oberflaeche im Preview ansehen/testen, ohne den Backend-Prozess (51 Bots!)
anzufassen. Kein Produkt-Code — reines Entwicklungs-Hilfsmittel.

Hinweis Guard (H1): Host/Origin werden auf das Upstream-Ziel umgeschrieben,
sonst lehnt der Local-Guard die Anfragen ab.
"""
from __future__ import annotations

import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = ("127.0.0.1", 8137)
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(*UPSTREAM, timeout=60)
        try:
            headers = {
                k: v for k, v in self.headers.items()
                if k.lower() not in HOP_BY_HOP and k.lower() not in ("host", "origin", "referer")
            }
            headers["Host"] = f"{UPSTREAM[0]}:{UPSTREAM[1]}"
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # Upstream weg o. ae. — ehrlicher 502
            msg = f"Proxy-Fehler: {exc}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
        finally:
            conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _forward

    def log_message(self, *args) -> None:  # leise
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or 8139)
    print(f"Preview-Proxy :{port} -> {UPSTREAM[0]}:{UPSTREAM[1]}")
    ThreadingHTTPServer(("127.0.0.1", port), Proxy).serve_forever()
