# Remote relay: agents on a server, sounds on your desktop

Use this only when Claude Code / Codex run on a headless machine (the *server*)
and sounds should play on the machine with speakers (the *client*). For the
usual case, where agents run on the machine you sit at, `./install.sh` in the
repo root is all you need.

The server picks the clip; the client's peon relay plays **its own copy** of
that pack, so run the local setup (`./install.sh`) on both machines first.

```
server: hook -> peon-remote -> peon.sh (PEON_PLATFORM=ssh)
        -> 127.0.0.1:19998 --(ssh -R reverse tunnel)--> client 127.0.0.1:19998 peon relay -> speakers
optional: 127.0.0.1:19996 peon-fanout -> several client relays
```

| File | What |
| --- | --- |
| `peon-remote` | Hook command on the server: gates, then runs `peon.sh` against the relay |
| `peon_hook_gate.py`, `peon_workers.py` | Silence hooks from T3 Code and headless `codex exec` / `claude -p` workers |
| `peon_background_pending.py` | Silence a session while its background command is still running |
| `peon_fanout.py` | Optional: forward each sound to several client relays |
| `systemd/server/` | `peon-fanout.service`, `remote.env.example` |
| `systemd/client/` | `peon-relay.service`, `peon-tunnel.service`, `tunnel.env.example` |

## Server

```bash
./install.sh --remote-server
```

This installs `~/.local/bin/peon-remote`, helpers in
`~/.local/lib/peon-ping-setup/`, and `~/.config/peon-ping-setup/remote.env`.
Set `PEON_RUNTIME` there to the real upstream `peon.sh` (for example
`~/.claude/hooks/peon-ping/peon.sh` or `$(brew --prefix peon-ping)/libexec/peon.sh`).
Do not point it at `peon-remote` itself. Then switch the hooks so each event
runs `peon-remote` instead of `peon.sh` (otherwise both fire):

```bash
python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote --replace peon-ping/peon.sh --apply
python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote --codex   # replace Codex's peon commands with this
```

`peon-remote` silences hooks while a background command of the same Claude
session is still running, and (unless `PEON_T3_GATE=0`) hooks from T3 Code and
headless workers. With no relay reachable it exits silently within about a second.

## Client (Linux with systemd user units)

```bash
./install.sh --remote-client
$EDITOR ~/.config/peon-ping-setup/tunnel.env     # PEON_SERVER=<ssh host alias>
systemctl --user daemon-reload
systemctl --user enable --now peon-relay peon-tunnel
```

The tunnel needs non-interactive SSH from client to server (`BatchMode=yes`):
a key in the agent or an SSH config entry. The relay binds loopback only; the
server reaches it only through the tunnel. On macOS, run `peon relay` and
`ssh -N -R 127.0.0.1:19998:127.0.0.1:19998 <server>` under launchd or a
terminal instead of the units.

Several clients: on the server, set `PEON_FANOUT_BACKENDS` in `remote.env`
(comma-separated `host:port`, e.g. a tunnelled desktop `127.0.0.1:19998` and a
laptop relay on its private-network address; that relay then needs
`--bind=<that address>`), and `systemctl --user enable --now peon-fanout`.
`peon-remote` tries `PEON_RELAY_PORTS` (default `19996,19998`) in order.

## Checks

```bash
# client
systemctl --user status peon-relay peon-tunnel
curl -fsS http://127.0.0.1:19998/health        # OK
# server
curl -fsS http://127.0.0.1:19998/health        # OK through the tunnel
echo '{"hook_event_name":"Stop","session_id":"setup-check","cwd":"'"$HOME"'"}' | PEON_T3_GATE=0 ~/.local/bin/peon-remote
```

The last command plays a sound on the client.

## Undo

`systemctl --user disable --now peon-fanout peon-relay peon-tunnel`, then delete
`~/.local/bin/peon-remote`, `~/.local/lib/peon-ping-setup/` and
`~/.config/peon-ping-setup/`. Restore hooks from
`~/.claude/settings.json.bak-peon-<timestamp>`.
