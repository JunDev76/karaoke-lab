from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json, subprocess, threading

ROOT = Path(__file__).parent.resolve()
player = subprocess.Popen([ROOT / "build/player"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
lock = threading.Lock()

def command(data):
    with lock:
        player.stdin.write(json.dumps(data) + "\n")
        player.stdin.flush()
        return json.loads(player.stdout.readline())

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state": return self.reply(command({"cmd": "state"}))
        if self.path == "/api/tracks":
            tracks = [p for p in (ROOT / "output").rglob("*.wav") if p.stem.endswith(("_instrumental", "_mr"))]
            return self.reply([str(p.relative_to(ROOT)) for p in sorted(tracks)])
        if self.path == "/": self.path = "/web/index.html"
        return super().do_GET()

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(size) or b"{}")
            if data.get("cmd") == "load":
                path = (ROOT / data.get("path", "")).resolve()
                if ROOT not in path.parents or not path.is_file(): raise ValueError("invalid path")
                data["path"] = str(path)
                result = command(data)
                lyrics = Path(str(path).removesuffix("_mr.wav") + "_lyrics.json")
                result["lyrics"] = json.loads(lyrics.read_text()) if lyrics.is_file() else []
                return self.reply(result)
            self.reply(command(data))
        except (ValueError, json.JSONDecodeError) as e: self.reply({"ok": False, "error": str(e)}, 400)

    def reply(self, value, status=200):
        body = json.dumps(value).encode(); self.send_response(status)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", len(body)); self.end_headers(); self.wfile.write(body)

try:
    print("http://127.0.0.1:9003")
    ThreadingHTTPServer(("127.0.0.1", 9003), Handler).serve_forever()
finally: player.terminate()
