"""Check a recorded signal timeline (audit.py's *.jsonl) for rewards that cannot be right, before any training.

One step should never pay a large share of a level. A jump like that is usually a signed or wrapping RAM byte.
"""
from __future__ import annotations

import json
from pathlib import Path


def lint_rows(rows, progress_unit, tag=''):
    problems, prev = [], None
    for row in rows:
        if prev is not None and row['in_play'] and prev['in_play']:
            where = f"{tag} t{row['t']}"
            if row['level'] == prev['level'] and row.get('progress_valid') and prev.get('progress_valid'):
                jump = row['progress'] - prev['progress']
                if abs(jump) > 0.5 * progress_unit:
                    problems.append(f'{where}: progress jumped {jump:g} (one level is {progress_unit:g})')
            if row['level'] - prev['level'] > 1:
                problems.append(f"{where}: level jumped {prev['level']} -> {row['level']}")
            if row.get('score') is not None and prev.get('score') is not None and row['score'] < prev['score']:
                problems.append(f"{where}: score fell {prev['score']} -> {row['score']}")
            if row.get('lives') is not None and prev.get('lives') is not None and row['lives'] > prev['lives'] + 1:
                problems.append(f"{where}: lives jumped {prev['lives']} -> {row['lives']}")
        prev = row
    return problems


def lint_dir(folder, progress_unit):
    problems = []
    for path in sorted(Path(folder).glob('*.jsonl')):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        problems += lint_rows(rows, progress_unit, path.stem)
    return problems
