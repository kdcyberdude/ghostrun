"""Stage runner. Every plugin tool is a thin call to one of these commands, and each prints one JSON object.

Layout (the two roots must not overlap):
  <reference_root>/<slug>/  game.nes, games/<slug>.py, evidence/, state.json   private to the reference side
  <builder_root>/<slug>/    the independent game, tools/oracle_client.py       has no route to the reference except the socket
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

CORE = Path(__file__).resolve().parent
REWARD10 = CORE.parent / 'engine' / 'scripts' / 'reward10'
sys.path[:0] = [str(CORE), str(REWARD10)]

import compare as compare_mod  # noqa: E402
import gate as gate_mod  # noqa: E402
import completion  # noqa: E402
import visual_check  # noqa: E402
from prepared_assets import validate_assets  # noqa: E402
import isolation  # noqa: E402
from ledger import Ledger, LedgerError, check_rights  # noqa: E402
import train_ctl  # noqa: E402


def ref_dir(a):
    return Path(a.reference_root).expanduser() / a.slug


def builder_dir(a):
    return Path(a.builder_root).expanduser() / a.slug


def ledger(a):
    return Ledger(ref_dir(a) / 'state.json')


def socket_path(a):
    """Short and outside both roots: Unix socket paths are limited to about 100 characters."""
    pin = ref_dir(a) / 'oracle-endpoint.json'
    if pin.exists():
        return Path(json.loads(pin.read_text())['socket'])
    key = hashlib.sha256(str(ref_dir(a).resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f'oracle-{key}.sock'


def publish_socket(a, mode):
    info = {'socket': str(socket_path(a)), 'mode': mode}
    (ref_dir(a) / 'oracle-endpoint.json').write_text(json.dumps(info))
    (builder_dir(a) / '.oracle.json').write_text(json.dumps(info))


def cmd_init(a):
    if ledger(a).path.exists():
        raise LedgerError('game already initialized; use ghostrun_status to resume or choose a new slug')
    if not isolation.paths_are_separate(a.reference_root, a.builder_root):
        raise LedgerError('reference and builder folders must not overlap')
    rights = json.loads(a.rights) if a.rights else None
    check_rights(a.mode, rights)
    ref, build = ref_dir(a), builder_dir(a)
    (ref / 'games').mkdir(parents=True, exist_ok=True)
    (ref / 'evidence').mkdir(exist_ok=True)
    (build / 'tools').mkdir(parents=True, exist_ok=True)
    rom = Path(a.rom).expanduser().resolve(strict=True)
    shutil.copyfile(rom, ref / 'game.nes')
    (ref / 'game.nes').chmod(0o600)
    module = ref / 'games' / f'{a.slug}.py'
    digest = hashlib.sha256(rom.read_bytes()).hexdigest()
    if not module.exists():
        module.write_text((CORE / 'templates' / 'game_module.py').read_text().replace('<sha256>', digest))
    shutil.copyfile(CORE / 'oracle_client.py', build / 'tools' / 'oracle_client.py')
    publish_socket(a, a.mode)
    led = ledger(a)
    led.create(a.slug, a.mode, rights)
    led.set('intake', 'passed', f'rom sha256 {digest}')
    return {'slug': a.slug, 'mode': a.mode, 'rom_sha256': digest, 'module': str(module), 'builder': str(build),
            'read_first': [str(CORE.parent / 'docs' / 'RECREATION.md'), str(REWARD10 / 'README.md'), str(module)],
            'next': led.next_stage()}


def cmd_status(a):
    led = ledger(a)
    if not led.path.exists():
        root = Path(a.reference_root).expanduser()
        games = sorted(p.parent.name for p in root.glob('*/state.json')) if root.is_dir() else []
        return {'error': f"No game '{a.slug}' yet. Start one with ghostrun_init.", 'games': games}
    return {**led.read(), 'next': led.next_stage()}


def cmd_set(a):
    if a.status == 'passed' and a.stage == 'verify' and ledger(a).read()['mode'] == 'recreate':
        contract = json.loads(Path(a.evidence).read_text())
        completion.validate_contract(contract)
        state = ledger(a).read()
        if state['stages']['reward']['status'] != 'passed':
            raise LedgerError('verify cannot pass before reward verification passes')
        if state.get('contract') and state['contract'] != contract:
            old = state['contract']
            if not set(old['levels']) <= set(contract['levels']) or not set(old['cases']) <= set(contract['cases']) or any(
                    k not in contract['fields'].get(group, {}) or contract['fields'][group][k] > limit
                    for group, fields in old['fields'].items() for k, limit in fields.items()):
                raise LedgerError('reference contract is pinned; do not shrink scope or loosen tolerances')
            state.setdefault('contract_history', []).append({'contract': old, 'stages': state['stages']})
            state['stages'] = {s: (dict(status='pending', evidence=None) if s in ('explore', 'oracle', 'assets', 'build', 'compare', 'gate', 'visual3d') else result)
                               for s, result in state['stages'].items()}
        state['contract'] = contract
        ledger(a)._write(state)
    if a.status == 'passed' and a.stage == 'explore' and ledger(a).read()['mode'] == 'recreate':
        report = completion.training(a.evidence, ledger(a).read()['contract'])
        if not report['complete']:
            raise LedgerError('policy training incomplete: ' + '; '.join(report['problems']))
    if a.status == 'passed' and a.stage == 'assets':
        validate_assets(builder_dir(a) / 'assets')
    if a.status in ('passed', 'skipped') and ledger(a).read()['mode'] == 'recreate' and a.stage in ('gate', 'visual3d'):
        contract = ledger(a).read().get('contract')
        if not contract:
            raise LedgerError('verify must pin the full-game reference contract first')
        report = completion.delivery(a.evidence, contract, three_d=a.status != 'skipped') if a.stage == 'visual3d' else completion.check(a.evidence, contract)
        recreation = Path(a.evidence)
        if a.stage == 'visual3d':
            recreation = recreation.parent / json.loads(recreation.read_text())['recreation']
        report['problems'].extend(completion.verify_reference(recreation, contract, ref_dir(a) / 'evidence' / 'oracle'))
        report['problems'].extend(visual_check.check(recreation, ref_dir(a) / 'evidence' / 'oracle'))
        report['complete'] = not report['problems']
        if not report['complete']:
            raise LedgerError('recreation incomplete: ' + '; '.join(report['problems']))
    state = ledger(a).set(a.stage, a.status, a.evidence, a.note)
    return {'stage': a.stage, **state['stages'][a.stage]}


def reward_env(a):
    return {**os.environ, 'REWARD10_GAMES_ROOT': str(ref_dir(a)),
            'PYTHONPATH': os.pathsep.join([str(ref_dir(a)), str(REWARD10)])}


def run_reward_tool(a, argv):
    p = subprocess.run([a.python, *argv], env=reward_env(a), cwd=ref_dir(a), capture_output=True, text=True)
    return {'exit_code': p.returncode, 'stdout': p.stdout[-6000:], 'stderr': p.stderr[-3000:]}


def cmd_reward_check(a):
    return run_reward_tool(a, [str(REWARD10 / 'contract.py')])


def cmd_audit(a):
    out = ref_dir(a) / 'evidence' / 'audit'
    res = run_reward_tool(a, [str(REWARD10 / 'audit.py'), a.slug, 'random', '--episodes', str(a.episodes),
                              '--steps', str(a.steps), '--out', str(out)])
    return {**res, 'evidence': str(out)}


def cmd_search(a):
    out = ref_dir(a) / 'evidence' / 'search'
    res = run_reward_tool(a, [str(REWARD10 / 'search.py'), a.slug, '--seconds', str(a.seconds), '--workers',
                              str(a.workers), '--out', str(out)])
    return {**res, 'evidence': str(out)}


def route_decisions(game, result_path):
    """Use recorded policy inputs directly, or expand a legacy search route."""
    from oracle import BUTTONS, MAX_FRAMES
    route = json.loads(Path(result_path).read_text())
    decisions = []
    if 'decisions' in route:
        decisions = [(row['buttons'], row['frames']) for row in route['decisions']]
    else:
        for i in route['acts']:
            if type(i) is not int or not 0 <= i < len(game.ACTIONS):
                raise LedgerError('route action index is outside the game action set')
            act = game.ACTIONS[i]
            decisions += [(list(b), f) for b, f in act] if isinstance(act, list) else [(list(act), 8)]
    for buttons, frames in decisions:
        if not isinstance(buttons, list) or not all(isinstance(b, str) and b in BUTTONS for b in buttons):
            raise LedgerError('route contains invalid applied buttons')
        if type(frames) is not int or not 1 <= frames <= MAX_FRAMES:
            raise LedgerError(f'route decisions need 1..{MAX_FRAMES} frames')
    return decisions


def cmd_oracle(a):
    """Runs in the foreground until stopped. It needs the emulator runtime, so start it with that Python."""
    import importlib
    from oracle import NesBackend, Oracle, PolicyPlayer, ReplayPlayer, serve
    os.environ['REWARD10_GAMES_ROOT'] = str(ref_dir(a))
    publish_socket(a, ledger(a).read()['mode'])
    game = importlib.import_module(f'games.{a.slug}')
    player = None
    if a.route:
        player = ReplayPlayer(route_decisions(game, a.route))
    elif a.policy:
        player = PolicyPlayer(a.policy.split())
    backend = NesBackend(game)
    backend.reset()
    serve(Oracle(backend, ref_dir(a) / 'evidence' / 'oracle' / a.session, player), socket_path(a))


def cmd_isolation(a):
    problems = isolation.scan(builder_dir(a), ref_dir(a))
    return {'isolated': not problems, 'problems': problems}


def cmd_import_assets(a):
    """Copy prepared assets with provenance. Nothing is extracted from a ROM."""
    state = ledger(a).read()
    if state['mode'] == 'mechanics':
        raise LedgerError('mechanics mode uses original art; assets can only be imported in faithful mode')
    src = Path(a.source).expanduser().resolve(strict=True)
    if not (src / 'manifest.json').exists():
        raise LedgerError('the asset folder needs a manifest.json listing each file and its licence')
    if state['mode'] == 'recreate':
        validate_assets(src)
    dest = builder_dir(a) / 'assets'
    if state['mode'] == 'recreate':
        problems = isolation.scan(src, ref_dir(a))
        if problems:
            raise LedgerError('asset kit is not isolated: ' + '; '.join(problems))
        if dest.is_symlink():
            raise LedgerError('asset destination must not be a symlink')
        with tempfile.TemporaryDirectory(dir=builder_dir(a), prefix='.asset-import-') as stage:
            kit = Path(stage) / 'assets'
            shutil.copytree(src, kit)
            validate_assets(kit)
            backup = dest.with_name('assets-backup-' + uuid.uuid4().hex)
            if dest.exists():
                dest.rename(backup)
            try:
                kit.rename(dest)
            except OSError:
                if backup.exists():
                    backup.rename(dest)
                raise
    else:
        shutil.copytree(src, dest, dirs_exist_ok=True)
    return {'imported': str(dest), 'files': sum(1 for p in dest.rglob('*') if p.is_file())}


def cmd_balance(a):
    res = run_reward_tool(a, [str(CORE / 'balance.py'), a.slug, '--steps', str(a.steps)])
    return res


def progress_unit(a):
    """Read the game's PROGRESS_UNIT in the reward runtime, which holds the imports the module needs."""
    code = f"import importlib;print(importlib.import_module('games.{a.slug}').PROGRESS_UNIT)"
    p = subprocess.run([a.python, '-c', code], env=reward_env(a), cwd=ref_dir(a), capture_output=True, text=True)
    if p.returncode:
        raise LedgerError(f'cannot load the game module: {p.stderr[-800:]}')
    return float(p.stdout)


def cmd_lint(a):
    import reward_lint
    problems = reward_lint.lint_dir(ref_dir(a) / 'evidence' / a.folder, progress_unit(a))
    return {'clean': not problems, 'problems': problems[:40], 'total': len(problems)}


def cmd_engine_setup(a):
    return train_ctl.engine_setup(ref_dir(a), a.slug, a.boot_frames)


def cmd_parity(a):
    return train_ctl.parity(ref_dir(a), a.slug, a.python)


def cmd_train_start(a):
    return train_ctl.start(ref_dir(a), a.slug, a.python, a.args.split() if a.args else [], a.share_gpu)


def cmd_train_stop(a):
    return train_ctl.stop(ref_dir(a), a.slug)


def cmd_watch(a):
    return train_ctl.check(ref_dir(a), a.slug)


def cmd_fix_begin(a):
    return train_ctl.fix_begin(ref_dir(a), a.slug, a.finding, a.hypothesis)


def cmd_fix_validate(a):
    return train_ctl.fix_validate(ref_dir(a), a.slug, a.python, reward_env(a), progress_unit(a))


def cmd_fix_apply(a):
    return train_ctl.fix_apply(ref_dir(a), a.slug, a.python)


def cmd_fix_review(a):
    return train_ctl.fix_review(ref_dir(a), a.slug)


def read_tolerances(a):
    return json.loads(Path(a.tolerances).read_text())


def cmd_compare(a):
    return compare_mod.compare(a.reference, a.rebuild, read_tolerances(a))


def cmd_completion(a):
    state = ledger(a).read()
    if state.get('mode') == 'recreate' and not state.get('contract'):
        raise LedgerError('verify must pin the full-game reference contract first')
    report = completion.check(a.manifest, state.get('contract'))
    if state.get('mode') == 'recreate':
        report['problems'].extend(completion.verify_reference(a.manifest, state['contract'], ref_dir(a) / 'evidence' / 'oracle'))
        report['problems'].extend(visual_check.check(a.manifest, ref_dir(a) / 'evidence' / 'oracle'))
        report['complete'] = not report['problems']
    return report


def baseline_path(a):
    return ref_dir(a) / 'evidence' / 'gate-baseline.json'


def cmd_gate(a):
    if a.save_baseline:
        return {'saved': gate_mod.save_baseline(a.reference, a.rebuild, read_tolerances(a), baseline_path(a))}
    return gate_mod.run(a.reference, a.rebuild, read_tolerances(a), baseline_path(a))


def parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference-root', default=os.environ.get('REBUILD_REFERENCE_ROOT', '~/.local/share/rebuild/reference'))
    ap.add_argument('--builder-root', default=os.environ.get('REBUILD_BUILDER_ROOT', '~/rebuild-projects'))
    ap.add_argument('--python', default=os.environ.get('REBUILD_PYTHON', sys.executable))
    sub = ap.add_subparsers(dest='cmd', required=True)

    def add(name, fn, *args):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        p.add_argument('slug')
        for flag, kw in args:
            p.add_argument(flag, **kw)

    add('init', cmd_init, ('--rom', dict(required=True)), ('--mode', dict(default='recreate')), ('--rights', {}))
    add('status', cmd_status)
    add('completion', cmd_completion, ('--manifest', dict(required=True)))
    add('set', cmd_set, ('stage', {}), ('status', {}), ('--evidence', {}), ('--note', {}))
    add('reward-check', cmd_reward_check)
    add('audit', cmd_audit, ('--episodes', dict(type=int, default=12)), ('--steps', dict(type=int, default=3000)))
    add('search', cmd_search, ('--seconds', dict(type=float, default=300)), ('--workers', dict(type=int, default=8)))
    add('balance', cmd_balance, ('--steps', dict(type=int, default=600)))
    add('lint', cmd_lint, ('--folder', dict(default='audit')))
    add('engine-setup', cmd_engine_setup, ('--boot-frames', dict(type=int, required=True)))
    add('parity', cmd_parity)
    add('train-start', cmd_train_start, ('--args', {}), ('--share-gpu', dict(action='store_true')))
    add('train-stop', cmd_train_stop)
    add('watch', cmd_watch)
    add('fix-begin', cmd_fix_begin, ('--finding', dict(required=True)), ('--hypothesis', dict(required=True)))
    add('fix-validate', cmd_fix_validate)
    add('fix-apply', cmd_fix_apply)
    add('fix-review', cmd_fix_review)
    add('oracle', cmd_oracle, ('--session', dict(default='default')), ('--route', {}), ('--policy', {}))
    add('isolation', cmd_isolation)
    add('import-assets', cmd_import_assets, ('--source', dict(required=True)))
    trace = (('--reference', dict(required=True)), ('--rebuild', dict(required=True)), ('--tolerances', dict(required=True)))
    add('compare', cmd_compare, *trace)
    add('gate', cmd_gate, *trace, ('--save-baseline', dict(action='store_true')))
    return ap


def main():
    a = parser().parse_args()
    try:
        result = a.fn(a)
    except (ValueError, train_ctl.TrainError, OSError, KeyError, TypeError) as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)
    if result is not None:
        print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
