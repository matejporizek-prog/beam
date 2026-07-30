"""
Tiny static file server for local development.

Python's built-in `http.server` sends no Cache-Control header, so browsers
heuristically cache the ES modules and CSS — which means edits silently don't
show up until a hard refresh, and you waste time wondering why. This server is
identical except it tells the browser never to cache, so every reload is fresh.

    python devserver.py            # serves the project at http://localhost:8788
    python devserver.py 9000       # ...on a different port

Open http://localhost:8788/app/ to view the PWA.

This is a development convenience only. In production the app is served by
Cloudflare Pages (Milestone 5), where caching is wanted and handled properly.
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    # SimpleHTTPRequestHandler speaks HTTP/1.0 by default, which means it closes
    # the socket after every single response. The app boots by fetching
    # screenings.json and films.json in parallel (Promise.all), and those
    # abrupt closes show up in the browser as intermittent
    # ERR_CONNECTION_RESET -> "Data se nepodařilo načíst", on a page whose data
    # is perfectly fine. HTTP/1.1 keeps the connection alive and ends the
    # response cleanly; the base class already sends an accurate Content-Length
    # for files, which is what makes keep-alive safe here.
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    # Quieter logging: one line per request is enough.
    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.command} {self.path}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    root = Path(__file__).resolve().parent
    handler = partial(NoCacheHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Beam dev server on http://localhost:{port}/app/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
