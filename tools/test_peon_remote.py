"""Replay hook routing with an isolated home and no network/audio playback."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class RemoteHookTests(unittest.TestCase):
    def run_wrapper(self, *, relay_up=True, t3=False, event='Stop', gate=True):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            lib = home / '.local/lib/peon-ping-setup'
            for path in (lib, home / '.local/share/peon-ping-runtime', home / '.claude/hooks/peon-ping', home / 'bin'):
                path.mkdir(parents=True)
            for name in ('peon_hook_gate.py', 'peon_workers.py', 'peon_background_pending.py'):
                (lib / name).write_bytes((HERE / name).read_bytes())
            (home / '.local/share/peon-ping-runtime/peon.sh').write_text(
                'cat >/dev/null; echo "PLAYED port=$PEON_RELAY_PORT platform=$PEON_PLATFORM"\n')
            curl = home / 'bin/curl'
            curl.write_text('#!/bin/sh\nexit %d\n' % (0 if relay_up else 7))
            curl.chmod(0o700)
            env = dict(os.environ, HOME=str(home), PATH=str(home / 'bin') + ':' + os.environ['PATH'],
                       XDG_CONFIG_HOME=str(home / '.config'))
            for name in ('PEON_QUIET', 'T3CODE_HOME', 'PEON_RUNTIME', 'PEON_SETUP_LIB', 'PEON_RELAY_PORTS',
                         'CLAUDE_PEON_DIR', 'PEON_T3_GATE'):
                env.pop(name, None)
            if t3:
                env['T3CODE_HOME'] = str(home / '.t3')
            if not gate:
                # The test runner itself may be a T3 or headless agent child.
                env['PEON_T3_GATE'] = '0'
            result = subprocess.run(['/bin/bash', str(HERE / 'peon-remote')], input=json.dumps({
                'hook_event_name': event, 'session_id': 'session', 'cwd': '/project'
            }), text=True, capture_output=True, env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_t3_provider_stop_does_not_play_directly(self):
        self.assertNotIn('PLAYED', self.run_wrapper(t3=True), 'T3 child/provider Stop bypassed main-thread policy')

    def test_plain_session_plays_through_first_healthy_relay(self):
        self.assertIn('PLAYED port=19996 platform=ssh', self.run_wrapper(gate=False))

    def test_offline_relay_is_silent(self):
        self.assertNotIn('PLAYED', self.run_wrapper(relay_up=False, gate=False))


if __name__ == '__main__':
    unittest.main()
