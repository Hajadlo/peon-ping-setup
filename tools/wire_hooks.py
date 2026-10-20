#!/usr/bin/env python3
"""Register a Peon hook command for Claude Code (settings.json) and print the Codex block.

  python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote          # dry run
  python3 tools/wire_hooks.py --command ~/.local/bin/peon-remote --apply  # edit + backup
  python3 tools/wire_hooks.py --command ... --replace peon-ping/peon.sh --apply
  python3 tools/wire_hooks.py --command ... --codex                       # print TOML only
  python3 tools/wire_hooks.py --command ... --if-missing --apply          # only if no Peon hook yet

Idempotent: an event that already runs the command is left alone. Other hooks
are kept, except those --replace names.
"""
import argparse
import json
from pathlib import Path
import shutil
import time

CLAUDE_EVENTS = ('SessionStart', 'SessionEnd', 'UserPromptSubmit', 'Stop', 'PermissionRequest', 'SubagentStart',
                 'SubagentStop', 'PreCompact', 'Notification', 'PostToolUseFailure')
# Codex's native hooks use the same payload shape; it has no Notification or PostToolUseFailure.
CODEX_EVENTS = ('SessionStart', 'SessionEnd', 'UserPromptSubmit', 'Stop', 'PermissionRequest', 'SubagentStart',
                'SubagentStop', 'PreCompact')


def merge_claude(settings, command, timeout=3, replace=None):
    """Return the number of events added.

    replace: drop other hook commands containing this substring first (e.g. the
    upstream installer's "peon-ping/peon.sh" when switching to peon-remote).
    """
    hooks = settings.setdefault('hooks', {})
    if replace:
        for event, groups in list(hooks.items()):
            for group in groups:
                group['hooks'] = [h for h in group.get('hooks', [])
                                  if h.get('command') == command or replace not in h.get('command', '')]
            hooks[event] = [g for g in groups if g.get('hooks')]
            if not hooks[event]:
                del hooks[event]
    added = 0
    for event in CLAUDE_EVENTS:
        groups = hooks.setdefault(event, [])
        if any(h.get('command') == command for g in groups for h in g.get('hooks', [])):
            continue
        groups.append({'matcher': '', 'hooks': [{'type': 'command', 'command': command, 'timeout': timeout}]})
        added += 1
    return added


def has_peon_hook(settings):
    """True when any hook command already runs Peon (peon.sh, peon-remote, an adapter)."""
    return any('peon' in h.get('command', '') for groups in settings.get('hooks', {}).values()
               for g in groups for h in g.get('hooks', []))


def codex_toml(command, timeout=3):
    lines = ['[features]', 'hooks = true', '']
    for event in CODEX_EVENTS:
        lines += [f'[[hooks.{event}]]', 'matcher = ""', f'[[hooks.{event}.hooks]]', 'type = "command"',
                  f'command = {json.dumps(command)}', f'timeout = {timeout}', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--command', required=True, help='hook command, e.g. ~/.local/bin/peon-remote')
    parser.add_argument('--settings', type=Path, default=Path.home() / '.claude/settings.json')
    parser.add_argument('--apply', action='store_true', help='write settings.json (a backup is kept)')
    parser.add_argument('--replace', metavar='SUBSTRING',
                        help='remove other hook commands containing SUBSTRING (e.g. peon-ping/peon.sh)')
    parser.add_argument('--codex', action='store_true', help='print the Codex config.toml block and exit')
    parser.add_argument('--if-missing', action='store_true',
                        help='leave settings alone when any hook already runs Peon (e.g. the upstream installer wired it)')
    args = parser.parse_args()
    command = str(Path(args.command).expanduser())
    if args.codex:
        print(codex_toml(command))
        return
    settings = json.loads(args.settings.read_text()) if args.settings.exists() else {}
    if args.if_missing and has_peon_hook(settings):
        print(f'Claude Code hooks already run Peon in {args.settings}; left unchanged')
        return
    before = json.dumps(settings)
    added = merge_claude(settings, command, replace=args.replace)
    changed = json.dumps(settings) != before
    if not args.apply:
        print(f'Would add {added} Claude Code hook events for {command} to {args.settings}'
              + (' and remove replaced hooks' if changed and args.replace else '') + ' (use --apply)')
        return
    if changed:
        if args.settings.exists():
            backup = args.settings.with_name(args.settings.name + '.bak-peon-' + time.strftime('%Y%m%d-%H%M%S'))
            shutil.copy2(args.settings, backup)
            print(f'Backup: {backup}')
        args.settings.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.settings.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(settings, indent=2) + '\n')
        tmp.replace(args.settings)
    print(f'Added {added} Claude Code hook events for {command}')


if __name__ == '__main__':
    main()
