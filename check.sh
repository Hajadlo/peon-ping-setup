#!/usr/bin/env bash
# Repo checks: shell syntax plus every unit test (no audio is ever played).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
bash -n install.sh tools/peon-remote
if shellcheck --version >/dev/null 2>&1; then shellcheck -S warning install.sh tools/peon-remote check.sh; fi
python3 -I -m unittest discover -s tools "$@"
