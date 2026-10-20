# Setup runbook (for a coding agent)

Reproduce this peon-ping setup on Linux or macOS. Work through the steps in
order and run each step's check before moving on. Steps 5 to 7 are optional;
ask the user whether they want them.

Rules while doing this:

- Every step that edits an existing file keeps a backup (the scripts do this);
  if you edit something by hand, copy it to `<file>.bak-<date>` first.
- Never commit, print or copy secrets (API keys, SSH keys, tokens, `auth.json`).
  Nothing in this setup needs one.
- Sounds are audible. Tell the user before a step plays one; the tests and
  `check.sh` never play audio.
- Requirements: `bash`, `curl`, Python 3.11+, `git`; `ffmpeg` only for step 4.

Placeholders: `<repo>` is this checkout, `<peon-dir>` is the peon-ping
directory (`~/.claude/hooks/peon-ping` for the upstream installer, or
`~/.openpeon` for some Homebrew setups; `install.sh` finds it).

## 1. Install peon-ping

Skip if `peon --version` (or `peon status`) already works.

- Homebrew (macOS or Linux): `brew install PeonPing/tap/peon-ping`, then run
  `peon-ping-setup` to register hooks.
- Otherwise: `curl -fsSL https://raw.githubusercontent.com/PeonPing/peon-ping/main/install.sh | bash`
  (read the script first if the user wants to; it can also be run from a clone
  of <https://github.com/PeonPing/peon-ping>).

The upstream installer registers hooks for Claude Code
(`~/.claude/settings.json`) and, when `~/.codex` exists, for Codex. It may
download a few default packs; they stay installed alongside ours.

Check: `peon status` reports peon-ping active; `<peon-dir>/peon.sh`
exists (or `$(brew --prefix peon-ping)/libexec/peon.sh`). Ensure Codex is
covered: `grep -n peon ~/.codex/config.toml ~/.codex/hooks.json 2>/dev/null`.

## 2. Install the packs and config

```bash
cd <repo>
./check.sh                       # repo sanity; plays nothing
./install.sh --all               # copies packs/, merges config.json
```

`--all` copies all 51 packs into `<peon-dir>/packs` and merges `config.json`
into `<peon-dir>/config.json`: keys from this repo win, keys it does not set
(newer peon-ping options) keep their current values. Replaced packs and the
old config go to `<peon-dir>/backups/peon-ping-setup-<timestamp>/`.

If the user wants different packs or weights, edit `pack_rotation` in
`<peon-dir>/config.json` afterwards (a pack listed N times is N times as likely)
rather than in the repo.

Check:

```bash
peon packs list            # the 51 packs appear
python3 -c "import json,os; print(json.load(open(os.path.expanduser('<peon-dir>/config.json')))['categories'])"
                           # only task.complete and input.required are true
```

Audible check (tell the user first; it plays every `task.complete` clip of
the current pack in turn): `peon preview task.complete`.

## 3. Hooks for Claude Code and Codex

For a local setup (sounds play on the same machine as the agent) step 1
already wired the hooks. Confirm:

```bash
python3 -c "import json,os; h=json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks']; print(sorted(e for e,g in h.items() if 'peon' in json.dumps(g)))"
grep -n 'peon' ~/.codex/config.toml ~/.codex/hooks.json 2>/dev/null
```

If Claude Code hooks are missing, add them (dry run first, then `--apply`):

```bash
python3 tools/wire_hooks.py --command "<peon-dir>/peon.sh"
python3 tools/wire_hooks.py --command "<peon-dir>/peon.sh" --apply
```

If Codex hooks are missing, print the block and add it to
`~/.codex/config.toml` by hand (back the file up first; merge `hooks = true`
into an existing `[features]` table instead of adding a second one):

```bash
python3 tools/wire_hooks.py --command "<peon-dir>/peon.sh" --codex
```

Codex asks the user to review and trust new hooks on its next start; they must
approve them there.

Check: start a new Claude Code session, give it a trivial task ("reply OK");
a voice line plays when it finishes. `peon logs` (with `debug: true`) shows the
event and pack. Repeat in Codex.

## 4. Optional: loudness normalisation (after refreshing packs)

The packs in this repo are already normalised. Run this only after
`./install.sh --refresh-registry` (which re-downloads the 39 registry packs
from their authors) or after adding other packs:

```bash
./install.sh --normalize       # needs ffmpeg with loudnorm and libmp3lame
```

It attenuates clips louder than -23 LUFS integrated or -6 dBTP true peak,
never boosts quiet ones, updates manifest checksums, and keeps every original
under `~/.local/state/peon-audio-normalization/<timestamp>/originals/`. To
measure without changing anything:
`python3 tools/normalize_peon_audio.py --report-dir /tmp/peon-scan` (no `--apply`).

Check: the printed summary shows `"boosted": 0` and `"peak_violations": 0`.

## 5. Optional: agents on a server, sounds on your desktop

Use this when Claude Code / Codex run on a headless machine (the *server*) and
sounds should play on the machine with speakers (the *client*). The server
picks the clip; the client's peon relay plays **its own copy** of that pack,
so steps 1 and 2 must be done on both machines.

```
server: hook -> peon-remote -> peon.sh (PEON_PLATFORM=ssh)
        -> 127.0.0.1:19998 --(ssh -R reverse tunnel)--> client 127.0.0.1:19998 peon relay -> speakers
optional: 127.0.0.1:19996 peon-fanout -> several client relays
```

On the **server**:

```bash
./install.sh --remote-server
```

This installs `~/.local/bin/peon-remote`, helpers in
`~/.local/lib/peon-ping-setup/`, and `~/.config/peon-ping-setup/remote.env`.
Set `PEON_RUNTIME` there to the real upstream `peon.sh` (for example
`<peon-dir>/peon.sh` or `$(brew --prefix peon-ping)/libexec/peon.sh`). Do not
point it at `peon-remote` itself. Then switch the hooks so each event runs
`peon-remote` instead of `peon.sh` (otherwise both fire):

```bash
python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote --replace peon-ping/peon.sh --apply
python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote --codex   # replace Codex's peon commands with this
```

`peon-remote` silences hooks while a background command of the same Claude
session is still running, and (unless `PEON_T3_GATE=0`) hooks from T3 Code and
headless `codex exec` / `claude -p` workers; see step 6. With no relay
reachable it exits silently within about a second.

On the **client** (Linux with systemd user units):

```bash
./install.sh --remote-client
$EDITOR ~/.config/peon-ping-setup/tunnel.env     # PEON_SERVER=<ssh host alias>
systemctl --user daemon-reload
systemctl --user enable --now peon-relay peon-tunnel
```

The tunnel needs non-interactive SSH from client to server (`BatchMode=yes`):
a key in the agent or an SSH config entry. The relay binds loopback only; the
server reaches it only through the tunnel. On macOS, run `peon relay` and the
same `ssh -N -R 127.0.0.1:19998:127.0.0.1:19998 <server>` under launchd or a
terminal instead of the units.

Several clients: on the server, set `PEON_FANOUT_BACKENDS` in `remote.env`
(comma-separated `host:port`, e.g. a tunnelled desktop `127.0.0.1:19998` and a
laptop relay on its private-network address; that relay then needs
`--bind=<that address>`), and `systemctl --user enable --now peon-fanout`.
`peon-remote` tries `PEON_RELAY_PORTS` (default `19996,19998`) in order.

Checks:

```bash
# client
systemctl --user status peon-relay peon-tunnel
curl -fsS http://127.0.0.1:19998/health        # OK
# server
curl -fsS http://127.0.0.1:19998/health        # OK through the tunnel
echo '{"hook_event_name":"Stop","session_id":"setup-check","cwd":"'"$HOME"'"}' | PEON_T3_GATE=0 ~/.local/bin/peon-remote
```

The last command plays a sound on the client (tell the user first).

## 6. Optional: T3 Code watcher

For [T3 Code](https://github.com/pingdotgg/t3code) users. Inside T3, provider
hooks fire for every child agent and helper job, which is noisy. With the
watcher installed, `peon-remote` silences raw hooks from T3 processes and
`t3_peon.py` plays sounds only for the main thread: once per completed main
run (after 5 s, and only when no children, background tasks or headless
workers in the same repository are still running), plus pending input or
approval (after 2 s). It reads T3's SQLite state database read-only and never
reads message text. Existing statuses are baselined on first start, so no
backlog plays.

It currently plays through a relay (step 5). On the server (or the single
machine that runs T3, with a local `peon relay` on 19998):

```bash
./install.sh --t3-watcher
python3 ~/.local/lib/peon-ping-setup/t3_peon.py --check   # reads metadata, plays nothing
systemctl --user daemon-reload && systemctl --user enable --now t3-peon
journalctl --user -u t3-peon -n 20 --no-pager
```

If T3's database is not at `~/.t3/userdata/statev2.sqlite`, add
`--database <path>` to `ExecStart` in `~/.config/systemd/user/t3-peon.service`.
If an MCP server opens its own input form inside T3 and should still sound,
set `PEON_GATE_INPUT_PASSTHROUGH=<suffix of its script path>` in `remote.env`.

## 7. Updating later

- New pack versions: `./install.sh --refresh-registry --normalize`.
- After `git pull` of this repo: `./install.sh --all` (backs up what it replaces).
- Re-run `./check.sh` after editing anything in `tools/`.

## Undo

- Packs/config: restore from `<peon-dir>/backups/peon-ping-setup-<timestamp>/`.
- Hooks: `~/.claude/settings.json.bak-peon-<timestamp>`; remove the Codex blocks you added.
- Remote/T3: `systemctl --user disable --now peon-fanout t3-peon peon-relay peon-tunnel`,
  then delete `~/.local/bin/peon-remote`, `~/.local/lib/peon-ping-setup/` and
  `~/.config/peon-ping-setup/`.
