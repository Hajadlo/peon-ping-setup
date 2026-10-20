#!/usr/bin/env python3
"""Attenuate loud Peon clips to -23 LUFS / -6 dBTP; retain quiet clips and backups."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import uuid

TARGET_I = -23.0
TARGET_TP = -6.0


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def measure(path):
    result = subprocess.run([
        'ffmpeg', '-hide_banner', '-nostdin', '-threads', '1', '-i', str(path),
        '-af', 'loudnorm=I=-23:TP=-6:LRA=11:dual_mono=true:print_format=json',
        '-f', 'null', '-'
    ], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Audio decode failed: ' + path.name)
    start = result.stderr.rfind('{')
    stats = json.loads(result.stderr[start:result.stderr.rfind('}') + 1])
    return {key: stats[key] for key in ('input_i', 'input_tp', 'input_lra')}


def gain(stats, suffix):
    limits = [0.0]
    integrated, peak = float(stats['input_i']), float(stats['input_tp'])
    if math.isfinite(integrated):
        limits.append(TARGET_I - integrated)
    if math.isfinite(peak):
        # Lossy re-encoding can slightly change decoded true peaks.
        limits.append(TARGET_TP - peak - (0.75 if suffix == '.mp3' else 0.02))
    return min(limits)


def referenced_files(packs):
    files = set()
    missing = []
    manifests = sorted(set(packs.glob('*/openpeon.json')) | set(packs.glob('*/manifest.json')))
    for manifest in manifests:
        value = json.loads(manifest.read_text())
        for category in value.get('categories', {}).values():
            for sound in category.get('sounds', []):
                ref = sound['file']
                path = manifest.parent / (ref if '/' in ref else 'sounds/' + ref)
                if not path.resolve().is_relative_to(packs.resolve()):
                    raise ValueError('Sound escapes pack directory')
                if not path.is_file():
                    missing.append(str(path.relative_to(packs)))
                    continue
                if path.suffix.lower() not in ('.mp3', '.wav'):
                    raise ValueError('Unsupported audio format: ' + path.suffix)
                files.add(path)
    return sorted(files), manifests, sorted(set(missing))


def scan_file(path, packs):
    stats = measure(path)
    return str(path.relative_to(packs)), dict(stats, sha256=sha256(path), gain_db=gain(stats, path.suffix.lower()))


def apply_file(path, record, backup):
    attenuation = record['gain_db']
    if attenuation > -0.05:
        return dict(record, changed=False, output_sha256=sha256(path), output_i=record['input_i'], output_tp=record['input_tp'])
    original = backup if backup.exists() else path
    if sha256(original) != record['sha256']:
        raise RuntimeError('Source changed since measurement: ' + path.name)
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    temporary = path.with_name(path.stem + '.normalizing-' + uuid.uuid4().hex + path.suffix)
    try:
        codec = ['-c:a', 'libmp3lame', '-q:a', '2'] if path.suffix.lower() == '.mp3' else ['-c:a', 'pcm_s16le']
        for _ in range(3):
            result = subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '1',
                '-i', str(original), '-map', '0:a:0', '-vn', '-af', f'volume={attenuation:.6f}dB',
                *codec, str(temporary)
            ], capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError('Audio encode failed: ' + path.name)
            output = measure(temporary)
            excess = max(0.0, float(output['input_i']) - TARGET_I,
                         float(output['input_tp']) - TARGET_TP)
            if excess <= 0.15:
                break
            attenuation -= excess + 0.1
        else:
            raise RuntimeError('Normalized output exceeded level ceiling: ' + path.name)
        digest = sha256(temporary)
        temporary.chmod(path.stat().st_mode & 0o777)
        temporary.replace(path)
        return dict(record, changed=True, gain_db=attenuation, output_sha256=digest,
                    output_i=output['input_i'], output_tp=output['input_tp'])
    finally:
        temporary.unlink(missing_ok=True)


def update_manifests(manifests, packs, results, backup_root):
    for manifest in manifests:
        value = json.loads(manifest.read_text())
        changed = False
        for category in value.get('categories', {}).values():
            for sound in category.get('sounds', []):
                ref = sound['file']
                path = manifest.parent / (ref if '/' in ref else 'sounds/' + ref)
                result = results.get(str(path.relative_to(packs)))
                if result and result['changed'] and 'sha256' in sound and sound['sha256'] != result['output_sha256']:
                    sound['sha256'] = result['output_sha256']
                    changed = True
        if changed:
            backup = backup_root / manifest.relative_to(packs)
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest, backup)
            save(manifest, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packs', type=Path, default=Path.home() / '.claude/hooks/peon-ping/packs')
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    args.packs = args.packs.resolve()
    args.report_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    files, manifests, missing = referenced_files(args.packs)
    save(args.report_dir / 'missing.json', missing)
    if missing:
        print(f'Skipping {len(missing)} already-missing pack references', flush=True)
    scan_path = args.report_dir / 'scan.json'
    if scan_path.exists():
        records = json.loads(scan_path.read_text())
        if set(records) != {str(path.relative_to(args.packs)) for path in files}:
            raise RuntimeError('Pack contents changed; use a fresh report directory')
    else:
        records = {}
        print(f'Measuring {len(files)} clips from {len(manifests)} packs; no playback', flush=True)
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
            pending = [pool.submit(scan_file, path, args.packs) for path in files]
            for future in as_completed(pending):
                ref, result = future.result()
                records[ref] = result
                if len(records) % 50 == 0:
                    print(f'Measured {len(records)}/{len(files)}', flush=True)
        save(scan_path, records)
    loud = sum(record['gain_db'] <= -0.05 for record in records.values())
    print(f'{loud}/{len(records)} clips need attenuation; target -23 LUFS, true peak -6 dBTP', flush=True)
    if not args.apply:
        return
    result_path = args.report_dir / 'results.json'
    results = json.loads(result_path.read_text()) if result_path.exists() else {}
    for index, path in enumerate(files, 1):
        ref = str(path.relative_to(args.packs))
        old = results.get(ref)
        if old:
            current_hash = sha256(path)
            if current_hash == old['output_sha256']:
                continue
            if current_hash != records[ref]['sha256']:
                raise RuntimeError('Clip changed since normalization; use a fresh report directory: ' + ref)
        results[ref] = apply_file(path, records[ref], args.report_dir / 'originals' / ref)
        if index % 25 == 0:
            save(result_path, results)
            print(f'Normalized and verified {index}/{len(files)}', flush=True)
    save(result_path, results)
    update_manifests(manifests, args.packs, results, args.report_dir / 'originals')
    summary = {'clips': len(results), 'packs': len(manifests), 'attenuated': sum(r['changed'] for r in results.values()),
               'target_lufs': TARGET_I, 'true_peak_ceiling_dbtp': TARGET_TP,
               'boosted': sum(r['gain_db'] > 0 for r in results.values()),
               'peak_violations': sum(float(r['output_tp']) > TARGET_TP + 0.15 for r in results.values()),
               'missing_references': len(missing), 'backup': str(args.report_dir / 'originals'), 'finished_at': time.time()}
    save(args.report_dir / 'summary.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
