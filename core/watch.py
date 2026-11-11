"""Training watcher: reads a run's metrics and test plays and says whether training is going the right way.

Costs no model tokens: it is plain arithmetic, so it can run often and only wake the agent on verdict 'act'.
Inputs are the trainer's own files: RUN/metrics.jsonl, RUN/eval/it*/summary.json and RUN/pid.
Each detector comes from a failure seen in real runs; see docs/TRAINING_WATCHER.md.
"""
from __future__ import annotations

import glob
import json
import math
import os
from pathlib import Path
import statistics as st

WINDOW = 100


def read_rows(run):
    path = Path(run) / 'metrics.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


def read_evals(run):
    out = []
    for path in sorted(glob.glob(str(Path(run) / 'eval' / 'it*' / 'summary.json'))):
        try:
            plays = json.loads(Path(path).read_text())
        except json.JSONDecodeError:   # still being written
            continue
        out.append({'it': int(Path(path).parent.name[2:]), 'plays': plays})
    return out


def alive(pid):
    """True if the process is running. A zombie has exited, though signal 0 still succeeds on it."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return True


def windows(values, size):
    return [st.mean(values[i:i + size]) for i in range(0, len(values) - size + 1, size)]


def finding(code, severity, evidence, next_step):
    return {'code': code, 'severity': severity, 'evidence': evidence, 'next_step': next_step}


def game_rows(rows):
    """{game: [(it, stats), ...]} for iterations in which episodes finished."""
    out = {}
    for r in rows:
        for name, g in (r.get('games') or {}).items():
            out.setdefault(name, []).append((r['it'], g))
    return out


def check_numbers(rows):
    bad = [r['it'] for r in rows[-WINDOW:] for k in ('pg', 'v', 'ent', 'kl', 'gnorm')
           if k in r and not math.isfinite(r[k])]
    return [finding('non_finite', 'act', f'NaN or Inf at iterations {sorted(set(bad))[:5]}',
                    'Stop the run and restart from the last good test play.')] if bad else []


def check_value_fit(rows):
    ev = windows([r['explained_var'] for r in rows if 'explained_var' in r], WINDOW)
    if len(ev) < 3 or max(ev[:-1]) < 0.9 or ev[-1] >= max(ev[:-1]) - 0.15:
        return []
    return [finding('value_fit_collapse', 'act', f'explained variance fell from {max(ev[:-1]):.2f} to {ev[-1]:.2f}',
                    'A sudden large reward is the usual cause. Replay recent episodes and look for one step that pays '
                    'far more than a level: a signed or wrapping RAM byte.')]


def check_levels(rows):
    found = []
    for name, series in game_rows(rows).items():
        means = windows([g['level_mean'] for _, g in series], WINDOW)
        if len(means) >= 3 and max(means[:-1]) >= 1 and means[-1] < 0.75 * max(means[:-1]):
            found.append(finding('level_regression', 'act',
                                 f'{name}: mean level reached fell from {max(means[:-1]):.2f} to {means[-1]:.2f}',
                                 'Compare frozen test plays from before and after the fall; find what changed.'))
    return found


def check_ends(rows):
    found, totals = [], {}
    for r in rows[-WINDOW:]:
        for name, g in (r.get('games') or {}).items():
            t = totals.setdefault(name, {})
            for end, n in g.get('ends', {}).items():
                t[end] = t.get(end, 0) + n
    for name, t in totals.items():
        n = sum(t.values())
        if t.get('fault'):
            found.append(finding('emulator_fault', 'act', f"{name}: {t['fault']} of {n} episodes faulted",
                                 'The environment is broken for this game. Check mapper support before anything else.'))
        if n >= 20 and t.get('stall', 0) / n > 0.5:
            found.append(finding('stall_dominates', 'act', f"{name}: {t['stall']} of {n} episodes ended by stalling",
                                 'Waiting is the best-paying play. Run the balance test and check the idle cost.'))
    return found


def median_level(ev):
    return st.median(p['level'] for p in ev['plays'])


def check_evals(evals):
    found = []
    for p in evals[-1]['plays'] if evals else []:
        parts = p.get('parts', {})
        if parts.get('progress', 0) > p.get('level', 0) + 2:
            found.append(finding('progress_overpaid', 'act',
                                 f"it{evals[-1]['it']} {p['game']}: progress paid {parts['progress']:.1f} by level "
                                 f"{p['level']}", 'Progress pays about 1 per level. Look for a jump in the reader.'))
            break
    if len(evals) >= 6:
        best = max(median_level(e) for e in evals[:-3])
        recent = st.median(median_level(e) for e in evals[-3:])
        if best >= 1 and recent <= best - 2:
            found.append(finding('test_play_regression', 'act',
                                 f'median level in test plays fell from {best:g} to {recent:g}',
                                 'Test plays are the measure that counts. Find the last good model in eval/.'))
    return found


def check_learning(rows, evals):
    found = []
    ent = [r['ent'] for r in rows if 'ent' in r]
    if len(ent) >= 2 * WINDOW:
        first, last = st.mean(ent[:WINDOW]), st.mean(ent[-WINDOW:])
        if last < 0.1 * first:
            found.append(finding('entropy_collapse', 'watch', f'entropy {first:.2f} -> {last:.2f}',
                                 'Check the actual button streams; the policy may be stuck holding one input.'))
    if len(evals) >= 8:
        half = len(evals) // 2
        if max(median_level(e) for e in evals[half:]) <= max(median_level(e) for e in evals[:half]):
            found.append(finding('no_test_play_gain', 'watch',
                                 f'no gain in test-play level across the last {len(evals) - half} evaluations',
                                 'Throughput and reward are not progress. Compare greedy and sampled play.'))
    sps = windows([r['sps'] for r in rows if 'sps' in r], WINDOW)
    if len(sps) >= 3 and sps[-1] < 0.6 * max(sps):
        found.append(finding('throughput_drop', 'watch', f'{max(sps):.0f} -> {sps[-1]:.0f} decisions/s',
                             'Look for another process sharing the CPU or GPU.'))
    return found


def check_process(run, rows, now):
    pid_file = Path(run) / 'pid'
    if not pid_file.exists() or (Path(run) / 'STOP').exists() or (Path(run) / 'CLEAN_EXIT').exists():
        return []
    pid = int(pid_file.read_text())
    if not alive(pid):
        return [finding('trainer_stopped', 'act', f'process {pid} is gone with no STOP file',
                        'Read the end of stdout.log, fix the cause, then resume from the last checkpoint.')]
    if rows and now - rows[-1].get('time', now) > 1800:
        return [finding('trainer_silent', 'act', f'process {pid} is alive but wrote no metrics for 30 minutes',
                        'The trainer may be hung. Inspect it before stopping it.')]
    return []


def check(run, now):
    rows, evals = read_rows(run), read_evals(run)
    found = (check_numbers(rows) + check_value_fit(rows) + check_levels(rows) + check_ends(rows) + check_evals(evals)
             + check_learning(rows, evals) + check_process(run, rows, now))
    verdict = 'act' if any(f['severity'] == 'act' for f in found) else 'watch' if found else 'healthy'
    return {'verdict': verdict, 'iteration': rows[-1]['it'] if rows else None,
            'decisions': rows[-1].get('decisions') if rows else None, 'test_plays': len(evals), 'findings': found}
