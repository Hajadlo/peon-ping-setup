#!/usr/bin/env python3
"""Play Peon sounds for stable main T3 runs and requests for user attention.

Reads T3 Code's state database read-only (metadata only, never message text)
and invokes the Peon runtime once per verified main-thread event.

Environment: PEON_RUNTIME, CLAUDE_PEON_DIR, PEON_RELAY_PORTS (see peon-remote).
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request

from t3_policy import advance, baseline, save
from t3_state import default_database, RunProof, snapshot


def relay_ports():
    return [int(port) for port in os.environ.get('PEON_RELAY_PORTS', '19996,19998').split(',') if port.strip()]


def default_runtime():
    return Path(os.environ.get('PEON_RUNTIME') or Path.home() / '.local/share/peon-ping-runtime/peon.sh')


def peon_dir():
    return Path(os.environ.get('CLAUDE_PEON_DIR') or Path.home() / '.claude/hooks/peon-ping').resolve()


def play(phase, thread, _old_id, _new_id, *, runtime=None, relay_port=None):
    if relay_port is None:
        for port in relay_ports():
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                    if response.status == 200:
                        relay_port = port
                        break
            except OSError:
                pass
    if relay_port is None:
        # Do not queue old sounds for when a client reconnects.
        print(f'Skipped sound: relay offline thread={thread}', flush=True)
        return
    payload = {'session_id': 't3-main-' + thread, 'cwd': str(Path.home())}
    if phase == 'completed':
        payload['hook_event_name'] = 'Stop'
    elif phase == 'approval':
        payload['hook_event_name'] = 'PermissionRequest'
    else:
        payload.update(hook_event_name='Notification', notification_type='elicitation_dialog')
    env = dict(os.environ, PEON_PLATFORM='ssh', PEON_RELAY_HOST='127.0.0.1', PEON_RELAY_PORT=str(relay_port),
               CLAUDE_PEON_DIR=str(peon_dir()), PEON_TEST='1')
    runtime = runtime or default_runtime()
    # Invoke the runtime directly only after verification; provider hook routing stays silent.
    try:
        result = subprocess.run(['/bin/bash', str(runtime)], input=json.dumps(payload), env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        if result.returncode:
            print(f'Skipped sound: runtime failed thread={thread}', flush=True)
    except (OSError, subprocess.TimeoutExpired):
        # Audio is ephemeral; replaying after a delivery timeout creates duplicate sounds.
        print(f'Skipped sound: runtime unavailable thread={thread}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=default_database())
    parser.add_argument('--state', type=Path, default=Path.home() / '.local/state/t3-peon/state.json')
    parser.add_argument('--check', action='store_true', help='read metadata once; no playback')
    args = parser.parse_args()
    if args.check:
        current, _ = snapshot(args.database)
        print(f'Readable T3 main-run metadata: {len(current)} threads; no playback')
        return
    os.umask(0o077)
    records = json.loads(args.state.read_text()) if args.state.exists() else None
    proof = RunProof(args.database)
    print('Watching T3 main runs every 1s; completion 5s; input 2s; errors 15s', flush=True)
    while True:
        try:
            current, _ = snapshot(args.database)
            before = json.dumps(records)
            if records is None:
                records = baseline(current, time.time())
                print('Existing statuses baselined; old sounds suppressed', flush=True)
            else:
                advance(records, current, time.time(), play, confirm_completion=proof)
            if json.dumps(records) != before:
                save(args.state, records)
        except (sqlite3.Error, OSError, subprocess.TimeoutExpired) as error:
            print(f'Peon watcher unavailable ({type(error).__name__}); retrying', flush=True)
        time.sleep(1)


if __name__ == '__main__':
    main()
