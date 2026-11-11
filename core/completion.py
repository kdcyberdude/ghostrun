"""Completion evidence is stricter than a no-regression baseline.

This validates supplied measurements, not the honesty or exhaustiveness of an agent's claims.
"""
import json
import math
from pathlib import Path

from compare import compare, load, sha256

GROUPS = ('player', 'enemies', 'rules', 'outcome')


def validate_contract(contract):
    if contract.get('full_game') is not True or not contract.get('scope_basis'):
        raise ValueError('reference contract must explain full-game scope, including loops/ending')
    if not contract.get('levels') or len(set(contract['levels'])) != len(contract['levels']):
        raise ValueError('reference contract needs distinct level/rule-regime identifiers')
    if not {'clear', 'heldout'} <= set(contract.get('cases', [])):
        raise ValueError('reference contract needs clear and heldout routes')
    for group in GROUPS:
        if not contract.get('fields', {}).get(group) and not contract.get('not_applicable', {}).get(group):
            raise ValueError(f'reference contract needs measurements or absence evidence for {group}')


def check(manifest_path, contract=None):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text())
    problems, results = [], []
    groups = manifest.get('fields', {})
    if contract:
        validate_contract(contract)
        for key in ('levels', 'fields', 'cases', 'not_applicable'):
            if manifest.get(key, {} if key in ('fields', 'not_applicable') else []) != contract.get(key, {} if key in ('fields', 'not_applicable') else []):
                problems.append(f'{key} differs from pinned reference contract')
    fields = {}
    for group in GROUPS:
        if not groups.get(group) and manifest.get('not_applicable', {}).get(group):
            continue
        if not isinstance(groups.get(group), dict) or not groups[group]:
            problems.append(f'missing gameplay field group: {group}')
        else:
            fields.update(groups[group])
    for field, limit in fields.items():
        if not isinstance(limit, (int, float)) or not math.isfinite(limit) or not 0 <= limit <= 3:
            problems.append(f'invalid tolerance: {field}')
    if 'terminal' not in fields:
        problems.append('required field: terminal')
    if any(fields.get(k, 0) != 0 for k in ('lives', 'terminal', 'score')):
        problems.append('lives, terminal and score must match exactly')
    if problems:
        return {'complete': False, 'problems': problems, 'routes': []}
    tolerances = {k: {'near': v, 'far': v} for k, v in fields.items()}
    levels = manifest.get('levels', [])
    if not levels or len(set(levels)) != len(levels):
        problems.append('declare the requested levels without duplicates')
    if manifest.get('unresolved') != []:
        problems.append('unresolved differences or missing unresolved checklist')
    if manifest.get('randomness') != 'reproduced-from-reset':
        problems.append('randomness must be reproduced from reset; statistical-only validation is not an exact trajectory pass')
    routes = manifest.get('routes', [])
    for level in levels:
        for kind in manifest.get('cases', ('clear', 'heldout', 'death-recovery')):
            if not any(r.get('level') == level and r.get('kind') == kind for r in routes):
                problems.append(f'missing {kind} route for level {level}')
    references = set()
    for route in routes:
        ref, new, repeat = [path.parent / route[k] for k in ('reference', 'rebuild', 'repeat')]
        a, b, c = load(ref), load(new), load(repeat)
        digest = sha256(ref)
        if digest in references:
            problems.append('routes must use distinct reference traces')
        references.add(digest)
        if not a or sorted(a) != list(range(len(a))) or set(a) != set(b) or set(a) != set(c):
            problems.append(f'{ref.name}: traces must cover every frame from reset')
        for f in a:
            if 'buttons' not in a[f] or any(a[f].get('buttons') != trace.get(f, {}).get('buttons') for trace in (b, c)):
                problems.append(f'{ref.name}: input mismatch at frame {f}')
                break
        if route.get('kind') in ('clear', 'heldout') and (not a or a[max(a)].get('terminal') != 1):
            problems.append(f'{ref.name}: route does not reach the requested ending')
        if route.get('kind') == 'death-recovery':
            deaths = [f for f in sorted(a) if f > 0 and a[f].get('lives', 0) < a.get(f - 1, {}).get('lives', 0)]
            if not deaths or not any(f > deaths[0] and a[f].get('lives', 0) > 0 and
                                     (a[f].get('player_x'), a[f].get('player_y')) !=
                                     (a[deaths[0]].get('player_x'), a[deaths[0]].get('player_y')) for f in a):
                problems.append(f'{ref.name}: no measured death and recovery')
        result = compare(ref, new, tolerances)
        deterministic = compare(ref, repeat, {k: {'near': 0, 'far': 0} for k in fields})
        for label, report in (('rebuild', result), ('repeat', deterministic)):
            if any(report[k] for k in ('events', 'missing_in_rebuild', 'extra_in_rebuild', 'missing_fields', 'invalid_values')):
                problems.append(f'{ref.name}: {label} differs or lacks measurements')
        results.append({'reference': str(ref), 'reference_sha256': digest, 'rebuild_sha256': sha256(new),
                        'repeat_sha256': sha256(repeat), 'comparison': result, 'repeat': deterministic})
    if not routes:
        problems.append('no complete routes')
    return {'complete': not problems, 'problems': problems, 'routes': results,
            'limit': 'Checks supplied traces; independent review must confirm scope, measurement validity and rendered behaviour.'}


def delivery(manifest_path, contract=None):
    """Verify render parity and probe the delivered recordings, without trusting claimed durations."""
    import subprocess
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text())
    recreation_path = path.parent / manifest['recreation']
    report = check(recreation_path, contract)
    problems = report['problems']
    traces = [load(path.parent / manifest[k]) for k in ('simulation', 'render2d', 'render3d')]
    if not traces[0] or any(trace != traces[0] for trace in traces[1:]):
        problems.append('headless, 2D and 3D hash/audio traces differ or are empty')
    if sorted(traces[0]) != list(range(len(traces[0]))) or any(not r.get('state_hash') or not isinstance(r.get('audio_events'), list) for r in traces[0].values()):
        problems.append('render parity needs contiguous per-frame state hashes and audio events')
    recreation = json.loads(recreation_path.read_text())
    route_path = (path.parent / manifest['route_reference']).resolve()
    accepted = [r for r in recreation['routes'] if r['kind'] in ('clear', 'heldout') and
                (recreation_path.parent / r['reference']).resolve() == route_path]
    if not accepted:
        problems.append('parity must use a completed clear or heldout reference route')
        expected = {}
    else:
        expected = load(route_path)
    if set(traces[0]) != set(expected) or any('buttons' not in row or row['buttons'] != expected.get(f, {}).get('buttons')
                                             for f, row in traces[0].items()):
        problems.append('parity must cover the complete accepted route with identical inputs')
    if not traces[0] or traces[0][max(traces[0])].get('terminal') != 1:
        problems.append('parity route must reach its ending')
    for name in ('assets3d', 'build2d', 'build3d'):
        p = path.parent / manifest[name]
        if not p.is_file() or not p.stat().st_size:
            problems.append(f'missing artifact: {name}')
    for name in ('video2d', 'video3d'):
        p = path.parent / manifest[name]
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(p)],
                               capture_output=True, text=True, timeout=30)
        data = json.loads(probe.stdout or '{}')
        duration = float(data.get('format', {}).get('duration', 0))
        minimum = max(0, (len(expected) - 1) / 60.0988 - 0.5)
        if probe.returncode or not any(s.get('codec_type') == 'video' for s in data.get('streams', [])) or not math.isfinite(duration) or duration <= 0 or duration < minimum:
            problems.append(f'invalid video: {name}')
    return {**report, 'complete': not problems}


def training(manifest_path, contract):
    """Require repeated completed policy evaluations, not a search route relabelled as training."""
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text())
    checkpoint = path.parent / manifest['checkpoint']
    problems = []
    if not checkpoint.is_file() or not checkpoint.stat().st_size:
        problems.append('missing trained checkpoint')
    elif manifest.get('checkpoint_sha256') != sha256(checkpoint):
        problems.append('trained checkpoint hash mismatch')
    plays = manifest.get('plays', [])
    if len(plays) < 2:
        problems.append('need at least two completed trained-policy evaluations')
    for play in plays:
        rows = load(path.parent / play['trace'])
        if play.get('controller') != 'trained-policy' or not rows or sorted(rows) != list(range(len(rows))):
            problems.append('evaluation must be a contiguous trained-policy play from reset')
        if not rows or rows[max(rows)].get('terminal') != 1:
            problems.append('trained policy did not reach the requested ending')
        observed = {str(row['level']) for row in rows.values() if 'level' in row}
        if not set(map(str, contract['levels'])) <= observed:
            problems.append('trained policy did not visit every declared level/rule regime')
        if any(not isinstance(row.get('buttons'), list) for row in rows.values()):
            problems.append('evaluation is missing applied policy inputs')
    return {'complete': not problems, 'problems': problems, 'plays': len(plays)}


def verify_reference(manifest_path, contract, oracle_root):
    """Authenticate public reference/repeat traces against the private oracle's observations."""
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text())
    fields = sorted({k for group in contract['fields'].values() for k in group})
    keys = ['f', 'buttons', *fields]
    def canonical(row):
        return {k: row[k] for k in keys if k in row}
    episodes = []
    for log in Path(oracle_root).rglob('trace.jsonl'):
        episode = []
        for line in log.read_text().splitlines():
            row = json.loads(line)
            if row.get('f') == 0:
                if episode:
                    episodes.append(episode)
                episode = []
            episode.append(canonical(row))
        if episode:
            episodes.append(episode)
    problems = []
    for route in manifest.get('routes', []):
        matches = []
        for name in ('reference', 'repeat'):
            source = path.parent / route[name]
            rows = [canonical(r) for r in load(source).values()]
            candidates = [i for i, episode in enumerate(episodes) if rows == episode[:len(rows)]]
            matches.append(candidates)
            if not candidates:
                problems.append(f'{source.name}: not a recorded private oracle playthrough')
        if all(matches) and not any(a != b for a in matches[0] for b in matches[1]):
            problems.append('randomness verification needs two separately recorded reference runs')
    return problems
