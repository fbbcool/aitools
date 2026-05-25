"""Persistent JoyCaption HTTP server.

Loads `Joy` (configured per `Skin` via `Joy.from_skin`, which resolves
the base model + LoRA paths through `AInstallerDB`) exactly ONCE at
startup, then listens on a local HTTP socket for caption/probe requests. Clients (slash commands, batch tools) reach the server via
`joy_client.py` to avoid the ~23s model-load cost on every invocation.

The server is intentionally DB-free: it loads from disk (model cache,
skin JSON, AInstallerDB YAML) only — no MongoDB connection. Scene-image
lookups happen on the client side; the HTTP API takes raw `image_url`
strings.

CLI:
    python -m ait.caption.joy_server [--skin NAME] [--port PORT]
                                     [--idle-timeout SECONDS]

Endpoints:
    GET  /healthz   -> {"status": "ok", ...}
    POST /caption   -> {"prompt": str, "caption": str}
    POST /shutdown  -> graceful exit

Body for POST /caption (JSON):
    {
        "image_url":      "<absolute path or http(s)://… or file://…>",
        "user_content":   "<the per-image probe/caption prompt>",
        "system_content": "<optional; defaults to skin.directive>",
        "gen_kwargs":     {...optional generation overrides}
    }

PID file at $WORKSPACE/joy_server.pid (or /tmp fallback). Stdout +
stderr captured to $WORKSPACE/joy_server.log.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from PIL import Image


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _workspace_dir() -> Path:
    """Resolve $WORKSPACE; fall back to /tmp if unset."""
    ws = os.environ.get('WORKSPACE')
    if ws:
        p = Path(ws)
        if p.exists():
            return p
    return Path('/tmp')


def pid_file() -> Path:
    return _workspace_dir() / 'joy_server.pid'


def log_file() -> Path:
    return _workspace_dir() / 'joy_server.log'


# ---------------------------------------------------------------------------
# Server state (module-level singleton — one model per process)
# ---------------------------------------------------------------------------

class _State:
    """Holds the loaded captioner + activity bookkeeping."""

    def __init__(self, skin_name: str, idle_timeout: int = 1800):
        self.skin_name = skin_name
        self.idle_timeout = idle_timeout
        self.loaded_at: float = 0.0
        self.last_request_at: float = 0.0
        self.request_count: int = 0
        self._lock = threading.Lock()
        self._joy = None     # Joy instance
        self._skin = None    # Skin instance
        self._shutdown_event = threading.Event()

    def load(self) -> None:
        # Imported lazily so `--help` doesn't pay the import cost.
        from ait.caption.joy import Joy
        from ait.caption.skin import SkinRegistry

        t0 = time.time()
        self._skin = SkinRegistry().get(self.skin_name)
        self._joy = Joy.from_skin(self._skin, use_lora=True, verbose=1)
        self.loaded_at = time.time()
        print(f'[joy_server] loaded skin={self.skin_name!r} '
              f'in {self.loaded_at - t0:.1f}s', flush=True)

    def caption(self, image_url: str, user_content: str,
                system_content: Optional[str] = None,
                gen_kwargs: Optional[dict] = None,
                adapter: str = 'default') -> tuple[str, str]:
        """Run a single caption/probe. Serialized via internal lock so
        concurrent HTTP requests don't trample the GPU. `adapter` selects
        which loaded LoRA adapter to use (default = the main captioning
        LoRA; 'hint' = the iter-5-hint LoRA when skin.lora_hint_path is set)."""
        if self._joy is None or self._skin is None:
            raise RuntimeError('captioner not loaded')
        img = _load_image(image_url)
        sys_content = system_content if system_content is not None else self._skin.directive
        with self._lock:
            self.request_count += 1
            self.last_request_at = time.time()
            prompt, caption = self._joy.caption(
                img=img,
                system_content=sys_content,
                user_content=user_content,
                default_prompt='',
                label_prompts=(),
                user_hint_preamble=None,
                user_hint='',
                post_prompt='',
                gen_kwargs=gen_kwargs or None,
                adapter=adapter,
            )
        return prompt, caption

    def health_dict(self) -> dict:
        return {
            'status': 'ok' if self._joy is not None else 'loading',
            'skin': self.skin_name,
            'loaded_at': self.loaded_at,
            'last_request_at': self.last_request_at,
            'request_count': self.request_count,
            'idle_timeout_seconds': self.idle_timeout,
            'idle_seconds': max(0.0, time.time() - self.last_request_at) if self.last_request_at else 0.0,
            'adapters': sorted(self._joy.adapters.keys()) if (self._joy is not None and self._joy.adapters) else [],
        }

    def start_idle_watchdog(self) -> None:
        """Daemon thread: shut down the server if no requests for
        `idle_timeout` seconds. Checks every 60 seconds."""
        def _watch():
            while not self._shutdown_event.wait(60):
                if self.request_count == 0:
                    # never served — be patient; the curator may pre-warm
                    continue
                idle = time.time() - self.last_request_at
                if idle > self.idle_timeout:
                    print(f'[joy_server] idle {idle:.0f}s > {self.idle_timeout}s '
                          f'— self-shutting-down', flush=True)
                    self.request_shutdown()
                    break
        t = threading.Thread(target=_watch, daemon=True, name='idle-watchdog')
        t.start()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()
        # Trigger the HTTP server to exit; the watchdog or /shutdown handler
        # calls this. The actual server.shutdown() call is wired up in main().


_STATE: Optional[_State] = None


def _load_image(image_url: str) -> Image.Image:
    """Load a PIL image from a local path, file:// URL, or http(s):// URL."""
    parsed = urlparse(image_url)
    if parsed.scheme in ('', 'file'):
        path = parsed.path if parsed.scheme == 'file' else image_url
        return Image.open(path).convert('RGB')
    # http(s)://
    with urlopen(image_url, timeout=15) as resp:
        data = resp.read()
    return Image.open(io.BytesIO(data)).convert('RGB')


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """One-request-per-call handler. State held by module-level _STATE."""

    server_version = 'joy_server/1.0'

    def log_message(self, fmt, *args):
        # Route access logs through our own stdout (captured to log_file)
        print(f'[joy_server:http] {self.address_string()} - ' + fmt % args, flush=True)

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict:
        n = int(self.headers.get('Content-Length', '0') or 0)
        raw = self.rfile.read(n) if n > 0 else b''
        if not raw:
            return {}
        return json.loads(raw.decode('utf-8'))

    def do_GET(self):
        if self.path == '/healthz':
            self._send_json(200, _STATE.health_dict() if _STATE else {'status': 'starting'})
        else:
            self._send_json(404, {'error': 'not found', 'path': self.path})

    def do_POST(self):
        if self.path == '/caption':
            if _STATE is None or _STATE._joy is None:
                self._send_json(503, {'error': 'captioner not loaded'})
                return
            try:
                body = self._read_json()
                image_url = body.get('image_url')
                user_content = body.get('user_content', '')
                if not image_url or not user_content:
                    self._send_json(400, {'error': 'image_url and user_content required'})
                    return
                t0 = time.time()
                prompt, caption = _STATE.caption(
                    image_url=image_url,
                    user_content=user_content,
                    system_content=body.get('system_content'),
                    gen_kwargs=body.get('gen_kwargs'),
                    adapter=body.get('adapter', 'default'),
                )
                dt = time.time() - t0
                self._send_json(200, {
                    'prompt': prompt,
                    'caption': caption,
                    'seconds': round(dt, 2),
                })
            except Exception as e:
                self._send_json(500, {'error': repr(e)})

        elif self.path == '/shutdown':
            self._send_json(200, {'status': 'shutting down'})
            # Mark for shutdown; main loop is unblocked by closing the server.
            if _STATE is not None:
                _STATE.request_shutdown()
            # Spawn a thread to call server.shutdown() to avoid deadlock
            # (we're inside a request handler).
            threading.Thread(target=_request_server_shutdown, daemon=True).start()

        else:
            self._send_json(404, {'error': 'not found', 'path': self.path})


_HTTPD: Optional[HTTPServer] = None


def _request_server_shutdown() -> None:
    global _HTTPD
    time.sleep(0.1)  # let the response flush
    if _HTTPD is not None:
        _HTTPD.shutdown()


# ---------------------------------------------------------------------------
# PID file handling
# ---------------------------------------------------------------------------

def _write_pid_file() -> None:
    p = pid_file()
    p.write_text(str(os.getpid()))
    print(f'[joy_server] PID file: {p}', flush=True)


def _remove_pid_file() -> None:
    p = pid_file()
    try:
        if p.exists():
            stored = p.read_text().strip()
            if stored == str(os.getpid()):
                p.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--skin', default='1xlasm')
    ap.add_argument('--port', type=int, default=int(os.environ.get('JOY_SERVER_PORT', '7862')))
    ap.add_argument('--idle-timeout', type=int, default=1800,
                    help='Self-shutdown after this many seconds of no caption requests (default 1800 = 30 min)')
    args = ap.parse_args(argv)

    global _STATE, _HTTPD

    _write_pid_file()

    def _sig_handler(signum, frame):
        print(f'[joy_server] signal {signum} received — shutting down', flush=True)
        if _STATE is not None:
            _STATE.request_shutdown()
        threading.Thread(target=_request_server_shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    try:
        _STATE = _State(skin_name=args.skin, idle_timeout=args.idle_timeout)
        _STATE.load()
        _STATE.start_idle_watchdog()

        addr = ('127.0.0.1', args.port)
        _HTTPD = HTTPServer(addr, _Handler)
        print(f'[joy_server] listening on http://{addr[0]}:{addr[1]}', flush=True)
        try:
            _HTTPD.serve_forever()
        except KeyboardInterrupt:
            pass
        _HTTPD.server_close()
        print('[joy_server] stopped', flush=True)
        return 0
    finally:
        _remove_pid_file()


if __name__ == '__main__':
    sys.exit(main())
