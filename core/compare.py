"""Compare a rebuild's per-frame trace with the reference trace, numbers first.

Traces are JSONL rows keyed by 'f'. Tolerances name the fields compared: {field: {"near": 3, "far": 8}}.
A difference above "near" is an event, above "far" a large event. Frames absent from either side are reported.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load(path):
    return {r['f']: r for r in map(json.loads, Path(path).read_text().splitlines()) if r}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(reference, rebuild, tolerances):
    ref, new = load(reference), load(rebuild)
    frames = sorted(set(ref) & set(new))
    events = large = 0
    first, per_field = None, {k: {'events': 0, 'large': 0} for k in tolerances}
    for f in frames:
        for field, tol in tolerances.items():
            a, b = ref[f].get(field), new[f].get(field)
            if a is None or b is None:
                continue
            d = abs(a - b)
            if d > tol['near']:
                events += 1
                per_field[field]['events'] += 1
                first = first or {'frame': f, 'field': field, 'reference': a, 'rebuild': b}
                if d > tol['far']:
                    large += 1
                    per_field[field]['large'] += 1
    return {'frames_compared': len(frames), 'missing_in_rebuild': len(set(ref) - set(new)),
            'extra_in_rebuild': len(set(new) - set(ref)), 'events': events, 'large': large,
            'first_divergence': first, 'per_field': per_field}
