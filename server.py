#!/usr/bin/env python3
"""
Live server for static files with auto-reload via Server-Sent Events.
Run: python server.py
Then open: http://localhost:8080
"""

import os
import sys
import time
import threading
import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8080
WATCH_EXTENSIONS = {".html", ".css", ".js"}

# Track file hashes to detect changes
file_hashes = {}
clients = []
clients_lock = threading.Lock()


def hash_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def scan_files(root="."):
    for dirpath, _, filenames in os.walk(root):
        if any(part.startswith(".") for part in dirpath.split(os.sep)):
            continue
        for name in filenames:
            if os.path.splitext(name)[1].lower() in WATCH_EXTENSIONS:
                yield os.path.join(dirpath, name)


def watcher():
    # Initial snapshot
    for path in scan_files():
        file_hashes[path] = hash_file(path)

    while True:
        time.sleep(0.5)
        changed = False
        current = set(scan_files())

        for path in current:
            h = hash_file(path)
            if file_hashes.get(path) != h:
                file_hashes[path] = h
                changed = True
                print(f"[reload] {path}")
                break

        for path in set(file_hashes) - current:
            del file_hashes[path]
            changed = True

        if changed:
            with clients_lock:
                for q in list(clients):
                    q.append("reload")


INJECT = b"""
<script>
(function() {
  const es = new EventSource('/__livereload__');
  es.onmessage = function(e) {
    if (e.data === 'reload') location.reload();
  };
  es.onerror = function() {
    setTimeout(() => location.reload(), 2000);
  };
  console.log('[live-server] watching for changes...');
})();
</script>
"""


class LiveHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Suppress SSE polling noise
        if "/__livereload__" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def do_GET(self):
        if self.path == "/__livereload__":
            self._sse()
            return

        path = self.translate_path(self.path)

        # Inject reload script into HTML responses
        if os.path.isfile(path) and path.endswith(".html"):
            with open(path, "rb") as f:
                content = f.read()
            injected = content.replace(b"</body>", INJECT + b"</body>", 1)
            if injected == content:
                injected = content + INJECT
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(injected)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(injected)
            return

        super().do_GET()

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        queue = []
        with clients_lock:
            clients.append(queue)

        try:
            while True:
                if queue:
                    msg = queue.pop(0)
                    self.wfile.write(f"data: {msg}\n\n".encode())
                    self.wfile.flush()
                else:
                    # Heartbeat every 15 s to keep connection alive
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    time.sleep(15)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with clients_lock:
                clients.remove(queue)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    threading.Thread(target=watcher, daemon=True).start()
    server = HTTPServer(("", PORT), LiveHandler)
    print(f"Live server running at http://localhost:{PORT}")
    print("Watching .html, .css, .js files for changes. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
