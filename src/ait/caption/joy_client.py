"""Thin client for the JoyCaption server (`joy_server.py`).

Slash commands use this module to:
  - check whether the server is running
  - start it if not (paying the ~23s model-load cost ONCE)
  - submit caption/probe requests
  - shut it down

The client is intentionally tiny — stdlib only, no Flask/requests dep.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .joy_server import pid_file, log_file


DEFAULT_PORT: int = int(os.environ.get('JOY_SERVER_PORT', '7862'))
DEFAULT_HOST: str = '127.0.0.1'


def _base_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f'http://{host}:{port}'


def _http_get(path: str, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
              timeout: float = 2.0) -> tuple[int, dict]:
    try:
        with urlopen(_base_url(host, port) + path, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return resp.status, data
    except URLError:
        return 0, {'error': 'connection refused'}
    except Exception as e:
        return 0, {'error': repr(e)}


def _http_post(path: str, body: dict, *, host: str = DEFAULT_HOST,
               port: int = DEFAULT_PORT, timeout: float = 600.0) -> tuple[int, dict]:
    payload = json.dumps(body).encode('utf-8')
    req = Request(_base_url(host, port) + path, data=payload, method='POST',
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return resp.status, data
    except URLError as e:
        return 0, {'error': f'connection refused: {e!r}'}
    except Exception as e:
        return 0, {'error': repr(e)}


def is_running(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Return True iff the server responds to /healthz with status='ok'.

    Verifies BOTH the PID file exists AND /healthz returns 200 with
    `status='ok'`. A PID file pointing at a dead/non-responding process
    is treated as not-running and the stale PID file is deleted.
    """
    pid = pid_file()
    if pid.exists():
        try:
            stored = int(pid.read_text().strip())
        except Exception:
            stored = -1
        if stored > 0:
            # Confirm the process exists
            try:
                os.kill(stored, 0)  # signal 0 = no-op, just checks existence
            except (ProcessLookupError, PermissionError):
                # Stale PID file
                try:
                    pid.unlink()
                except Exception:
                    pass
                return False
    # Check /healthz
    status, data = _http_get('/healthz', host=host, port=port)
    return status == 200 and data.get('status') == 'ok'


def status(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Return the /healthz response, or a stub if not running."""
    s, data = _http_get('/healthz', host=host, port=port)
    if s != 200:
        return {'status': 'not running', 'detail': data.get('error', '')}
    return data


def ensure_running(*, skin: str = '1xlasm', config: str = 'prod',
                   port: int = DEFAULT_PORT, idle_timeout: int = 1800,
                   ready_timeout: int = 90, log_to_file: bool = True) -> None:
    """If the server is already running, return immediately. Otherwise
    spawn `python -m ait.caption.joy_server`, wait for /healthz to
    return 200, and return when ready.

    Raises RuntimeError if the server fails to come up within
    `ready_timeout` seconds.
    """
    if is_running(port=port):
        return

    # Compose argv
    py = sys.executable
    cmd = [
        py, '-m', 'ait.caption.joy_server',
        '--skin', skin,
        '--config', config,
        '--port', str(port),
        '--idle-timeout', str(idle_timeout),
    ]
    env = os.environ.copy()
    # Ensure src is on PYTHONPATH so `-m ait.caption.joy_server` resolves
    src_dir = Path(__file__).resolve().parents[2]
    env['PYTHONPATH'] = f'{src_dir}:{env.get("PYTHONPATH", "")}'

    out = None
    if log_to_file:
        out = open(log_file(), 'ab')
    print(f'[joy_client] starting server: {" ".join(cmd)}', flush=True)
    subprocess.Popen(
        cmd,
        stdout=out or subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,  # detach from parent's process group
    )
    # The Popen handle is intentionally not retained — the server is
    # standalone and detached. We use is_running() as the readiness check.

    t0 = time.time()
    while time.time() - t0 < ready_timeout:
        if is_running(port=port):
            print(f'[joy_client] server ready after {time.time()-t0:.1f}s', flush=True)
            return
        time.sleep(1)
    raise RuntimeError(
        f'joy_server did not become ready within {ready_timeout}s '
        f'(check {log_file()})'
    )


def caption(image_url: str, user_content: str, *,
            system_content: Optional[str] = None,
            gen_kwargs: Optional[dict] = None,
            adapter: str = 'default',
            host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
            timeout: float = 600.0,
            retry_once: bool = True) -> tuple[str, str]:
    """POST /caption. Returns `(prompt, caption)`.

    `adapter` selects the LoRA adapter on the server side (default = main
    captioning LoRA; 'hint' = iter-5 hint LoRA when configured via
    skin.lora_hint_path). Pass 'hint' only when calling iter-5 of the
    /img_suggest workflow.

    If the request fails with a connection error AND `retry_once`, tries
    `ensure_running()` and retries the POST once. This handles the case
    where the server crashed between calls in a slash-command session.
    """
    body = {'image_url': str(image_url), 'user_content': user_content}
    if system_content is not None:
        body['system_content'] = system_content
    if gen_kwargs is not None:
        body['gen_kwargs'] = gen_kwargs
    if adapter != 'default':
        body['adapter'] = adapter

    s, data = _http_post('/caption', body, host=host, port=port, timeout=timeout)
    if s != 200 and retry_once and 'connection refused' in data.get('error', ''):
        ensure_running(port=port)
        s, data = _http_post('/caption', body, host=host, port=port, timeout=timeout)
    if s != 200:
        raise RuntimeError(f'/caption failed: {data}')
    return data['prompt'], data['caption']


def shutdown(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
             wait_timeout: float = 10.0) -> bool:
    """Stop the joy_server. Fast path: send SIGTERM directly to the
    process via PID and poll `os.kill(pid, 0)` (no HTTP, no 2s connection
    timeouts). The server's signal handler triggers the same graceful-exit
    path as the HTTP `/shutdown` endpoint.

    Falls back to HTTP `/shutdown` if the PID file is absent or
    unreadable (e.g. server started outside our normal lifecycle).

    Returns True if the process exited within `wait_timeout` seconds.
    Typical: 200-400 ms via SIGTERM, vs ~2-3s via the old HTTP path.
    """
    pid = _read_pid()
    if pid is None or not _process_alive(pid):
        # No PID or stale → confirm via HTTP and clean up.
        if not _http_get_quick('/healthz', host=host, port=port):
            return True
        # PID missing but server responding → fall back to HTTP shutdown.
        _http_post('/shutdown', {}, host=host, port=port, timeout=2.0)
        t0 = time.time()
        while time.time() - t0 < wait_timeout:
            if not is_running(port=port):
                return True
            time.sleep(0.2)
        return False

    # Fast path: SIGTERM and poll process existence.
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    t0 = time.time()
    while time.time() - t0 < wait_timeout:
        if not _process_alive(pid):
            # Process gone; PID file is cleaned by the server's finally
            # block. Verify and force-clean if needed.
            try:
                from .joy_server import pid_file
                p = pid_file()
                if p.exists():
                    stored = p.read_text().strip()
                    if stored == str(pid):
                        p.unlink()
            except Exception:
                pass
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Helpers for fast shutdown
# ---------------------------------------------------------------------------

def _read_pid() -> Optional[int]:
    """Return the PID from the PID file, or None if absent/unreadable."""
    try:
        from .joy_server import pid_file
        p = pid_file()
        if not p.exists():
            return None
        return int(p.read_text().strip())
    except Exception:
        return None


def _process_alive(pid: int) -> bool:
    """True iff the process with this PID exists. Cheap — uses signal 0.

    `PermissionError` means the process exists but we lack rights to
    signal it (different user). For our use case (joy_server launched
    as the same user) this never fires, but we treat it as "alive"
    to be correct.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _http_get_quick(path: str, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Fast `is the server responding` check with a tight 0.5s timeout."""
    status, _ = _http_get(path, host=host, port=port, timeout=0.5)
    return status == 200
