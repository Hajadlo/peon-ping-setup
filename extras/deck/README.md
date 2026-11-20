# Deck rotation mode (optional patch for peon-ping 2.30.0)

Stock peon-ping has `pack_rotation_mode` values `random`, `round-robin` and
`shuffle`. This patch adds `"deck"`: every clip plays once before any repeats.

The repo's `config.json` stays on `"shuffle"`, with per-pack weights chosen so
every clip is about equally likely (see the main README). Deck mode gets the same
fairness exactly, and also keeps the same pack from playing twice in a row.

## What deck mode does

Per category (`task.complete`, `input.required`) there is one deck: every
(pack, file) pair across the unique packs in `pack_rotation`, minus
`disabled_sounds` and manifest entries whose file is missing. Duplicates in
`pack_rotation` are ignored (they are weights in shuffle mode, not here).

- Draws come off a shuffled deck kept in `.state.json`
  (`deck.<category> = {remaining, known, last_pack}`); an empty deck is reshuffled.
- When you add or remove packs or clips, the cycle continues: removed items leave
  the deck, new ones are inserted at random positions.
- The first card whose pack differs from the previous pack is taken, so the same
  pack does not play twice in a row unless nothing else is left.
- The `[sound]` debug log line gains `deck_left=N`.
- Other modes are unchanged. Like them, deck yields to session overrides and
  `path_rules`.
- There is no lock: two hook invocations at the same instant may draw the same
  clip (last write wins), as with the other modes.

## Apply

The patch is a unified diff against peon-ping 2.30.0's `peon.sh`. Run it in the
directory that holds the installed `peon.sh` (for the standard install,
`~/.claude/hooks/peon-ping`):

```bash
cd ~/.claude/hooks/peon-ping
cp peon.sh peon.sh.bak-deck
git apply --check -p1 /path/to/peon-ping-setup/extras/deck/peon-deck.patch   # dry run
git apply -p1 /path/to/peon-ping-setup/extras/deck/peon-deck.patch
```

`git apply` works outside a Git repository; `patch -p1 < peon-deck.patch` does
the same. If peon.sh is a symlink into a package manager (Homebrew), copy the
file out and patch the copy instead, since package upgrades would overwrite it.
A newer peon-ping may no longer match; then the dry run fails and nothing is
changed.

## Set the mode

In `<peon-dir>/config.json`:

```json
"pack_rotation_mode": "deck"
```

Keep `pack_rotation` as is (its duplicates are ignored). Switch back to
`"shuffle"` any time; the saved deck is simply not used.

## Revert

```bash
cd ~/.claude/hooks/peon-ping
cp peon.sh.bak-deck peon.sh        # or: git apply -R -p1 /path/to/extras/deck/peon-deck.patch
```

Re-running peon-ping's own installer or upgrading it also replaces peon.sh, so
reapply the patch afterwards.

## Test

```bash
python3 -I -m unittest discover -s extras/deck
```

It applies the patch to a temporary copy of the installed `peon.sh`
(`$PEON_SH` or `~/.claude/hooks/peon-ping/peon.sh`; an already patched file is
used as is) and runs it for real against a temporary peon directory and a local
recording relay, so no audio plays. It skips when no matching `peon.sh` is
found. `./check.sh` runs it too.
