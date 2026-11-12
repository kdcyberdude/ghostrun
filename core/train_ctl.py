"""Training control: per-game engine copy, owned trainer processes, and the reward-fix loop.

A run belongs to the plugin only if train.json names it. Nothing here touches a process it did not start.
Each reward version gets its own run folder, so its metrics and test plays are never mixed with an older reward's.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import statistics as st
import subprocess
import sys
import time

import reward_lint
import training_policy as policy
import watch
from ghostrun_security import child_env, validate_slug

CORE = Path(__file__).resolve().parent
ENGINE = CORE.parent / 'engine'
NESLE_URL = 'https://github.com/hbofz/NeSLE.git'
NESLE_BASE = '0b04d8b9b6a93eea6758b06519206d8f13f6db78'
MAX_FIXES = 3
MIN_REVIEW_PLAYS = 3
GPU_BUSY_MIB = 1024


class TrainError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def write_json(path, value):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, indent=1))
    os.replace(tmp, path)


class Game:
    """Paths and state of one game on the reference side."""

    def __init__(self, ref, slug):
        self.ref, self.slug = Path(ref), validate_slug(slug)
        self.module = self.ref / 'games' / f'{slug}.py'
        self.engine = self.ref / 'engine'
        self.nesle = self.ref.parent / '_shared' / 'nesle'
        self.state_path = self.ref / 'train.json'
        self.versions = self.ref / 'reward_versions'

    @property
    def state(self):
        return read_json(self.state_path, {'version': 0, 'fixes_used': 0, 'pid': None, 'run': None, 'args': [],
                                           'pending_fix': None, 'history': []})

    def save(self, state):
        write_json(self.state_path, state)

    def run_dir(self, version):
        return self.ref / 'runs' / f'v{version:03d}'

    def env(self):
        inherited = child_env()
        return {**inherited, 'NESLE_INC': str(self.nesle / 'cpp' / 'include'),
                'NESLE_ROM_CPP': str(self.nesle / 'cpp' / 'src' / 'rom.cpp'), 'RL_ROM_DIR': str(self.ref / 'rom'),
                'NES_ROM_DIR': str(self.ref / 'rom'), 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'}


def setup_nesle(game):
    """Fetch the upstream emulator at its pinned commit into plugin data and apply the local mapper and renderer patch."""
    if (game.nesle / '.patched').exists():
        return 'already set up'
    game.nesle.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(game.nesle, ignore_errors=True)
    subprocess.run(['git', 'clone', '-q', NESLE_URL, str(game.nesle)], check=True, env=child_env())
    subprocess.run(['git', '-C', str(game.nesle), 'checkout', '-q', NESLE_BASE], check=True, env=child_env())
    subprocess.run(['git', '-C', str(game.nesle), 'apply', str(ENGINE / 'third_party' / 'nesle-extensions.patch')],
                   check=True, env=child_env())
    (game.nesle / '.patched').write_text(NESLE_BASE)
    return f'NeSLE {NESLE_BASE[:8]} with extensions'


def build_host(game):
    """CPU build of the emulator, used to record each game's boot inputs before GPU training."""
    out = game.engine / '.cache' / 'nesle-check' / 'libnesle_host.so'
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    src = game.engine / 'scripts' / 'nesle_check' / 'nesle_capi.cpp'
    subprocess.run(['c++', '-O2', '-std=c++20', '-shared', '-fPIC', f"-I{game.nesle / 'cpp' / 'include'}", str(src),
                    str(game.nesle / 'cpp' / 'src' / 'rom.cpp'), '-o', str(out)], check=True, env=child_env())


def register_game(game, boot_frames):
    """Add this game to the per-game engine copy: module, ROM link, manifest entry and the generated game list."""
    games = game.engine / 'scripts' / 'reward10' / 'games'
    shutil.copyfile(game.module, games / f'{game.slug}.py')
    rom_dir = game.ref / 'rom'
    rom_dir.mkdir(exist_ok=True)
    rom_name = 'game.nes'
    shutil.copyfile(game.ref / 'game.nes', rom_dir / rom_name)
    manifest_path = game.engine / 'rl' / 'games_manifest.json'
    manifest = read_json(manifest_path)
    manifest[game.slug] = {'rom': rom_name, 'sha256': sha(rom_dir / rom_name), 'boot_frames': boot_frames}
    write_json(manifest_path, manifest)
    gen = game.engine / 'rl' / 'scripts' / 'gen_reward_consts.py'
    text = gen.read_text()
    if f"'{game.slug}'" not in text:
        gen.write_text(text.replace("'finalmission', 'punchout']", f"'finalmission', 'punchout', '{game.slug}']", 1))


def engine_setup(ref, slug, boot_frames):
    game = Game(ref, slug)
    note = setup_nesle(game)
    if not game.engine.exists():
        shutil.copytree(ENGINE, game.engine)
    build_host(game)
    register_game(game, boot_frames)
    return {'engine': str(game.engine), 'nesle': note,
            'next': 'Port the reader into rl/csrc/reward10.cuh (skill gpu-env-port), then run train-parity.'}


def parity(ref, slug, python):
    """The CUDA port must equal the Python reader: regenerate constants, then replay recorded RAM through both."""
    game = Game(ref, slug)
    env = {**game.env(), 'RL_PARITY_GAMES': slug}
    traces = game.engine / '.cache' / 'nesle-check' / 'traces'
    traces.mkdir(parents=True, exist_ok=True)
    record = {**env, 'PYTHONPATH': str(game.engine / 'scripts' / 'reward10')}
    p = subprocess.run([python, str(CORE / 'record_ram.py'), slug, str(traces / f'{slug}.ram.bin')], cwd=game.engine, env=record,
                       capture_output=True, text=True)
    if p.returncode:
        return {'parity': False, 'command': 'record_ram.py', 'output': (p.stdout + p.stderr)[-4000:]}
    steps = [[python, 'rl/scripts/gen_reward_consts.py'], [python, '-m', 'pytest', '-q', 'rl/tests/test_reward_replay.py']]
    for cmd in steps:
        p = subprocess.run(cmd, cwd=game.engine, env=env, capture_output=True, text=True)
        if p.returncode:
            return {'parity': False, 'command': ' '.join(cmd[1:]), 'output': (p.stdout + p.stderr)[-4000:]}
    return {'parity': True}


def gpu_other_users(own_pid=None):
    """Processes on the GPU using real memory. One owner at a time: a shared GPU slows both and confuses measurements."""
    try:
        out = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, check=True, env=child_env()).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    rows = [line.split(', ') for line in out.strip().splitlines() if line.strip()]
    return [int(p) for p, mib in rows if mib.strip().isdigit() and int(mib) >= GPU_BUSY_MIB and int(p) != own_pid]


def launch(game, state, python, args, restart_from=None, training_policy=None):
    run = game.run_dir(state['version'])
    run.mkdir(parents=True, exist_ok=True)
    (run / 'STOP').unlink(missing_ok=True)
    if training_policy is not None:
        write_json(run / 'training-policy.json', training_policy)
        state['training_policy'] = training_policy
    argv = [python, 'rl/train.py', '--run', str(run), '--games', game.slug, *args]
    if restart_from:
        argv += ['--restart-from', str(restart_from)]
    log = open(run / 'stdout.log', 'a')
    p = subprocess.Popen(argv, cwd=game.engine, env=game.env(), stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    (run / 'pid').write_text(str(p.pid))
    state.update(pid=p.pid, run=str(run), args=list(args))
    game.save(state)
    return {'pid': p.pid, 'run': str(run), 'version': state['version'], 'training_policy': training_policy}


def state_args(args):
    """Runtime limits and reporting do not change checkpoint compatibility."""
    runtime = {'--time-limit', '--total-iters', '--ckpt-minutes', '--ckpt-iters', '--eval-every-minutes',
               '--eval-steps', '--eval-threads', '--log-every'}
    result, tokens = [], iter(args)
    for arg in tokens:
        if arg.split('=', 1)[0] in runtime:
            if '=' not in arg:
                next(tokens, None)
        else:
            result.append(arg)
    return result


def start(ref, slug, python, args, share_gpu=False, smoke=False, adjustment_evidence=None, recipe_note=None):
    game = Game(ref, slug)
    state = game.state
    if state['pid'] and watch.alive(state['pid']):
        raise TrainError(f"training already running as process {state['pid']}")
    previous = state.get('training_policy')
    if not args and previous and (previous['phase'] == 'smoke') == smoke:
        args = previous.get('requested_args', state['args'])
    settings, changed = policy.parse(args, smoke)
    on_cpu = settings['device'] == 'cpu'
    others = [] if on_cpu else gpu_other_users()
    if others and not share_gpu:
        raise TrainError(f'the GPU is in use by process(es) {others}; refusing to share it')
    if not adjustment_evidence and previous and previous.get('adjustment_evidence'):
        adjustment_evidence = previous['adjustment_evidence']['run']
    if recipe_note is None and previous and all(previous['settings'][k] == settings[k] for k in policy.BASELINE['settings']):
        recipe_note = previous.get('recipe_note')
    plan = policy.plan(game, settings, changed, smoke, adjustment_evidence, recipe_note)
    plan['requested_args'] = policy.argv(settings)
    failed_preflight = None
    try:
        measured = None if smoke or not state['run'] else policy.throughput(state['run'], previous, plan)
    except policy.PolicyError as exc:
        failed_preflight, measured = str(exc), None
    if measured:
        plan.update(phase='production', throughput=measured)
    else:
        plan['settings'] = policy.bounded(settings)
    args = policy.argv(plan['settings'])
    restart_from = None
    reason = None
    if state['version'] == 0:
        state['version'] = 1
        snapshot(game, 1, {'reason': 'first reward'})
    elif state['run'] and (failed_preflight or not previous or (previous['phase'] == 'smoke') != smoke or
                           any(previous.get(k) != plan.get(k) for k in ('baseline_sha256', 'hardware', 'model_sha256')) or
                           state_args(args) != state_args(state['args'])):
        checkpoint = Path(state['run']) / 'ckpt_rank0_latest.pt'
        same_model = previous and previous['phase'] != 'smoke' and previous.get('model_sha256') == plan['model_sha256'] and all(
            previous['settings'][k] == settings[k] for k in ('core', 'moods'))
        if same_model and not failed_preflight:
            restart_from = checkpoint if checkpoint.exists() else previous.get('restart_from')
        model, key = best_model(state['run'])
        reason = {'reason': failed_preflight or ('training configuration changed' if same_model else 'start selected recipe; preserve incompatible/unverified old run'),
                  'previous_args': state['args'], 'args': list(args)}
        state['history'].append({'version': state['version'], 'run': state['run'],
                                 'best_model': str(model) if model else None, 'best': key, **reason})
        state['version'] += 1
        snapshot(game, state['version'], reason)
    elif previous and previous.get('restart_from') and not (Path(state['run']) / 'ckpt_rank0_latest.pt').exists():
        restart_from = previous['restart_from']
    if restart_from and not Path(restart_from).is_file():
        raise TrainError('the recorded restart checkpoint is missing; existing results were preserved')
    plan['restart_from'] = str(restart_from) if restart_from else None
    if not reason and previous and not restart_from:
        plan['restart_from'] = previous.get('restart_from')
    result = launch(game, state, python, args, restart_from=restart_from, training_policy=plan)
    return {**result, 'restarted_from': str(restart_from) if restart_from else None,
            'reason': reason['reason'] if reason else None,
            'next': 'Short diagnostic only; never use this configuration for production.' if smoke else
                    'Measured preflight accepted; monitor learning.' if measured else
                    'Wait for the bounded preflight, inspect throughput, then use requested_args with --time-limit reduced to the remaining user budget; do not copy internal bounds.'}


def stop(ref, slug, timeout=1200):
    """Graceful stop: the trainer sees STOP, writes a checkpoint and exits."""
    game = Game(ref, slug)
    state = game.state
    if not state['pid']:
        raise TrainError('no training process is owned by this plugin for this game')
    if watch.alive(state['pid']):
        (Path(state['run']) / 'STOP').write_text('')
        deadline = time.time() + timeout
        while watch.alive(state['pid']) and time.time() < deadline:
            time.sleep(5)
        if watch.alive(state['pid']):
            raise TrainError(f"process {state['pid']} did not stop within {timeout} s; it was left running")
    state['pid'] = None
    game.save(state)
    return {'stopped': True, 'run': state['run']}


def check(ref, slug):
    game = Game(ref, slug)
    state = game.state
    if not state['run']:
        raise TrainError('no run yet')
    report = watch.check(state['run'], time.time())
    report.update(version=state['version'], fixes_used=state['fixes_used'], fix_budget=MAX_FIXES,
                  pending_fix=state['pending_fix'])
    plan = state.get('training_policy')
    if plan:
        report['training_phase'] = plan['phase']
        report['training_recipe'] = plan['recipe']
        report['recipe_notice'] = plan['notice']
        report['recipe_note'] = plan['recipe_note']
        report['requested_args'] = plan.get('requested_args', state['args'])
    if plan and plan['phase'] == 'preflight' and (Path(state['run']) / 'CLEAN_EXIT').exists():
        gpu = None if plan['settings']['device'] == 'cpu' else policy.hardware()
        try:
            measured = policy.throughput(state['run'], plan, {**plan, 'hardware': gpu})
            problem = None
        except policy.PolicyError as exc:
            measured, problem = None, str(exc)
        report['throughput'] = measured
        code = 'preflight_failed' if problem else 'preflight_ready' if measured else 'preflight_incomplete'
        report['findings'].append(watch.finding(code, 'act',
            problem or ('Selected-recipe preflight finished; measured throughput is available.' if measured else 'Preflight ended before three valid measurements.'),
            'Call train-start using requested_args with --time-limit reduced to the remaining user budget; reward discovery is separate.' if measured else
            'Inspect the owned preflight logs and runtime budget before retrying; do not launch a long run.'))
        report['verdict'] = 'act'
    folder = game.ref / 'evidence' / 'watch'
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"v{state['version']:03d}.jsonl", 'a') as f:
        f.write(json.dumps({'time': time.time(), **report}) + '\n')
    return report


def snapshot(game, version, reason):
    folder = game.versions / f'v{version:03d}'
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(game.module, folder / f'{game.slug}.py')
    cuda = game.engine / 'rl' / 'csrc' / 'reward10.cuh'
    if cuda.exists():
        shutil.copyfile(cuda, folder / 'reward10.cuh')
    write_json(folder / 'reason.json', reason)


def fix_begin(ref, slug, finding, hypothesis):
    """Open a fix. The budget stops an endless patch loop: past it, the problem goes to the human."""
    game = Game(ref, slug)
    state = game.state
    if state['pending_fix']:
        raise TrainError('a fix is already open; validate and apply it, or cancel it')
    if state['fixes_used'] >= MAX_FIXES:
        raise TrainError(f'the fix budget of {MAX_FIXES} is used up; report to the user instead of patching again')
    state['pending_fix'] = {'finding': finding, 'hypothesis': hypothesis, 'base_sha': sha(game.module), 'validated': None}
    game.save(state)
    return {'open': True, 'edit': str(game.module), 'then': 'edit the reader and its CUDA port, then fix-validate'}


def fix_validate(ref, slug, python, reward_env, progress_unit):
    """Every check must pass on the edited reader. The result is tied to the file's hash."""
    game = Game(ref, slug)
    state = game.state
    fix = state['pending_fix']
    if not fix:
        raise TrainError('no open fix')
    if sha(game.module) == fix['base_sha']:
        raise TrainError('the reader is unchanged')
    engine_module = game.engine / 'scripts' / 'reward10' / 'games' / f'{slug}.py'
    shutil.copyfile(game.module, engine_module)
    reward = CORE.parent / 'engine' / 'scripts' / 'reward10'
    audit_dir = game.ref / 'evidence' / f"audit-fix-{state['fixes_used'] + 1}"
    results = {}
    for name, argv in (('contract', [str(reward / 'contract.py')]),
                       ('audit', [str(reward / 'audit.py'), slug, 'random', '--episodes', '12', '--steps', '3000',
                                  '--out', str(audit_dir)]),
                       ('balance', [str(CORE / 'balance.py'), slug])):
        p = subprocess.run([python, *argv], env=reward_env, cwd=game.ref, capture_output=True, text=True)
        results[name] = {'ok': p.returncode == 0, 'output': (p.stdout + p.stderr)[-1500:]}
        if name == 'balance' and p.returncode == 0:
            problem = json.loads(p.stdout)['problem']
            results[name] = {'ok': problem is None, 'problem': problem}
    problems = reward_lint.lint_dir(audit_dir, progress_unit) if audit_dir.exists() else ['no audit output']
    results['lint'] = {'ok': not problems, 'problems': problems[:20]}
    results['parity'] = parity(ref, slug, python)
    results['parity']['ok'] = results['parity']['parity']
    passed = all(r['ok'] for r in results.values())
    fix['validated'] = sha(game.module) if passed else None
    game.save(state)
    return {'passed': passed, 'checks': results, 'contact_sheets': str(audit_dir),
            'reminder': 'Look at the contact sheets too: numbers cannot confirm that an event matches the screen.'}


def best_model(run):
    """The frozen test-play model with the highest median level, then median return."""
    best, key = None, None
    for ev in watch.read_evals(run):
        model = Path(run) / 'eval' / f"it{ev['it']:06d}" / 'model.pt'
        if not model.exists():
            continue
        k = (watch.median_level(ev), st.median(p['ret'] for p in ev['plays']))
        if key is None or k > key:
            best, key = model, k
    return best, key


def fix_apply(ref, slug, python):
    """Stop, keep the old run, and start a new run on the fixed reward from the best measured weights."""
    game = Game(ref, slug)
    state = game.state
    fix = state['pending_fix']
    if not fix or not fix['validated'] or fix['validated'] != sha(game.module):
        raise TrainError('the fix is not validated, or the reader changed after validation')
    prior = state.get('training_policy')
    if not prior:
        raise TrainError('legacy training has no recorded recipe; select and measure it with train-start before applying a reward fix')
    smoke = prior['phase'] == 'smoke'
    settings, changed = policy.parse(prior.get('requested_args', state['args']), smoke)
    source = (prior.get('adjustment_evidence') or {}).get('run')
    plan = policy.plan(game, settings, changed, smoke, source, prior.get('recipe_note'))
    plan['requested_args'] = policy.argv(settings)
    plan['settings'] = policy.bounded(settings)
    if settings['device'] != 'cpu' and gpu_other_users(state['pid']):
        raise TrainError('the GPU is in use by another process; existing owned run was left unchanged')
    if state['pid']:
        stop(ref, slug)
        state = game.state
    old_run = state['run']
    model, key = best_model(old_run)
    latest = Path(old_run) / 'ckpt_rank0_latest.pt'
    if model is None and latest.exists():
        model = latest
    plan['restart_from'] = str(model) if model else None
    state['history'].append({'version': state['version'], 'run': old_run, 'best_model': str(model) if model else None,
                             'best': key, 'fix': fix})
    state['version'] += 1
    state['fixes_used'] += 1
    state['pending_fix'] = None
    snapshot(game, state['version'], fix)
    return {**launch(game, state, python, policy.argv(plan['settings']), restart_from=model, training_policy=plan), 'restarted_from': str(model) if model else None,
            'review': f'After {MIN_REVIEW_PLAYS} test plays, run fix-review.'}


def fix_review(ref, slug):
    """Judge a fix by test plays only. Reward and throughput cannot show that behaviour improved."""
    game = Game(ref, slug)
    state = game.state
    if not state['history']:
        raise TrainError('no applied fix to review')
    evals = watch.read_evals(state['run'])
    if len(evals) < MIN_REVIEW_PLAYS:
        return {'verdict': 'wait', 'test_plays': len(evals), 'needed': MIN_REVIEW_PLAYS}
    before = state['history'][-1]['best']
    now = st.median(watch.median_level(e) for e in evals[-MIN_REVIEW_PLAYS:])
    if before is None:
        return {'verdict': 'no_baseline', 'now': now}
    return {'verdict': 'worse' if now < before[0] else 'kept' if now > before[0] else 'inconclusive',
            'level_before': before[0], 'level_now': now,
            'if_inconclusive': 'No measured level gain: compare raw task progress and frozen-policy behaviour; reward totals under changed rewards are not comparable.',
            'if_worse': 'Restore the previous reward from reward_versions and report it; do not tune further.'}


if __name__ == '__main__':
    sys.exit('use core/cli.py')
