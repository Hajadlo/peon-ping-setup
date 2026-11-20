"""Deck rotation mode of peon-ping 2.30.0, run for real against a temporary peon dir and a
local recording relay (PEON_TEST=1, no audible playback).

The patched peon.sh comes from, in order: $PEON_SH (used as is when it already has deck
mode, otherwise patched), ~/.claude/hooks/peon-ping/peon.sh. The patch is always applied to
a temporary copy; the installed file is never modified. Skipped when none is found or the
patch does not apply."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse

PATCH = Path(__file__).resolve().parent / 'peon-deck.patch'
CATEGORY = 'task.complete'
_WORK = tempfile.TemporaryDirectory()


def find_runtime():
    candidates = [os.environ.get('PEON_SH'), Path.home() / '.claude/hooks/peon-ping/peon.sh']
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        text = Path(candidate).read_text()
        if "'deck'" in text:
            return Path(candidate)
        copy = Path(_WORK.name) / 'peon.sh'
        shutil.copyfile(candidate, copy)
        applied = subprocess.run(['git', 'apply', '-p1', str(PATCH)], cwd=_WORK.name, capture_output=True)
        if applied.returncode == 0:
            return copy
    return None


RUNTIME = find_runtime()


@unittest.skipUnless(RUNTIME, 'no peon.sh found that takes the deck patch (set PEON_SH)')
class DeckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.peon = self.home / '.claude/hooks/peon-ping'
        self.peon.mkdir(parents=True)
        self.received = []
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.packs = {}
        self.disabled = {}
        self.rotation = []
        self.counter = 0

    def pack(self, name, files, listed=None):
        """Create a pack; `listed` is the manifest list (defaults to files, may repeat or name missing files)."""
        sounds = self.peon / 'packs' / name / 'sounds'
        sounds.mkdir(parents=True, exist_ok=True)
        for f in files:
            (sounds / f).write_bytes(b'fixture')
        listed = files if listed is None else listed
        manifest = {'name': name, 'categories': {CATEGORY: {'sounds': [{'file': 'sounds/' + f, 'label': f} for f in listed]}}}
        (self.peon / 'packs' / name / 'openpeon.json').write_text(json.dumps(manifest))
        self.packs[name] = files

    def write_config(self, **extra):
        config = {'default_pack': self.rotation[0], 'enabled': True, 'volume': 0.5, 'desktop_notifications': False,
                  'pack_rotation': self.rotation, 'pack_rotation_mode': 'deck', 'debug': True,
                  'categories': {CATEGORY: True}, 'session_start_cooldown_seconds': 0,
                  'disabled_sounds': self.disabled}
        config.update(extra)
        (self.peon / 'config.json').write_text(json.dumps(config))

    def play(self):
        """One task.complete event; returns (pack, filename) taken from the relay request."""
        self.counter += 1
        state_file = self.peon / '.state.json'
        if state_file.exists():  # the runtime debounces Stop for 5s; clear it, keep the deck
            state = json.loads(state_file.read_text())
            state.pop('last_stop_time', None)
            state_file.write_text(json.dumps(state))
        before = len(self.received)
        env = dict(os.environ, HOME=str(self.home), PEON_PLATFORM='ssh', PEON_RELAY_HOST='127.0.0.1',
                   PEON_RELAY_PORT=str(self.server.server_port), CLAUDE_PEON_DIR=str(self.peon), PEON_TEST='1')
        payload = {'hook_event_name': 'Stop', 'session_id': 'deck-%d' % self.counter, 'cwd': str(self.home)}
        result = subprocess.run(['/bin/bash', str(RUNTIME)], input=json.dumps(payload), env=env, text=True,
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        plays = [u for u in self.received[before:] if u.startswith('/play?')]
        self.assertEqual(len(plays), 1, (self.received[before:], result.stdout, result.stderr))
        path = parse_qs(urlparse(plays[0]).query)['file'][0]
        parts = path.split('/')
        return parts[-3], parts[-1]

    def state(self):
        if not (self.peon / '.state.json').exists():
            return {}
        return json.loads((self.peon / '.state.json').read_text())

    def remaining(self):
        deck = self.state().get('deck', {}).get(CATEGORY, {})
        return [(pack, name.split('/')[-1]) for pack, name in deck.get('remaining', [])]

    def draw(self, n):
        return [self.play() for _ in range(n)]

    def total(self):
        return sum(len(v) for v in self.packs.values())

    def test_full_cycle_without_repeats_duplicates_ignored_then_reshuffle(self):
        self.pack('alpha', ['a1.wav', 'a2.wav', 'a3.wav'])
        self.pack('beta', ['b1.wav', 'b2.wav'])
        self.pack('gamma', ['g1.wav', 'g2.wav', 'g3.wav', 'g4.wav'])
        self.rotation = ['alpha', 'alpha', 'alpha', 'beta', 'gamma', 'gamma']  # duplicates are old weighting
        self.write_config()
        expected = {(p, f) for p, fs in self.packs.items() for f in fs}
        for cycle in range(3):
            got = self.draw(self.total())
            self.assertEqual(len(set(got)), len(got), 'repeat inside a cycle: %s' % got)
            self.assertEqual(set(got), expected)
        self.assertEqual(self.remaining(), [])

    def test_deck_left_is_logged(self):
        self.pack('alpha', ['a1.wav', 'a2.wav'])
        self.pack('beta', ['b1.wav'])
        self.rotation = ['alpha', 'beta']
        self.write_config()
        self.play()
        logs = ''.join(p.read_text() for p in (self.peon / 'logs').glob('*.log'))
        self.assertIn('deck_left=2', logs)
        self.assertEqual(len(self.remaining()), 2)

    def test_disabled_and_missing_files_excluded_and_listed_twice_counts_once(self):
        self.pack('alpha', ['a1.wav', 'a2.wav'], listed=['a1.wav', 'a2.wav', 'a2.wav', 'ghost.wav'])
        self.pack('beta', ['b1.wav', 'b2.wav'])
        self.rotation = ['alpha', 'beta']
        self.disabled = {'beta': {CATEGORY: ['b2.wav']}}
        self.write_config()
        got = self.draw(6)
        self.assertEqual(set(got), {('alpha', 'a1.wav'), ('alpha', 'a2.wav'), ('beta', 'b1.wav')})
        self.assertEqual(len(set(got[:3])), 3)
        self.assertEqual(len(set(got[3:])), 3)

    def test_additions_fold_into_running_cycle_without_reset(self):
        self.pack('alpha', ['a1.wav', 'a2.wav', 'a3.wav'])
        self.pack('beta', ['b1.wav', 'b2.wav', 'b3.wav'])
        self.rotation = ['alpha', 'beta']
        self.write_config()
        first = self.draw(2)
        self.pack('alpha', ['a1.wav', 'a2.wav', 'a3.wav', 'a4.wav'])
        self.pack('gamma', ['g1.wav'])
        self.rotation = ['alpha', 'beta', 'gamma']
        self.write_config()
        rest = self.draw(self.total() - 2)
        everything = first + rest
        self.assertEqual(len(set(everything)), len(everything), 'cycle restarted: %s' % everything)
        self.assertEqual(set(everything), {(p, f) for p, fs in self.packs.items() for f in fs})
        self.assertEqual(self.remaining(), [])

    def test_removals_are_dropped_from_remaining(self):
        for name in ('alpha', 'beta', 'gamma'):
            self.pack(name, [name[0] + '%d.wav' % n for n in range(1, 5)])
        self.rotation = ['alpha', 'beta', 'gamma']
        self.write_config()
        first = self.draw(2)
        self.rotation = ['alpha', 'beta']
        self.write_config()
        self.disabled = {'alpha': {CATEGORY: ['a1.wav']}}
        self.write_config()
        remaining = set(self.remaining())
        self.draw(1)  # the draw applies the new eligible set
        kept = {r for r in remaining if r[0] != 'gamma' and r != ('alpha', 'a1.wav')}
        left = set(self.remaining())
        self.assertTrue(left <= kept, (left, kept))
        self.assertEqual(len(left), len(kept) - 1 if kept else 0)
        rest = self.draw(len(left))
        self.assertTrue(all(p != 'gamma' and r != ('alpha', 'a1.wav') for p, r in rest), rest)
        self.assertEqual(set(rest), left)

    def test_no_same_pack_back_to_back_when_avoidable(self):
        self.pack('alpha', ['a1.wav', 'a2.wav', 'a3.wav'])
        self.pack('beta', ['b1.wav', 'b2.wav', 'b3.wav'])
        self.pack('gamma', ['g1.wav', 'g2.wav', 'g3.wav'])
        self.rotation = ['alpha', 'beta', 'gamma']
        self.write_config()
        got = []
        for _ in range(self.total() * 3):  # spans two reshuffle boundaries
            before = self.remaining()
            got.append(self.play())
            if len(got) > 1 and got[-1][0] == got[-2][0]:
                # Allowed only when the deck held nothing else (an unavoidable tail).
                self.assertTrue(before and all(pack == got[-1][0] for pack, _ in before), (before, got))
        self.assertGreater(len(set(p for p, _ in got)), 1)

    def test_other_modes_do_not_touch_the_deck(self):
        self.pack('alpha', ['a1.wav', 'a2.wav'])
        self.rotation = ['alpha']
        self.write_config(pack_rotation_mode='shuffle')
        self.draw(2)
        self.assertNotIn('deck', self.state())


if __name__ == '__main__':
    unittest.main()
