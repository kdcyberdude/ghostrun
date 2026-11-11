"""Check that a builder workspace is an independent game and has no route to the reference."""
from __future__ import annotations

from pathlib import Path
import re

BANNED_SUFFIXES = {'.nes', '.fds', '.unf', '.state', '.sav', '.fm2'}
BANNED_TEXT = re.compile(r'stable_retro|nes_py|jsnes|fceux|nestopia|mesen|wasm-nes|retroarch', re.I)
SKIP_DIRS = {'node_modules', '.git', 'dist', '.oracle'}
TEXT_SUFFIXES = {'.js', '.mjs', '.ts', '.tsx', '.jsx', '.py', '.html', '.json', '.md', '.sh'}


def paths_are_separate(reference_root, builder_root):
    a, b = Path(reference_root).resolve(), Path(builder_root).resolve()
    return not (a == b or a in b.parents or b in a.parents)


def scan(builder_root, reference_root):
    """Return a list of problems (empty means isolated). The oracle client is the one allowed connection."""
    root, ref = Path(builder_root).resolve(), Path(reference_root).resolve()
    problems = []
    if not paths_are_separate(ref, root):
        problems.append('builder and reference folders overlap')
    stack = [root]
    while stack:
        for p in stack.pop().iterdir():
            rel = p.relative_to(root)
            if p.is_symlink():
                target = p.resolve()
                if target != root and root not in target.parents:
                    problems.append(f'{rel}: symlink leaves the workspace')
                continue
            if p.is_dir():
                if p.name not in SKIP_DIRS:
                    stack.append(p)
                continue
            if p.suffix.lower() in BANNED_SUFFIXES:
                problems.append(f'{rel}: reference file type')
            elif p.suffix.lower() in TEXT_SUFFIXES:
                text = p.read_text(errors='ignore')
                if str(ref) in text:
                    problems.append(f'{rel}: mentions the reference folder')
                m = BANNED_TEXT.search(text)
                if m:
                    problems.append(f'{rel}: mentions emulator {m.group(0)!r}')
    return sorted(problems)
