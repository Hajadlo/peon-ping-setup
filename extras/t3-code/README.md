# T3 Code watcher

For [T3 Code](https://github.com/pingdotgg/t3code) users. Inside T3, provider
hooks fire for every child agent and helper job, which is noisy. With the
watcher installed, `peon-remote` silences raw hooks from T3 processes and
`t3_peon.py` plays sounds only for the main thread: once per completed main
run (after 5 s, and only when no children, background tasks or headless
workers in the same repository are still running), plus pending input or
approval (after 2 s). It reads T3's SQLite state database read-only and never
reads message text. Existing statuses are baselined on first start, so no
backlog plays.

It plays through a peon relay and reuses the helpers in
[`../remote`](../remote/README.md), so set that up first. On a single machine
that runs T3, a local `peon relay --port=19998` is enough.

| File | What |
| --- | --- |
| `t3_peon.py` | The watcher (`--check` reads metadata and plays nothing) |
| `t3_state.py`, `t3_policy.py` | T3 database reads and the play/skip decisions |
| `t3-peon.service` | systemd user unit |

```bash
./install.sh --t3-watcher
python3 ~/.local/lib/peon-ping-setup/t3_peon.py --check
systemctl --user daemon-reload && systemctl --user enable --now t3-peon
journalctl --user -u t3-peon -n 20 --no-pager
```

If T3's database is not at `~/.t3/userdata/statev2.sqlite`, add
`--database <path>` to `ExecStart` in `~/.config/systemd/user/t3-peon.service`.
If an MCP server opens its own input form inside T3 and should still sound,
set `PEON_GATE_INPUT_PASSTHROUGH=<suffix of its script path>` in
`~/.config/peon-ping-setup/remote.env`.

Undo: `systemctl --user disable --now t3-peon` and delete the `t3_*.py` files in
`~/.local/lib/peon-ping-setup/`.
