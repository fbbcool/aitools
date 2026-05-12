---
description: Lifecycle control for the persistent JoyCaption server (subcommands start | stop | status | restart). The server loads the captioner model once and serves caption/probe requests over HTTP, avoiding the ~23s model-load cost on every slash-command invocation.
argument-hint: "<start|stop|status|restart>"
---

`$ARGUMENTS` must be one of: `start`, `stop`, `status`, `restart`. Anything else prints a short usage error.

## Pipeline

```python
from ait.caption import joy_client

cmd = $ARGUMENTS.strip().lower()
if cmd == 'status':
    print(joy_client.status())
elif cmd == 'start':
    joy_client.ensure_running()
    print(joy_client.status())
elif cmd == 'stop':
    ok = joy_client.shutdown()
    print('stopped' if ok else 'shutdown timeout')
elif cmd == 'restart':
    joy_client.shutdown()
    joy_client.ensure_running()
    print(joy_client.status())
else:
    print('usage: /joy_server <start|stop|status|restart>')
```

## When to invoke

- **Before a curator session**: `start` pre-warms the model (~23s) so the first `/caption_image` or `/suggest_image` returns in ~5-10s instead of ~30s.
- **After a session**: `stop` frees ~24 GiB of GPU memory for ComfyUI / other workloads. The server also self-shuts after 30 min of idle, so explicit stop is usually optional.
- **If the captioner misbehaves**: `restart` reloads the model cleanly.
- **To check state**: `status` prints `{status, skin, loaded_at, last_request_at, request_count, idle_seconds}`.

## Configuration

- Port: env var `JOY_SERVER_PORT` (default `7862`).
- Skin: defaults to `1xlasm`. Override via direct CLI: `python -m ait.caption.joy_server --skin <name>`.
- Idle timeout: default 30 min. Override via the CLI or by editing `joy_client.ensure_running(idle_timeout=...)`.
- PID file: `$WORKSPACE/joy_server.pid`.
- Log: `$WORKSPACE/joy_server.log`.

## GPU prerequisite

Starting the server requires ≥16 GiB free GPU memory. If less is available, `ensure_running` raises after the model fails to load. If you see this, free other GPU users (typically ComfyUI) and retry.

## Access rights

Read access to the local HTTP server and write to the PID/log files in `$WORKSPACE`. No DB writes, no canonical-field mutations.

## See also

- `/caption_image <id>` — routes through joy_client when the server is running, falls back to in-process loading when not.
- `/suggest_image <id>` — same.
- `/validate_suggestions count=N` — same.
