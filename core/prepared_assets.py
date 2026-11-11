"""Validate the observed asset kit before an independent builder starts."""
import json
from pathlib import Path

from compare import sha256
from isolation import BANNED_SUFFIXES


def validate_assets(folder):
    if Path(folder).is_symlink():
        raise ValueError('asset folder must not be a symlink')
    root = Path(folder).resolve(strict=True)
    for p in root.rglob('*'):
        if p.is_symlink() or p.suffix.lower() in BANNED_SUFFIXES:
            raise ValueError('asset kit contains a symlink or reference file type')
    manifest = json.loads((root / 'manifest.json').read_text())
    entries = manifest.get('files', [])
    if not isinstance(entries, list) or not entries:
        raise ValueError('asset manifest needs a nonempty files list')
    seen = set()
    for entry in entries:
        name = entry['path']
        path = root / name
        if Path(name).is_absolute() or not path.resolve(strict=True).is_relative_to(root) or path.is_symlink():
            raise ValueError('assets must be ordinary files inside the kit')
        if name in seen or not path.is_file() or not path.stat().st_size:
            raise ValueError(f'duplicate or empty asset: {name}')
        seen.add(name)
        if not entry.get('source') or entry.get('method') not in ('observed-frame', 'observed-audio', 'authored'):
            raise ValueError(f'asset needs provenance and observation/authorship method: {name}')
        if entry.get('sha256') != sha256(path):
            raise ValueError(f'asset hash mismatch: {name}')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != root / 'manifest.json'}
    if actual != seen:
        raise ValueError('asset manifest must cover every file in the kit')
    return manifest
