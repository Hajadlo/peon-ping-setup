# Setup runbook (for a coding agent)

Set up this peon-ping configuration on the machine where Claude Code / Codex
run (Linux or macOS); sounds play on that machine. Run each step's check
before moving on.

Rules:

- `install.sh` backs up every file it replaces. If you edit something by hand,
  copy it to `<file>.bak-<date>` first.
- Never print or copy secrets (API keys, SSH keys, `auth.json`). Nothing here needs one.
- Sounds are audible: tell the user before a step plays one. `check.sh` and
  `--dry-run` never play audio.

## 1. Prerequisites

`bash`, `curl`, `git`, Python 3.11+. `ffmpeg` only for step 4. If peon-ping is
already installed (`peon status` works), the installer keeps it and only adds
what is missing.

## 2. Run the installer

```bash
cd <repo>
./check.sh                 # repo sanity; plays nothing
./install.sh --dry-run     # show the plan; changes nothing
./install.sh
```

With no options it:

1. installs peon-ping if missing, using the upstream installer: Homebrew
   (`brew install PeonPing/tap/peon-ping`, then `peon-ping-setup`) when `brew`
   exists, otherwise
   `curl -fsSL https://raw.githubusercontent.com/PeonPing/peon-ping/main/install.sh | bash`.
   Upstream registers the Claude Code hooks, and Codex hooks when `~/.codex` exists;
2. copies the 51 packs into `<peon-dir>/packs` (`<peon-dir>` is usually
   `~/.claude/hooks/peon-ping`);
3. merges `config.json` into `<peon-dir>/config.json`: keys from this repo win,
   keys it does not set keep their current values;
4. adds Claude Code hooks for `<peon-dir>/peon.sh` only if no hook runs Peon
   yet, and reports whether Codex has Peon hooks.

Replaced packs and the old config go to
`<peon-dir>/backups/peon-ping-setup-<timestamp>/`; a changed
`~/.claude/settings.json` is kept as `settings.json.bak-peon-<timestamp>`.

If it reports that Codex has no Peon hooks, print the block, back up
`~/.codex/config.toml`, and add it by hand (merge `hooks = true` into an
existing `[features]` table rather than adding a second one):

```bash
python3 tools/wire_hooks.py --command "<peon-dir>/peon.sh" --codex
```

Codex asks the user to review and trust new hooks on its next start.

To change packs or weights, edit `pack_rotation` in `<peon-dir>/config.json`
(a pack listed N times is N times as likely).

## 3. Verify

```bash
peon packs list            # the 51 packs appear
python3 -c "import json,os; h=json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks']; print(sorted(e for e,g in h.items() if 'peon' in json.dumps(g)))"
```

Then, after telling the user: `peon preview task.complete` plays the current
pack's clips. Start a new Claude Code session, give it a trivial task ("reply
OK"); a voice line plays when it finishes. `peon logs` shows the event and
pack. Repeat in Codex if the user uses it.

## 4. Optional: loudness normalisation

The packs here are already normalised. Only after
`./install.sh --refresh-registry` (re-downloads the 39 registry packs from
their authors) or after adding other packs:

```bash
./install.sh --normalize       # needs ffmpeg with loudnorm and libmp3lame
```

It only attenuates clips louder than -23 LUFS / -6 dBTP and keeps originals
under `~/.local/state/peon-audio-normalization/<timestamp>/originals/`. Check:
the summary shows `"boosted": 0` and `"peak_violations": 0`.

## Updating and undo

- After `git pull`: `./install.sh` again. New pack versions:
  `./install.sh --refresh-registry --normalize`.
- Undo: restore from `<peon-dir>/backups/peon-ping-setup-<timestamp>/` and
  `~/.claude/settings.json.bak-peon-<timestamp>`.

Agents on a different machine from the speakers, or T3 Code: see
[extras/remote](extras/remote/README.md) and [extras/t3-code](extras/t3-code/README.md).
