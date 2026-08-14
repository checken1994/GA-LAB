#!/usr/bin/env python3
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def snapshot(src: Path, dst: Path) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise FileExistsError(dst)
    src_uri = f'file:{src.resolve().as_posix()}?mode=ro'
    with sqlite3.connect(src_uri, uri=True, timeout=10) as source:
        with sqlite3.connect(dst) as target:
            source.backup(target)
            target.commit()
            integrity = target.execute('PRAGMA integrity_check').fetchone()[0]
    return {'source': str(src.resolve()), 'snapshot': str(dst.resolve()), 'sha256': sha256(dst), 'integrity_check': integrity}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    stamp = __import__('datetime').datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    out_dir = root / '.private-secrets' / 'release-audit' / 'scp-247' / 'experiments' / 'snapshots' / stamp
    results = []
    for rel in ('data/v13.db', 'data/kb_evolve.sqlite'):
        src = root / rel
        dst = out_dir / Path(rel).name
        results.append(snapshot(src, dst))
    manifest = out_dir / 'manifest.json'
    manifest.write_text(json.dumps({'created_utc': __import__('datetime').datetime.utcnow().isoformat() + 'Z', 'snapshots': results}, indent=2), encoding='utf-8')
    print(json.dumps({'manifest': str(manifest), 'snapshots': results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
