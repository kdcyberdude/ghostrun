import json

import numpy as np
import pytest

import gate
import isolation
from compare import compare
from ledger import Ledger, LedgerError, check_rights
from oracle import Oracle, OracleError, ReplayPlayer


class Fake:
    def __init__(self):
        self.x = 0

    def reset(self):
        self.x = 0

    def step(self, buttons, frames):
        self.x += frames * (1 if 'RIGHT' in buttons else 0)

    def screen(self):
        return np.zeros((240, 256, 3), np.uint8)

    def observables(self):
        return {'x': self.x}

    def save(self):
        return self.x

    def load(self, snap):
        self.x = snap


def test_oracle_steps_and_never_leaks(tmp_path):
    o = Oracle(Fake(), tmp_path)
    assert o.handle({'op': 'reset'})['frame'] == 0
    r = o.handle({'op': 'step', 'buttons': ['RIGHT'], 'frames': 5})
    assert r['observables'] == {'x': 5} and r['frame'] == 5
    assert 'image_png_base64' not in r and not {'ram', 'rom', 'state'} & set(r)
    rows = [json.loads(line) for line in (tmp_path / 'trace.jsonl').read_text().splitlines()]
    assert [row['f'] for row in rows] == list(range(6))
    assert rows[0]['x'] == 0 and rows[-1]['x'] == 5


@pytest.mark.parametrize('req', [{'op': 'ram'}, {'op': 'step', 'poke': 1}, {'op': 'step', 'frames': 0},
                                 {'op': 'step', 'buttons': ['Z']}, {'op': 'restore', 'name': 'none'}])
def test_oracle_rejects(tmp_path, req):
    with pytest.raises(OracleError):
        Oracle(Fake(), tmp_path).handle(req)


def test_oracle_checkpoint_and_player(tmp_path):
    o = Oracle(Fake(), tmp_path, ReplayPlayer([(['RIGHT'], 2), ([], 1)]))
    o.handle({'op': 'reset'})
    o.handle({'op': 'checkpoint', 'name': 'a'})
    r = o.handle({'op': 'play', 'ticks': 5})
    assert r['finished'] and len(r['moves']) == 2 and r['observables'] == {'x': 2}
    assert o.handle({'op': 'restore', 'name': 'a'})['observables'] == {'x': 0}


def write(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


TOL = {'x': {'near': 3, 'far': 8}}


def test_compare_first_divergence(tmp_path):
    a = write(tmp_path / 'a', [{'f': 0, 'x': 0}, {'f': 1, 'x': 10}, {'f': 2, 'x': 20}])
    b = write(tmp_path / 'b', [{'f': 0, 'x': 1}, {'f': 1, 'x': 15}, {'f': 2, 'x': 40}])
    r = compare(a, b, TOL)
    assert (r['events'], r['large']) == (2, 1) and r['first_divergence']['frame'] == 1


def test_gate(tmp_path):
    ref = write(tmp_path / 'ref', [{'f': 0, 'x': 0}, {'f': 1, 'x': 10}])
    good = write(tmp_path / 'good', [{'f': 0, 'x': 0}, {'f': 1, 'x': 10}])
    bad = write(tmp_path / 'bad', [{'f': 0, 'x': 0}, {'f': 1, 'x': 30}])
    base = tmp_path / 'base.json'
    assert gate.run(ref, good, TOL, base)['verdict'] == 'FAIL'
    gate.save_baseline(ref, good, TOL, base)
    assert gate.run(ref, good, TOL, base)['verdict'] == 'PASS'
    assert gate.run(ref, bad, TOL, base)['verdict'] == 'REGRESSION'
    assert gate.run(ref, bad, {'x': {'near': 99, 'far': 99}}, base)['verdict'] == 'FAIL'
    write(ref, [{'f': 0, 'x': 0}, {'f': 1, 'x': 30}])
    assert gate.run(ref, bad, TOL, base)['verdict'] == 'FAIL'


def test_isolation(tmp_path):
    ref, b = tmp_path / 'ref', tmp_path / 'b'
    ref.mkdir(), b.mkdir()
    assert isolation.scan(b, ref) == []
    (b / 'g.nes').write_bytes(b'x')
    (b / 'a.ts').write_text("import 'jsnes'")
    (b / 'c.js').write_text(str(ref))
    (b / 'link').symlink_to(ref)
    assert len(isolation.scan(b, ref)) == 4
    assert not isolation.paths_are_separate(ref, ref / 'sub')


def test_ledger(tmp_path):
    led = Ledger(tmp_path / 's.json')
    led.create('g', 'mechanics')
    with pytest.raises(LedgerError):
        led.set('reward', 'passed', 'e')
    led.set('intake', 'passed', 'e')
    with pytest.raises(LedgerError):
        led.set('reward', 'passed')
    assert led.next_stage() == 'reward'
    assert Ledger(tmp_path / 's.json').read()['stages']['intake']['status'] == 'passed'


@pytest.mark.parametrize('rights', [None, {'basis': 'fan'}, {'basis': 'owner'}, {'basis': 'open-license', 'source': 'u'}])
def test_faithful_needs_rights(rights):
    with pytest.raises(LedgerError):
        check_rights('faithful', rights)


def test_rights_ok():
    check_rights('mechanics', None)
    check_rights('faithful', {'basis': 'open-license', 'source': 'u', 'license': 'MIT'})


def test_lint_catches_wrap():
    from reward_lint import lint_rows
    row = dict(in_play=True, level=15, progress_valid=True, score=0, lives=2)
    rows = [{**row, 't': 1, 'progress': 800.0}, {**row, 't': 2, 'progress': 65000.0}]
    assert 'progress jumped' in lint_rows(rows, 3000.0)[0]
    assert lint_rows([{**row, 't': 1, 'progress': 800.0}, {**row, 't': 2, 'progress': 804.0}], 3000.0) == []


def test_balance_flags_standing_still():
    import sys, types
    sys.modules.setdefault('nesram', types.SimpleNamespace(Nes=None))
    sys.modules.setdefault('search', types.SimpleNamespace(apply_action=None, load=None))
    sys.modules.setdefault('reward', types.SimpleNamespace(RewardTracker=None))
    from balance import judge
    run = {'action': 'R', 'discounted_return': -6.14, 'level': 0, 'progress': 900.0}
    crouch = {'action': 'D', 'discounted_return': -0.55, 'level': 0, 'progress': 2.0}
    assert 'without moving' in judge([run, crouch])
    assert judge([{**run, 'discounted_return': 0.5}, crouch]) is None


def test_status_of_unknown_game_explains(tmp_path):
    import argparse, cli
    (tmp_path / 'known').mkdir()
    Ledger(tmp_path / 'known' / 'state.json').create('known', 'mechanics')
    out = cli.cmd_status(argparse.Namespace(reference_root=str(tmp_path), slug='missing'))
    assert 'ghostrun_init' in out['error'] and out['games'] == ['known']


def test_oracle_batched_per_frame_matches_single_steps(tmp_path):
    batch = Oracle(Fake(), tmp_path / 'batch')
    single = Oracle(Fake(), tmp_path / 'single')
    reply = batch.handle({'op': 'step', 'buttons': ['RIGHT'], 'frames': 5, 'per_frame': True})
    expected = [single.handle({'op': 'step', 'buttons': ['RIGHT'], 'frames': 1})['observables']['x'] for _ in range(5)]
    assert [r['x'] for r in reply['trace']] == expected
    assert [r['f'] for r in reply['trace']] == [1, 2, 3, 4, 5]
    assert reply['frame'] == 5


def test_prepared_assets_reject_changed_unlisted_and_escaping_files(tmp_path):
    from compare import sha256
    from prepared_assets import validate_assets
    kit = tmp_path / 'kit'
    kit.mkdir()
    asset = kit / 'sprite.png'
    asset.write_bytes(b'observed frame fixture')
    manifest = {'files': [{'path': 'sprite.png', 'source': 'observed frame 0',
                           'method': 'observed-frame', 'sha256': sha256(asset)}]}
    (kit / 'manifest.json').write_text(json.dumps(manifest))
    assert validate_assets(kit) == manifest
    asset.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        validate_assets(kit)
    manifest['files'][0]['sha256'] = sha256(asset)
    (kit / 'manifest.json').write_text(json.dumps(manifest))
    (kit / 'extra.png').write_bytes(b'unlisted')
    with pytest.raises(ValueError, match='every file'):
        validate_assets(kit)
    manifest['files'][0]['path'] = '../outside.png'
    (tmp_path / 'outside.png').write_bytes(b'external')
    (kit / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='inside the kit'):
        validate_assets(kit)


def test_policy_reset_replays_first_action_each_time():
    from oracle import PolicyPlayer
    player = PolicyPlayer.__new__(PolicyPlayer)
    calls = []
    def reply(**request):
        calls.append(request['op'])
        return {'ok': True, 'buttons': ['RIGHT'], 'frames': 1, 'tick': 0, 'mask': 128}
    player._call = reply
    for _ in range(2):
        player.reset(b'frame')
        assert player.next(b'frame') == (['RIGHT'], 1)
        player.next(b'frame')
    assert calls == ['reset', 'advance', 'reset', 'advance']


def test_asset_kit_rejects_unlisted_directory_symlink_and_rom(tmp_path):
    from prepared_assets import validate_assets
    from compare import sha256
    kit = tmp_path / 'kit'
    kit.mkdir()
    (kit / 'sprite.png').write_bytes(b'image')
    item = {'path': 'sprite.png', 'source': 'frame0', 'method': 'observed-frame', 'sha256': sha256(kit / 'sprite.png')}
    (kit / 'manifest.json').write_text(json.dumps({'files': [item]}))
    private = tmp_path / 'private'
    private.mkdir()
    (private / 'game.nes').write_bytes(b'private ROM')
    (kit / 'unlisted').symlink_to(private, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        validate_assets(kit)
    (kit / 'unlisted').unlink()
    (kit / 'game.nes').write_bytes(b'ROM')
    with pytest.raises(ValueError, match='reference file'):
        validate_assets(kit)


def test_replacing_asset_kit_removes_stale_files_and_preserves_previous_kit(tmp_path):
    import argparse
    import cli
    from compare import sha256
    ref, build, source = tmp_path / 'ref', tmp_path / 'build', tmp_path / 'source'
    (ref / 'g').mkdir(parents=True)
    (build / 'g').mkdir(parents=True)
    source.mkdir()
    Ledger(ref / 'g/state.json').create('g', 'recreate')
    def kit(name):
        for p in source.iterdir():
            p.unlink()
        p = source / name
        p.write_bytes(b'asset')
        (source / 'manifest.json').write_text(json.dumps({'files': [dict(path=name, source='frame0', method='observed-frame', sha256=sha256(p))]}))
    args = argparse.Namespace(reference_root=str(ref), builder_root=str(build), slug='g', source=str(source))
    kit('old.png')
    cli.cmd_import_assets(args)
    kit('new.png')
    cli.cmd_import_assets(args)
    assert not (build / 'g/assets/old.png').exists()
    assert (build / 'g/assets/new.png').exists()
    assert list((build / 'g').glob('assets-backup-*/old.png'))


def test_parallel_work_can_run_without_premature_acceptance(tmp_path):
    led = Ledger(tmp_path / 'state.json')
    led.create('g', 'recreate')
    led.set('explore', 'running', 'provisional training')
    led.set('assets', 'running', 'prepare observed kit')
    assert led.next_stage() == 'intake'
    with pytest.raises(LedgerError):
        led.set('explore', 'passed', 'still missing earlier verification')
