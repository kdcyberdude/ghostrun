"""Regression gate. Verdicts: PASS, REGRESSION, FAIL.

A baseline pins the reference trace hash and the tolerances. Changing either is a FAIL, so a pass cannot be made by
editing the evidence or loosening the limits. Saving a new baseline is a separate, explicit step.
"""
from __future__ import annotations

import json
from pathlib import Path

from compare import compare, sha256


def tolerance_key(tolerances):
    return json.dumps(tolerances, sort_keys=True)


def run(reference, rebuild, tolerances, baseline_path):
    result = compare(reference, rebuild, tolerances)
    report = {'result': result, 'reasons': []}
    if not result['frames_compared']:
        report['reasons'].append('no frames compared')
    path = Path(baseline_path)
    if not path.exists():
        report['reasons'].append('no baseline saved yet')
        report['verdict'] = 'FAIL'
        return report
    base = json.loads(path.read_text())
    if base['reference_sha256'] != sha256(reference):
        report['reasons'].append('reference trace changed since the baseline')
    if base['tolerances'] != tolerance_key(tolerances):
        report['reasons'].append('tolerances changed since the baseline')
    if report['reasons']:
        report['verdict'] = 'FAIL'
        return report
    for key in ('events', 'large', 'missing_in_rebuild'):
        if result[key] > base['result'][key]:
            report['reasons'].append(f"{key} rose {base['result'][key]} -> {result[key]}")
    report['verdict'] = 'REGRESSION' if report['reasons'] else 'PASS'
    return report


def save_baseline(reference, rebuild, tolerances, baseline_path):
    result = compare(reference, rebuild, tolerances)
    path = Path(baseline_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'reference_sha256': sha256(reference), 'tolerances': tolerance_key(tolerances),
                                'result': result}, indent=1))
    return result
