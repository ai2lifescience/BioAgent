"""Independent trusted-site fixture for the website embedding contract."""
from __future__ import annotations
import argparse, json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from harness.website import issue_ticket

ROOT = Path(__file__).parent
ORIGIN = os.getenv("EXAMPLE_ORIGIN", "http://localhost:8081")
SECRET = os.getenv("AGENT_WEBSITE_SECRET", "dev-website-secret-change-me-32chars!!")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data=(ROOT/"index.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_error(404)
    def do_POST(self):
        if self.path != "/assistant-token": self.send_error(404); return
        token=issue_ticket(SECRET,site_id="external-workspace",origin=ORIGIN,subject="demo-user")
        data=json.dumps({"token":token}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=8081); args=parser.parse_args()
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
