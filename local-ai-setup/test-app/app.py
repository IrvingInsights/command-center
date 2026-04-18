"""Hello-world web server showing today's date — first real test for the local AI stack."""
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import date


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        today = date.today().strftime("%A, %B %d, %Y")
        body = f"""<!DOCTYPE html>
<html>
<head><title>Hello World</title>
<style>body{{font-family:sans-serif;display:flex;justify-content:center;
align-items:center;height:100vh;margin:0;background:#0d1117;color:#e6edf3}}</style>
</head>
<body><div style="text-align:center">
  <h1>Hello, World</h1>
  <p style="font-size:1.4rem;color:#58a6ff">{today}</p>
  <p style="color:#8b949e">Local AI stack is running.</p>
</div></body></html>""".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} — {fmt % args}")


if __name__ == "__main__":
    port = 8000
    print(f"Serving at http://localhost:{port}  (Ctrl+C to stop)")
    HTTPServer(("", port), Handler).serve_forever()
