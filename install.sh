#!/usr/bin/env bash
# Set up peon-ping with this repo's packs and config on this machine.
# With no options: install peon-ping if it is missing, copy the packs, merge the
# config and make sure Claude Code (and Codex) hooks run Peon. Safe to re-run:
# every replaced pack, config or settings file is backed up first.
set -euo pipefail

repo="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
stamp="$(date +%Y%m%d-%H%M%S)"
peon_dir="${CLAUDE_PEON_DIR:-}"
claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
codex_dir="${CODEX_HOME:-$HOME/.codex}"
upstream_installer="https://raw.githubusercontent.com/PeonPing/peon-ping/main/install.sh"
do_peon=0 do_packs=0 do_config=0 do_hooks=0 do_refresh=0 do_normalize=0 do_server=0 do_t3=0 do_client=0 dry=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

With no options, does the full local setup (sounds play where the agents run):
install peon-ping if missing, then --packs --config --hooks.

  --packs             copy every pack in packs/ into <peon-dir>/packs
  --config            merge config.json into <peon-dir>/config.json
  --hooks             add Claude Code hooks for <peon-dir>/peon.sh if none run Peon;
                      check Codex hooks when ~/.codex exists
  --all               --packs --config
  --refresh-registry  re-download registry packs from their authors
                      (`peon packs install`); replaces the normalised copies
  --normalize         loudness-normalise installed packs (-23 LUFS / -6 dBTP; needs ffmpeg)
  --peon-dir DIR      peon-ping directory (default: $CLAUDE_PEON_DIR,
                      ~/.claude/hooks/peon-ping, then ~/.openpeon)
  --dry-run           print what would happen; change nothing

Advanced (agents on another machine, T3 Code; see extras/):
  --remote-server     install peon-remote + helpers (agent server side)
  --t3-watcher        install the T3 Code main-thread watcher (implies --remote-server)
  --remote-client     install relay + reverse-tunnel user units (machine with speakers)
EOF
}

[ $# -gt 0 ] || { do_peon=1; do_packs=1; do_config=1; do_hooks=1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --packs) do_packs=1 ;;
    --config) do_config=1 ;;
    --hooks) do_hooks=1 ;;
    --all) do_packs=1; do_config=1 ;;
    --refresh-registry) do_refresh=1 ;;
    --normalize) do_normalize=1 ;;
    --remote-server) do_server=1 ;;
    --t3-watcher) do_server=1; do_t3=1 ;;
    --remote-client) do_client=1 ;;
    --peon-dir) peon_dir="$2"; shift ;;
    --peon-dir=*) peon_dir="${1#*=}" ;;
    --dry-run) dry=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
# --dry-run alone means "show the default local setup".
[ $((do_packs + do_config + do_hooks + do_refresh + do_normalize + do_server + do_client)) -gt 0 ] \
  || { do_peon=1; do_packs=1; do_config=1; do_hooks=1; }

run() { if [ "$dry" = 1 ]; then echo "+ $*"; else "$@"; fi; }

find_peon_dir() {
  [ -n "$peon_dir" ] && return
  for candidate in "$claude_dir/hooks/peon-ping" "$HOME/.openpeon/hooks/peon-ping" "$HOME/.openpeon"; do
    if [ -f "$candidate/peon.sh" ] || [ -f "$candidate/config.json" ]; then peon_dir="$candidate"; return; fi
  done
  return 0
}
find_peon_dir

if [ "$do_peon" = 1 ] && [ -z "$peon_dir" ]; then
  echo "peon-ping is not installed yet; installing it with the upstream installer."
  if command -v peon-ping-setup >/dev/null; then
    run peon-ping-setup
  elif command -v brew >/dev/null; then
    run brew install PeonPing/tap/peon-ping
    run peon-ping-setup
  else
    run bash -c "curl -fsSL $upstream_installer | bash"
  fi
  find_peon_dir
  # A dry run installs nothing; plan against the upstream default location.
  [ -n "$peon_dir" ] || [ "$dry" = 0 ] || peon_dir="$claude_dir/hooks/peon-ping"
fi

if [ $((do_packs + do_config + do_hooks + do_refresh + do_normalize)) -gt 0 ]; then
  [ -n "$peon_dir" ] && { [ -d "$peon_dir" ] || [ "$dry" = 1 ]; } || {
    echo "peon-ping directory not found. Run ./install.sh with no options to install peon-ping," >&2
    echo "or pass --peon-dir if it lives somewhere else." >&2
    exit 1
  }
  [ -d "$peon_dir" ] && peon_dir="$(cd "$peon_dir" && pwd -P)"
  echo "peon-ping directory: $peon_dir"
fi
backup="${peon_dir:-$HOME}/backups/peon-ping-setup-$stamp"

if [ "$do_packs" = 1 ]; then
  run mkdir -p "$peon_dir/packs"
  count=0
  for src in "$repo"/packs/*/; do
    name="$(basename "$src")"
    dest="$peon_dir/packs/$name"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      run mkdir -p "$backup/packs"
      run mv "$dest" "$backup/packs/$name"
    fi
    run cp -R "$src" "$dest"
    count=$((count + 1))
  done
  echo "Installed $count packs into $peon_dir/packs"
  [ -d "$backup/packs" ] && echo "Previous versions of replaced packs: $backup/packs"
fi

if [ "$do_config" = 1 ]; then
  target="$peon_dir/config.json"
  if [ -f "$target" ]; then
    run mkdir -p "$backup"
    run cp "$target" "$backup/config.json"
    echo "Backed up existing config to $backup/config.json"
  fi
  if [ "$dry" = 1 ]; then
    echo "+ merge $repo/config.json into $target"
  else
    # Keys this repo does not set (e.g. newer peon-ping options) keep their current values.
    python3 -I - "$repo/config.json" "$target" <<'PY'
import json, sys
from pathlib import Path
ours = json.loads(Path(sys.argv[1]).read_text())
target = Path(sys.argv[2])
current = json.loads(target.read_text()) if target.exists() else {}
current.update(ours)
tmp = target.with_suffix('.json.tmp')
tmp.write_text(json.dumps(current, indent=2, ensure_ascii=False) + '\n')
tmp.replace(target)
PY
    echo "Merged config.json into $target"
  fi
fi

if [ "$do_hooks" = 1 ]; then
  apply=(--apply); [ "$dry" = 1 ] && apply=()
  python3 -I "$repo/tools/wire_hooks.py" --command "$peon_dir/peon.sh" --settings "$claude_dir/settings.json" \
    --if-missing ${apply[@]+"${apply[@]}"}
  if [ -d "$codex_dir" ]; then
    if grep -qs peon "$codex_dir/config.toml" "$codex_dir/hooks.json"; then
      echo "Codex hooks already run Peon ($codex_dir)"
    else
      echo "Codex has no Peon hooks. Re-run the upstream installer, or print the block to add to"
      echo "$codex_dir/config.toml with: python3 $repo/tools/wire_hooks.py --command $peon_dir/peon.sh --codex"
    fi
  fi
fi

if [ "$do_refresh" = 1 ]; then
  command -v peon >/dev/null || { echo "peon CLI not on PATH; cannot refresh from the registry" >&2; exit 1; }
  names="$(python3 -I -c 'import json,sys; print(",".join(n for n,e in json.load(open(sys.argv[1])).items() if e["origin"]=="registry"))' "$repo/pack-sources.json")"
  run env CLAUDE_PEON_DIR="$peon_dir" peon packs install "$names"
  echo "Refreshed registry packs. Run with --normalize to even out their loudness again."
fi

if [ "$do_normalize" = 1 ]; then
  command -v ffmpeg >/dev/null || { echo "ffmpeg is required for --normalize" >&2; exit 1; }
  report="$HOME/.local/state/peon-audio-normalization/$stamp"
  run python3 -I "$repo/tools/normalize_peon_audio.py" --packs "$peon_dir/packs" \
    --report-dir "$report" --workers "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)" --apply
  echo "Normalisation report and original clips: $report"
fi

if [ "$do_server" = 1 ]; then
  lib="$HOME/.local/lib/peon-ping-setup"
  run mkdir -p "$lib" "$HOME/.local/bin" "$HOME/.config/peon-ping-setup"
  for f in peon_hook_gate.py peon_workers.py peon_background_pending.py peon_fanout.py; do
    run install -m 0644 "$repo/extras/remote/$f" "$lib/$f"
  done
  run install -m 0755 "$repo/extras/remote/peon-remote" "$HOME/.local/bin/peon-remote"
  if [ ! -e "$HOME/.config/peon-ping-setup/remote.env" ]; then
    run install -m 0600 "$repo/extras/remote/systemd/server/remote.env.example" "$HOME/.config/peon-ping-setup/remote.env"
  fi
  if command -v systemctl >/dev/null; then
    run mkdir -p "$HOME/.config/systemd/user"
    run install -m 0644 "$repo/extras/remote/systemd/server/peon-fanout.service" "$HOME/.config/systemd/user/"
  fi
  echo "Installed ~/.local/bin/peon-remote and helpers in $lib"
  echo "Set PEON_RUNTIME in ~/.config/peon-ping-setup/remote.env if peon.sh is not at ~/.local/share/peon-ping-runtime/peon.sh"
fi

if [ "$do_t3" = 1 ]; then
  for f in t3_peon.py t3_state.py t3_policy.py; do
    run install -m 0644 "$repo/extras/t3-code/$f" "$HOME/.local/lib/peon-ping-setup/$f"
  done
  if command -v systemctl >/dev/null; then
    run install -m 0644 "$repo/extras/t3-code/t3-peon.service" "$HOME/.config/systemd/user/"
  fi
  echo "Installed the T3 watcher. Check: python3 ~/.local/lib/peon-ping-setup/t3_peon.py --check"
fi

if [ "$do_client" = 1 ]; then
  run mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/peon-ping-setup"
  run install -m 0644 "$repo/extras/remote/systemd/client/peon-relay.service" "$repo/extras/remote/systemd/client/peon-tunnel.service" \
    "$HOME/.config/systemd/user/"
  if [ ! -e "$HOME/.config/peon-ping-setup/tunnel.env" ]; then
    run install -m 0600 "$repo/extras/remote/systemd/client/tunnel.env.example" "$HOME/.config/peon-ping-setup/tunnel.env"
  fi
  echo "Installed peon-relay/peon-tunnel units. Edit ~/.config/peon-ping-setup/tunnel.env, then:"
  echo "  systemctl --user daemon-reload && systemctl --user enable --now peon-relay peon-tunnel"
fi

if [ "$dry" = 1 ]; then
  echo "Dry run: nothing was changed."
elif [ "$do_peon" = 1 ]; then
  cat <<EOF

Done. Test it (plays sound): peon preview task.complete
Then start a new Claude Code or Codex session and give it a small task; a voice
line plays when it finishes. Anything replaced was backed up under $backup
EOF
fi
