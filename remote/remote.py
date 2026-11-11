#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
FONT = HERE.parent / "assets" / "Jost.ttf"
ADB = os.environ.get("ADB", "/opt/homebrew/share/android-commandlinetools/platform-tools/adb")
DEVICE = os.environ.get("PROJECTOR", "192.168.0.22:5555")
PORT = int(os.environ.get("PORT", "8765"))

KEYS = {
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "ok": 23,
    "back": 4,
    "home": 3,
    "menu": 82,
    "volup": 24,
    "voldown": 25,
    "mute": 164,
    "playpause": 85,
    "rewind": 89,
    "forward": 90,
    "power": 26,
}
HELPER = HERE / "inj.dex"
REMOTE_HELPER = "/data/local/tmp/inj.dex"

lock = threading.Lock()


def adb(*args, timeout=8):
    return subprocess.run([ADB, "-s", DEVICE, *args], capture_output=True, text=True, timeout=timeout)


def connected():
    out = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=8).stdout
    return any(line.startswith(DEVICE) and line.endswith("device") for line in out.splitlines())


def ensure():
    if connected():
        return True
    subprocess.run([ADB, "connect", DEVICE], capture_output=True, text=True, timeout=8)
    return connected()


class Helper:
    def __init__(self):
        self.proc = None

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        self.stop()
        adb("push", str(HELPER), REMOTE_HELPER)
        self.proc = subprocess.Popen(
            [ADB, "-s", DEVICE, "shell", f"CLASSPATH={REMOTE_HELPER}", "app_process", "/system/bin", "Inj"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        ready = self.proc.stdout.readline().strip()
        if ready != "ready":
            self.stop()
            return False
        return True

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except OSError:
                pass
        self.proc = None

    def press(self, code):
        self.proc.stdin.write(f"{code}\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip() == "ok"


helper = Helper()


def send_key(name):
    with lock:
        for attempt in range(2):
            try:
                if not helper.alive():
                    if not ensure() or not helper.start():
                        return False, "projector not reachable"
                if helper.press(KEYS[name]):
                    return True, ""
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            helper.stop()
        return False, "projector not reachable"


def send_text(text):
    cleaned = "".join(c for c in text if c.isalnum() or c in " .,-_@")[:120]
    if not cleaned:
        return False, "nothing to send"
    with lock:
        if not ensure():
            return False, "projector not reachable"
        r = adb("shell", "input", "text", cleaned.replace(" ", "%s"))
        return r.returncode == 0, r.stderr.strip()


def status():
    with lock:
        return helper.alive() or ensure()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost"):
            return False
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return False
        return True

    def do_GET(self):
        if not self.local_only():
            return self.reply(403, "forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/":
            return self.reply(200, (HERE / "index.html").read_text(), "text/html; charset=utf-8")
        if path == "/Jost.ttf" and FONT.exists():
            return self.reply(200, FONT.read_bytes(), "font/ttf")
        if path == "/status":
            return self.reply(200, json.dumps({"online": status()}))
        return self.reply(404, "not found", "text/plain")

    def do_POST(self):
        if not self.local_only() or self.headers.get("X-Remote") != "1":
            return self.reply(403, "forbidden", "text/plain")
        path = urlparse(self.path).path
        length = min(int(self.headers.get("Content-Length") or 0), 2048)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.reply(400, json.dumps({"ok": False, "error": "bad json"}))
        if path == "/key" and body.get("key") in KEYS:
            ok, err = send_key(body["key"])
        elif path == "/text" and isinstance(body.get("text"), str):
            ok, err = send_text(body["text"])
        else:
            return self.reply(400, json.dumps({"ok": False, "error": "unknown action"}))
        return self.reply(200, json.dumps({"ok": ok, "error": err}))


def warm():
    with lock:
        if ensure():
            helper.start()


if __name__ == "__main__":
    threading.Thread(target=warm, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"projector remote on http://127.0.0.1:{PORT}  (device {DEVICE})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
