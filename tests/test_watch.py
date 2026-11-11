import json

import watch


def run_dir(tmp_path, rows, evals=()):
    (tmp_path / 'metrics.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    for it, plays in evals:
        d = tmp_path / 'eval' / f'it{it:06d}'
        d.mkdir(parents=True)
        (d / 'summary.json').write_text(json.dumps(plays))
    return tmp_path


def row(it, ev=0.97, level=4.0, ends=None):
    return {'it': it, 'time': 1000.0, 'decisions': it, 'pg': 0.0, 'v': 1.0, 'ent': 3.6, 'kl': 0.01, 'gnorm': 1.0,
            'explained_var': ev, 'sps': 9000.0,
            'games': {'g': {'n': 2, 'ret': 5.0, 'level_max': 5, 'level_mean': level, 'ends': ends or {'game_over': 2}}}}


def codes(report):
    return {f['code'] for f in report['findings']}


def test_healthy(tmp_path):
    report = watch.check(run_dir(tmp_path, [row(i) for i in range(400)]), 1000.0)
    assert report['verdict'] == 'healthy' and not report['findings']


def test_value_collapse_and_level_regression(tmp_path):
    rows = [row(i) for i in range(300)] + [row(i, ev=0.7, level=2.5) for i in range(300, 400)]
    report = watch.check(run_dir(tmp_path, rows), 1000.0)
    assert report['verdict'] == 'act' and {'value_fit_collapse', 'level_regression'} <= codes(report)


def test_stall_and_fault(tmp_path):
    rows = [row(i, ends={'stall': 2, 'fault': 1}) for i in range(100)]
    assert {'stall_dominates', 'emulator_fault'} <= codes(watch.check(run_dir(tmp_path, rows), 1000.0))


def test_non_finite(tmp_path):
    rows = [row(i) for i in range(10)]
    rows[-1]['kl'] = float('nan')
    assert 'non_finite' in codes(watch.check(run_dir(tmp_path, rows), 1000.0))


def test_overpaid_progress(tmp_path):
    play = {'game': 'g', 'level': 3, 'parts': {'progress': 24.5}}
    assert 'progress_overpaid' in codes(watch.check(run_dir(tmp_path, [row(0)], [(1, [play])]), 1000.0))


def test_dead_process(tmp_path):
    d = run_dir(tmp_path, [row(0)])
    (d / 'pid').write_text('999999999')
    assert 'trainer_stopped' in codes(watch.check(d, 1000.0))
    (d / 'STOP').write_text('')
    assert 'trainer_stopped' not in codes(watch.check(d, 1000.0))


def test_zombie_is_not_alive():
    import subprocess
    import sys
    import time
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    for _ in range(100):
        if not watch.alive(p.pid):
            break
        time.sleep(0.05)
    assert not watch.alive(p.pid)
    p.wait()
