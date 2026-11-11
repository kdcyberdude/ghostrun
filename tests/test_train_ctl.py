import json

import pytest

import train_ctl as tc


def game(tmp_path, code='A = 1\n'):
    ref = tmp_path / 'g'
    (ref / 'games').mkdir(parents=True)
    (ref / 'games' / 'g.py').write_text(code)
    return ref, tc.Game(ref, 'g')


def test_fix_needs_a_change_and_budget(tmp_path):
    ref, g = game(tmp_path)
    tc.fix_begin(ref, 'g', 'value_fit_collapse', 'signed byte')
    with pytest.raises(tc.TrainError):
        tc.fix_begin(ref, 'g', 'x', 'y')
    with pytest.raises(tc.TrainError, match='unchanged'):
        tc.fix_validate(ref, 'g', 'python3', {}, 100.0)
    state = g.state
    state.update(pending_fix=None, fixes_used=tc.MAX_FIXES)
    g.save(state)
    with pytest.raises(tc.TrainError, match='budget'):
        tc.fix_begin(ref, 'g', 'x', 'y')


def test_apply_refuses_unvalidated_or_edited(tmp_path):
    ref, g = game(tmp_path)
    with pytest.raises(tc.TrainError, match='not validated'):
        tc.fix_apply(ref, 'g', 'python3')
    tc.fix_begin(ref, 'g', 'f', 'h')
    state = g.state
    state['pending_fix']['validated'] = tc.sha(g.module)
    g.save(state)
    g.module.write_text('A = 2\n')
    with pytest.raises(tc.TrainError, match='changed after validation'):
        tc.fix_apply(ref, 'g', 'python3')


def test_stop_refuses_unowned(tmp_path):
    ref, _ = game(tmp_path)
    with pytest.raises(tc.TrainError, match='no training process'):
        tc.stop(ref, 'g')


def test_start_refuses_busy_gpu(tmp_path, monkeypatch):
    ref, _ = game(tmp_path)
    monkeypatch.setattr(tc, 'gpu_other_users', lambda *_: [123])
    with pytest.raises(tc.TrainError, match='GPU is in use'):
        tc.start(ref, 'g', 'python3', [])


def test_changed_sampling_config_preserves_checkpoint_and_forks_without_reward_fix(tmp_path, monkeypatch):
    ref, g = game(tmp_path)
    run = g.run_dir(1)
    run.mkdir(parents=True)
    checkpoint = run / 'ckpt_rank0_latest.pt'
    checkpoint.write_bytes(b'preserved latest weights')
    state = g.state
    state.update(version=1, run=str(run), args=['--envs-per-game', '128'])
    g.save(state)
    monkeypatch.setattr(tc, 'gpu_other_users', lambda *_: [])
    launched = []
    def launch(game, state, python, args, restart_from=None):
        launched.append((state, args, restart_from))
        return {'version': state['version']}
    monkeypatch.setattr(tc, 'launch', launch)
    assert tc.start(ref, 'g', 'python3', state['args'])['version'] == 1
    assert launched[-1][2] is None
    assert tc.start(ref, 'g', 'python3', [*state['args'], '--time-limit=180', '--eval-threads', '2'])['version'] == 1
    assert launched[-1][2] is None
    result = tc.start(ref, 'g', 'python3', ['--envs-per-game', '8192'])
    fork = launched[-1][0]
    assert result['version'] == 2 and launched[-1][2] == checkpoint
    assert fork['fixes_used'] == 0 and fork['history'][0]['run'] == str(run)
    assert checkpoint.read_bytes() == b'preserved latest weights'
    assert (g.versions / 'v002' / 'g.py').exists()


def test_runtime_limits_do_not_reset_training_state():
    assert tc.state_args(['--time-limit', '120', '--steps', '64', '--eval-steps=6000']) == ['--steps', '64']
    assert tc.state_args(['--core', '256', '--log-every', '2']) != tc.state_args(['--core', '512'])


def write_eval(run, it, level, ret):
    d = run / 'eval' / f'it{it:06d}'
    d.mkdir(parents=True)
    (d / 'summary.json').write_text(json.dumps([{'game': 'g', 'level': level, 'ret': ret}]))
    (d / 'model.pt').write_bytes(b'x')


def test_best_model_and_review(tmp_path):
    ref, g = game(tmp_path)
    old, new = g.run_dir(1), g.run_dir(2)
    for it, level in ((1, 2), (2, 6), (3, 3)):
        write_eval(old, it, level, float(level))
    model, key = tc.best_model(old)
    assert model.parent.name == 'it000002' and key == (6, 6.0)
    state = g.state
    state.update(run=str(new), history=[{'best': key}])
    g.save(state)
    new.mkdir(parents=True)
    assert tc.fix_review(ref, 'g')['verdict'] == 'wait'
    for it in (1, 2, 3):
        write_eval(new, it, 4, 4.0)
    assert tc.fix_review(ref, 'g')['verdict'] == 'worse'


FAKE_TRAINER = '''
import os, sys, time
from pathlib import Path
args = sys.argv[1:]
run = Path(args[args.index('--run') + 1])
(run / 'argv.txt').write_text(' '.join(args))
while not (run / 'STOP').exists():
    time.sleep(0.05)
'''


def test_start_stop_apply_with_a_real_process(tmp_path, monkeypatch):
    import sys
    ref, g = game(tmp_path)
    monkeypatch.setattr(tc, 'gpu_other_users', lambda *_: [])
    (g.engine / 'rl').mkdir(parents=True)
    (g.engine / 'rl' / 'train.py').write_text(FAKE_TRAINER)
    started = tc.start(ref, 'g', sys.executable, ['--steps', '16'])
    assert started['version'] == 1 and tc.watch.alive(started['pid'])
    with pytest.raises(tc.TrainError, match='already running'):
        tc.start(ref, 'g', sys.executable, [])
    write_eval(g.run_dir(1), 7, 5, 9.0)
    tc.fix_begin(ref, 'g', 'value_fit_collapse', 'signed byte')
    g.module.write_text('A = 2\n')
    state = g.state
    state['pending_fix']['validated'] = tc.sha(g.module)
    g.save(state)
    applied = tc.fix_apply(ref, 'g', sys.executable)
    assert applied['version'] == 2 and applied['restarted_from'].endswith('it000007/model.pt')
    assert not tc.watch.alive(started['pid']) or (g.run_dir(1) / 'STOP').exists()
    assert (g.versions / 'v002' / 'g.py').read_text() == 'A = 2\n'
    state = g.state
    assert state['fixes_used'] == 1 and state['pending_fix'] is None and state['history'][0]['best'] == [5, 9.0] or state['history'][0]['best'] == (5, 9.0)
    argv_file = g.run_dir(2) / 'argv.txt'
    for _ in range(100):
        if argv_file.exists():
            break
        tc.time.sleep(0.05)
    assert '--restart-from' in argv_file.read_text() and '--steps 16' in argv_file.read_text()
    tc.stop(ref, 'g')
    assert g.state['pid'] is None
    resumed = tc.start(ref, 'g', sys.executable, g.state['args'])
    tc.time.sleep(0.2)
    assert resumed['version'] == 2 and tc.watch.alive(resumed['pid'])
    tc.stop(ref, 'g')


def test_equal_level_after_reward_change_is_not_proof_of_learning(tmp_path):
    ref, g = game(tmp_path)
    run = g.run_dir(2)
    state = g.state
    state.update(run=str(run), history=[{'best': [0, -0.8]}])
    g.save(state)
    for it in (1, 2, 3):
        write_eval(run, it, 0, 1000.0)
    assert tc.fix_review(ref, 'g')['verdict'] == 'inconclusive'
