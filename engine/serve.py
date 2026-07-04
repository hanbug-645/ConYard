"""Local dev server for game templates.

Routes:
    GET /                       -> auto-generated index page listing base.js
                                   plus every file in example/, with each
                                   file's @demonstrates blurb.
    GET /run/<entry_path>       -> bare HTML shell whose module script
                                   points at /<entry_path>. entry_path is
                                   relative to the template folder.
    GET /<anything else>        -> static file from the template folder.

Usage::

    python3 -m engine.serve snake                              # index at /
    python3 -m engine.serve snake --port 8765
"""

from __future__ import annotations

import argparse
import html
import http.server
import os
import re
import socketserver
from pathlib import Path

try:
    from .template_manager import TemplateManager
except ImportError:  # allow running as a plain script
    from template_manager import TemplateManager

BOOTSTRAP_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  </head>
  <body>
    <script type="module" src="/{entry}"></script>
  </body>
</html>
"""

DEMONSTRATES_RE = re.compile(r"@demonstrates:\s*(.+?)(?=\n\s*\*/|\n\s*\*\s*@|\Z)", re.S)


def read_demonstrates(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = DEMONSTRATES_RE.search(text)
    if not match:
        return ""
    # Strip leading " * " on continuation lines and collapse whitespace.
    lines = [re.sub(r"^\s*\*\s?", "", line) for line in match.group(1).splitlines()]
    return " ".join(line.strip() for line in lines if line.strip())


def build_index(template_dir: Path, template_name: str) -> str:
    entries: list[tuple[str, str]] = [("base.js", "Default game (no customization).")]
    example_dir = template_dir / "example"
    if example_dir.exists():
        for path in sorted(example_dir.glob("*.js")):
            rel = path.relative_to(template_dir).as_posix()
            entries.append((rel, read_demonstrates(path) or "(no @demonstrates tag)"))

    rows = []
    for entry, blurb in entries:
        rows.append(
            f'<li><a href="/run/{html.escape(entry)}"><code>{html.escape(entry)}</code></a>'
            f'<p>{html.escape(blurb)}</p></li>'
        )
    body = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><title>{html.escape(template_name)} — entries</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #e6ecf5; background: #0d1928; }}
  h1 {{ font-size: 1.4rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 1rem 0; padding: .8rem 1rem; background: #17283a; border-radius: 8px; }}
  a {{ color: #62e6a7; text-decoration: none; font-family: ui-monospace, monospace; }}
  a:hover {{ text-decoration: underline; }}
  p {{ margin: .3rem 0 0; color: #a8b8cc; }}
  code {{ font-family: ui-monospace, monospace; }}
</style></head>
<body>
<h1>{html.escape(template_name)} — entries</h1>
<ul>
{body}
</ul>
</body></html>
"""


def make_handler(template_dir: Path, template_name: str):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/" or self.path == "/index.html":
                body = build_index(template_dir, template_name).encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)
                return
            if self.path.startswith("/run/"):
                entry = self.path[len("/run/"):]
                entry_file = template_dir / entry
                if not entry_file.exists() or entry_file.is_dir():
                    self._send(404, "text/plain", f"Not found: {entry}".encode())
                    return
                body = BOOTSTRAP_HTML.format(entry=html.escape(entry, quote=True)).encode()
                self._send(200, "text/html; charset=utf-8", body)
                return
            return super().do_GET()

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            pass

    return Handler


def serve(template_id: str, port: int) -> None:
    manager = TemplateManager()
    template = next(
        (t for t in manager._templates if t.template_id == template_id),
        None,
    )
    if template is None:
        raise SystemExit(f"Unknown template: {template_id}")

    os.chdir(template.template_dir)
    handler = make_handler(template.template_dir, template.manifest.get("name", template_id))
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving template '{template_id}' on http://localhost:{port}/")
        print("  /             -> index of entries")
        print("  /run/<entry>  -> load an entry in a bare HTML shell")
        httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template_id")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.template_id, args.port)


if __name__ == "__main__":
    main()
