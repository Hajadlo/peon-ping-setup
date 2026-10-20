#!/usr/bin/env bash
# Repo checks: shell syntax plus every unit test (no audio is ever played).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
scripts=(install.sh check.sh extras/remote/peon-remote)
bash -n "${scripts[@]}"
if shellcheck --version >/dev/null 2>&1; then shellcheck -S warning "${scripts[@]}"; fi
for dir in tools extras/remote extras/t3-code; do
  python3 -I -m unittest discover -s "$dir" "$@"
done
