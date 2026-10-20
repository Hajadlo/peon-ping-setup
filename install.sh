#!/usr/bin/env bash
# Install this repo's packs, config and optional helpers into an existing
# peon-ping installation. Run with --help for options. Safe to re-run: every
# replaced pack or config is moved to a timestamped backup first.
set -euo pipefail

repo="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
stamp="$(date +%Y%m%d-%H%M%S)"
peon_dir="${CLAUDE_PEON_DIR:-}"
do_packs=0 do_config=0 do_refresh=0 do_normalize=0 do_server=0 do_t3=0 do_client=0 dry=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

  --packs             copy every pack in packs/ into <peon-dir>/packs
  --config            merge config.json into <peon-dir>/config.json
  --all               --packs --config
  --refresh-registry  re-download registry packs from their authors
                      (`peon packs install`); replaces the normalised copies
  --normalize         loudness-normalise installed packs (-23 LUFS / -6 dBTP; needs ffmpeg)
  --remote-server     install peon-remote + helpers (agent server side)
  --t3-watcher        install the T3 Code main-thread watcher (implies --remote-server)
  --remote-client     install relay + reverse-tunnel user units (machine with speakers)
  --peon-dir DIR      peon-ping directory (default: $CLAUDE_PEON_DIR,
                      ~/.claude/hooks/peon-ping, then ~/.openpeon)
  --dry-run           print what would happen
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --packs) do_packs=1 ;;
    --config) do_config=1 ;;
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
[ $((do_packs + do_config + do_refresh + do_normalize + do_server + do_client)) -gt 0 ] || { usage; exit 2; }

run() { if [ "$dry" = 1 ]; then echo "+ $*"; else "$@"; fi; }

if [ -z "$peon_dir" ]; then
  for candidate in "$HOME/.claude/hooks/peon-ping" "$HOME/.openpeon"; do
    [ -d "$candidate" ] && { peon_dir="$candidate"; break; }
  done
fi
if [ $((do_packs + do_config + do_refresh + do_normalize)) -gt 0 ]; then
  [ -n "$peon_dir" ] && [ -d "$peon_dir" ] || {
    echo "peon-ping directory not found. Install peon-ping first (SETUP.md step 1) or pass --peon-dir." >&2
    exit 1
  }
  peon_dir="$(cd "$peon_dir" && pwd -P)"
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
    run install -m 0644 "$repo/tools/$f" "$lib/$f"
  done
  run install -m 0755 "$repo/tools/peon-remote" "$HOME/.local/bin/peon-remote"
  if [ ! -e "$HOME/.config/peon-ping-setup/remote.env" ]; then
    run install -m 0600 "$repo/systemd/server/remote.env.example" "$HOME/.config/peon-ping-setup/remote.env"
  fi
  if command -v systemctl >/dev/null; then
    run mkdir -p "$HOME/.config/systemd/user"
    run install -m 0644 "$repo/systemd/server/peon-fanout.service" "$HOME/.config/systemd/user/"
  fi
  echo "Installed ~/.local/bin/peon-remote and helpers in $lib"
  echo "Set PEON_RUNTIME in ~/.config/peon-ping-setup/remote.env if peon.sh is not at ~/.local/share/peon-ping-runtime/peon.sh"
fi

if [ "$do_t3" = 1 ]; then
  for f in t3_peon.py t3_state.py t3_policy.py; do
    run install -m 0644 "$repo/tools/$f" "$HOME/.local/lib/peon-ping-setup/$f"
  done
  if command -v systemctl >/dev/null; then
    run install -m 0644 "$repo/systemd/server/t3-peon.service" "$HOME/.config/systemd/user/"
  fi
  echo "Installed the T3 watcher. Check: python3 ~/.local/lib/peon-ping-setup/t3_peon.py --check"
fi

if [ "$do_client" = 1 ]; then
  run mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/peon-ping-setup"
  run install -m 0644 "$repo/systemd/client/peon-relay.service" "$repo/systemd/client/peon-tunnel.service" \
    "$HOME/.config/systemd/user/"
  if [ ! -e "$HOME/.config/peon-ping-setup/tunnel.env" ]; then
    run install -m 0600 "$repo/systemd/client/tunnel.env.example" "$HOME/.config/peon-ping-setup/tunnel.env"
  fi
  echo "Installed peon-relay/peon-tunnel units. Edit ~/.config/peon-ping-setup/tunnel.env, then:"
  echo "  systemctl --user daemon-reload && systemctl --user enable --now peon-relay peon-tunnel"
fi
