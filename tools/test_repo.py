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

    def test_install_into_scratch_home(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            peon = home / '.claude/hooks/peon-ping'
            (peon / 'packs/peon').mkdir(parents=True)
            (peon / 'config.json').write_text('{"volume": 0.9, "future_option": true}')
            env = dict(os.environ, HOME=str(home))
            env.pop('CLAUDE_PEON_DIR', None)
            subprocess.run(['bash', str(ROOT / 'install.sh'), '--all'], check=True, capture_output=True, env=env)
            config = json.loads((peon / 'config.json').read_text())
            self.assertEqual((config['volume'], config['future_option']), (0.5, True))
            self.assertEqual({p.name for p in (peon / 'packs').iterdir()}, {p.name for p in PACKS.iterdir() if p.is_dir()})
            self.assertEqual(len(list(peon.glob('backups/peon-ping-setup-*/packs/peon'))), 1)


if __name__ == '__main__':
    unittest.main()
