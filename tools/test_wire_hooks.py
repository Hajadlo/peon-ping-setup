"""Hook wiring is idempotent and leaves unrelated hooks alone."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from wire_hooks import CLAUDE_EVENTS, CODEX_EVENTS, codex_toml, merge_claude

SCRIPT = Path(__file__).resolve().with_name('wire_hooks.py')


class WireHooksTests(unittest.TestCase):
    def test_merge_is_idempotent_and_keeps_other_hooks(self):
        other = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'lint'}]}
        settings = {'model': 'x', 'hooks': {'Stop': [other]}}
        self.assertEqual(merge_claude(settings, '/bin/peon'), len(CLAUDE_EVENTS))
        self.assertEqual(merge_claude(settings, '/bin/peon'), 0)
        self.assertEqual(settings['hooks']['Stop'][0], other)
        self.assertEqual(settings['model'], 'x')

    def test_replace_swaps_upstream_hook(self):
        upstream = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'bash ~/.claude/hooks/peon-ping/peon.sh'}]}
        other = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'lint'}]}
        settings = {'hooks': {'Stop': [upstream, other], 'PreToolUse': [json.loads(json.dumps(upstream))]}}
        merge_claude(settings, '/bin/peon-remote', replace='peon-ping/peon.sh')
        self.assertNotIn('PreToolUse', settings['hooks'])
        commands = [h['command'] for g in settings['hooks']['Stop'] for h in g['hooks']]
        self.assertEqual(commands, ['lint', '/bin/peon-remote'])

    def test_codex_block_is_valid_toml(self):
        parsed = tomllib.loads(codex_toml('/bin/peon'))
        self.assertTrue(parsed['features']['hooks'])
        self.assertEqual(set(parsed['hooks']), set(CODEX_EVENTS))
        self.assertEqual(parsed['hooks']['Stop'][0]['hooks'][0]['command'], '/bin/peon')

    def test_apply_writes_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'settings.json'
            settings.write_text('{"hooks": {}}')
            subprocess.run([sys.executable, '-I', str(SCRIPT), '--command', '/bin/peon', '--settings', str(settings),
                            '--apply'], check=True, capture_output=True)
            self.assertEqual(len(json.loads(settings.read_text())['hooks']), len(CLAUDE_EVENTS))
            self.assertEqual(len(list(Path(directory).glob('settings.json.bak-peon-*'))), 1)


if __name__ == '__main__':
    unittest.main()
