"""Normaliser on generated clips: loud ones attenuated, quiet ones untouched. Needs ffmpeg."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name('normalize_peon_audio.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
class NormalizeTests(unittest.TestCase):
    def test_loud_clip_attenuated_quiet_clip_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sounds = root / 'packs/demo/sounds'
            sounds.mkdir(parents=True)
            for name, volume in (('loud.wav', 1.0), ('quiet.wav', 0.01)):
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'lavfi',
                                '-i', 'sine=frequency=440:duration=1', '-af', f'volume={volume}',
                                str(sounds / name)], check=True)
            manifest = {'name': 'demo', 'categories': {'task.complete': {'sounds': [
                {'file': 'sounds/loud.wav', 'label': 'loud', 'sha256': digest(sounds / 'loud.wav')},
                {'file': 'sounds/quiet.wav', 'label': 'quiet'}]}}}
            (root / 'packs/demo/openpeon.json').write_text(json.dumps(manifest))
            quiet_before = digest(sounds / 'quiet.wav')
            subprocess.run([sys.executable, '-I', str(SCRIPT), '--packs', str(root / 'packs'),
                            '--report-dir', str(root / 'report'), '--apply'],
                           check=True, capture_output=True, timeout=120)
            summary = json.loads((root / 'report/summary.json').read_text())
            self.assertEqual((summary['attenuated'], summary['boosted'], summary['peak_violations']), (1, 0, 0))
            self.assertEqual(digest(sounds / 'quiet.wav'), quiet_before)
            updated = json.loads((root / 'packs/demo/openpeon.json').read_text())
            self.assertEqual(updated['categories']['task.complete']['sounds'][0]['sha256'], digest(sounds / 'loud.wav'))
            self.assertTrue((root / 'report/originals/demo/sounds/loud.wav').exists())


if __name__ == '__main__':
    unittest.main()
