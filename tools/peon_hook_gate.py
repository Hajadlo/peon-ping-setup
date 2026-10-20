"""Silence T3 and headless-worker hooks; the main-run watcher owns T3 sounds.

Exit 0 means "silence this hook". PEON_GATE_INPUT_PASSTHROUGH may list
comma-separated argv suffixes of ancestor processes (for example an MCP server
that opens its own browser form) whose input-required notifications should
still play even inside T3.
"""
import os
import json
from pathlib import Path
import sys
from peon_workers import headless_worker


def passthrough_suffixes():
    return tuple(part.strip() for part in os.environ.get('PEON_GATE_INPUT_PASSTHROUGH', '').split(',') if part.strip())


def t3_process(pid=None, proc_root=Path('/proc'), *, interview_input=False):
    """Raw hooks from T3 or automated CLI children must not play independently."""
    pid = pid or os.getppid()
    suffixes = passthrough_suffixes() if interview_input else ()
    while pid > 1:
        try:
            proc = proc_root / str(pid)
            args = proc.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
            # Input forms opened outside T3's request table still need their sound.
            if suffixes and any(arg.endswith(suffixes) for arg in args):
                return False
            if headless_worker(args):
                return True
            if Path(args[0]).name in ('t3', 't3-code'):
                return True
            pid = int(next(line.split()[1] for line in proc.joinpath('status').read_text().splitlines()
                           if line.startswith('PPid:')))
        except (OSError, ValueError, IndexError, StopIteration):
            break
    return bool(os.environ.get('T3CODE_HOME'))


if __name__ == '__main__':
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        event = {}
    interview_input = event.get('hook_event_name') == 'Notification' and event.get('notification_type') == 'elicitation_dialog'
    sys.exit(0 if t3_process(interview_input=interview_input) else 1)
