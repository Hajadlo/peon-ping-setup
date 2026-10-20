"""Repo consistency: packs, manifests, config and install.sh against a scratch home."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
PACKS = ROOT / 'packs'
# Upstream manifest references a clip its release does not ship.
KNOWN_MISSING = {'r2d2/sounds/Error3.mp3'}


class RepoTests(unittest.TestCase):
    def test_manifests_reference_existing_audio(self):
        missing = set()
        for manifest in PACKS.glob('*/openpeon.json'):
            for category in json.loads(manifest.read_text()).get('categories', {}).values():
                for sound in category.get('sounds', []):
                    path = manifest.parent / sound['file']
                    if not path.is_file():
                        missing.add(str(path.relative_to(PACKS)))
        self.assertEqual(missing, KNOWN_MISSING)

    def test_every_pack_has_a_source_and_rotation_entries_exist(self):
        packs = {p.name for p in PACKS.iterdir() if p.is_dir()}
        sources = json.loads((ROOT / 'pack-sources.json').read_text())
        self.assertEqual(set(sources), packs)
        config = json.loads((ROOT / 'config.json').read_text())
        self.assertLessEqual(set(config['pack_rotation']), packs)
        self.assertIn(config['default_pack'], packs)

    def test_no_file_near_github_limits(self):
        large = [p for p in ROOT.rglob('*') if '.git' not in p.parts and p.is_file() and p.stat().st_size > 50 * 2**20]
        self.assertEqual(large, [])

    @staticmethod
    def scratch_env(home, path=None):
        env = dict(os.environ, HOME=str(home))
        for name in ('CLAUDE_PEON_DIR', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            env.pop(name, None)
        if path:
            env['PATH'] = path
        return env

    def test_default_dry_run_plans_local_setup_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            # No peon, peon-ping-setup or brew on this PATH: the upstream curl installer is planned.
            result = subprocess.run(['bash', str(ROOT / 'install.sh'), '--dry-run'], check=True, text=True,
                                    capture_output=True, env=self.scratch_env(home, '/usr/bin:/bin'))
            out = result.stdout
            self.assertIn('raw.githubusercontent.com/PeonPing/peon-ping/main/install.sh | bash', out)
            peon = home / '.claude/hooks/peon-ping'
            self.assertIn(f'cp -R {PACKS}/peon/ {peon}/packs/peon', out)
            self.assertIn(f'merge {ROOT}/config.json into {peon}/config.json', out)
            self.assertIn(f'Claude Code hook events for {peon}/peon.sh', out)
            for remote in ('peon-remote', 'systemd', 'relay', 'tunnel', 't3_peon', 't3-peon', 'extras/'):
                self.assertNotIn(remote, out)
            self.assertEqual(list(home.iterdir()), [], 'a dry run wrote into HOME')

    def test_default_run_fills_missing_claude_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            peon = home / '.claude/hooks/peon-ping'
            peon.mkdir(parents=True)
            (peon / 'peon.sh').write_text('#!/bin/sh\n')
            settings = home / '.claude/settings.json'
            settings.write_text('{"model": "x"}')
            subprocess.run(['bash', str(ROOT / 'install.sh')], check=True, capture_output=True,
                           env=self.scratch_env(home))
            hooks = json.loads(settings.read_text())['hooks']
            self.assertEqual(hooks['Stop'][0]['hooks'][0]['command'], str(peon.resolve() / 'peon.sh'))
            self.assertEqual(len(list(home.glob('.claude/settings.json.bak-peon-*'))), 1)
            self.assertTrue((peon / 'packs/originalwar-peons/openpeon.json').is_file())

    def test_install_into_scratch_home(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            peon = home / '.claude/hooks/peon-ping'
            (peon / 'packs/peon').mkdir(parents=True)
            (peon / 'config.json').write_text('{"volume": 0.9, "future_option": true}')
            subprocess.run(['bash', str(ROOT / 'install.sh'), '--all'], check=True, capture_output=True,
                           env=self.scratch_env(home))
            config = json.loads((peon / 'config.json').read_text())
            self.assertEqual((config['volume'], config['future_option']), (0.5, True))
            self.assertEqual({p.name for p in (peon / 'packs').iterdir()}, {p.name for p in PACKS.iterdir() if p.is_dir()})
            self.assertEqual(len(list(peon.glob('backups/peon-ping-setup-*/packs/peon'))), 1)


if __name__ == '__main__':
    unittest.main()
