---
description: Lifecycle control for the persistent JoyCaption server (subcommands start | stop | status | restart). The server loads the captioner model once and serves caption/probe requests over HTTP, avoiding the ~23s model-load cost on every slash-command invocation.
argument-hint: "<start|stop|status|restart> [skin=<name>]"
---

`$ARGUMENTS` must start with one of: `start`, `stop`, `status`, `restart`, optionally followed by `skin=<name>` (default `1xlasm`). Anything else prints a short usage error.

The `skin=` term picks which skin the server is started / restarted with. Default `1xlasm` preserves the current behavior. If `start` is invoked while a server is already running with a different skin, `joy_client.ensure_running` cleanly shuts the old one down and respawns with the new skin (only one skin's weights fit in VRAM at a time).

## Pipeline

```python
import re
from ait.caption import joy_client

raw = ($ARGUMENTS or '').strip()
m = re.match(r'(?i)\b(start|stop|status|restart)\b', raw)
cmd = (m.group(1).lower() if m else raw.lower())
sm = re.search(r'\bskin\s*=\s*(\S+)', raw, re.IGNORECASE)
skin = sm.group(1) if sm else '1xlasm'

if cmd == 'status':
    print(joy_client.status())
elif cmd == 'start':
    joy_client.ensure_running(skin=skin)
    print(joy_client.status())
elif cmd == 'stop':
    ok = joy_client.shutdown()
    print('stopped' if ok else 'shutdown timeout')
elif cmd == 'restart':
    joy_client.shutdown()
    joy_client.ensure_running(skin=skin)
    print(joy_client.status())
else:
    print('usage: /joy_server <start|stop|status|restart> [skin=<name>]')
```

## When to invoke

- **Before a curator session**: `start` pre-warms the model (~23s) so the first `/img_caption` or `/img_suggest` returns in ~5-10s instead of ~30s.
- **After a session**: `stop` frees ~24 GiB of GPU memory for ComfyUI / other workloads. The server also self-shuts after 30 min of idle, so explicit stop is usually optional.
- **If the captioner misbehaves**: `restart` reloads the model cleanly.
- **To check state**: `status` prints `{status, skin, loaded_at, last_request_at, request_count, idle_seconds}`.

## Configuration

- Port: env var `JOY_SERVER_PORT` (default `7862`).
- Skin: defaults to `1xlasm`. Override via `/joy_server start skin=<name>` (or restart) — this drives `joy_client.ensure_running(skin=...)`, which automatically restarts the server if a different skin is currently loaded. The lower-level direct CLI `python -m ait.caption.joy_server --skin <name>` also still works. The server is DB-free: it loads from disk (model cache, skin JSON, AInstallerDB YAML) and does NOT open a MongoDB connection. Scene-image lookups happen on the client side; the server's `/caption` HTTP API takes raw `image_url` strings.
- Idle timeout: default 30 min. Override via the CLI or by editing `joy_client.ensure_running(idle_timeout=...)`.
- PID file: `$WORKSPACE/joy_server.pid`.
- Log: `$WORKSPACE/joy_server.log`.

## GPU prerequisite

Starting the server requires ≥16 GiB free GPU memory. If less is available, `ensure_running` raises after the model fails to load. If you see this, free other GPU users (typically ComfyUI) and retry.

## Access rights

Read access to the local HTTP server and write to the PID/log files in `$WORKSPACE`. No DB writes, no canonical-field mutations.

## See also

- `/img_caption <id>` — routes through joy_client when the server is running, falls back to in-process loading when not.
- `/img_suggest <id>` — same.
- `/imgs_validate_suggestions count=N` — same.
