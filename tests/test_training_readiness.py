"""Require real recorded policy inputs for provisional and final learning evidence."""
import json
from pathlib import Path

import pytest

import completion
from compare import sha256
from test_completion import make_training_evidence, capture_training_evidence, read_rows, write_rows


def artifacts(path, play=0):
    manifest = json.loads(path.read_text())
    item = manifest['plays'][play]
    receipt_path = path.parent / item['evaluation']
    receipt = json.loads(receipt_path.read_text())
    return manifest, item, receipt_path, receipt


def update_summary(path, edit, play=0):
    _, _, receipt_path, receipt = artifacts(path, play)
    summary = receipt_path.parent / receipt['summary']['path']
    rows = json.loads(summary.read_text())
    edit(rows[0])
    summary.write_text(json.dumps(rows))
    receipt['summary']['sha256'] = sha256(summary)
    receipt_path.write_text(json.dumps(receipt))


def test_losing_actual_policy_data_is_provisional_not_a_learning_pass(tmp_path):
    path = make_training_evidence(tmp_path)
    manifest, play, _, _ = artifacts(path)
    manifest['plays'] = [play]
    path.write_text(json.dumps(manifest))
    trace = path.parent / play['trace']
    rows = read_rows(trace)
    rows[-1].update(terminal=0, game_over=1, lives=0)
    write_rows(trace, rows)
    update_summary(path, lambda r: r.update(end='game_over', deaths=3))
    contract = {'levels':['unseen-later-level'], 'training':{'no_life_loss':True}}
    assert completion.training(path, contract, game='game', require_win=False)['complete']
    assert not completion.training(path, contract, game='game')['complete']


def test_no_life_loss_is_explicit_and_detects_loss_even_after_an_extra_life(tmp_path):
    path = make_training_evidence(tmp_path)
    _, play, _, _ = artifacts(path)
    trace = path.parent / play['trace']
    rows = read_rows(trace)
    rows[1]['lives'] = 2
    rows[2]['lives'] = 3
    write_rows(trace, rows)
    update_summary(path, lambda r: r.update(deaths=1))
    assert completion.training(path, {'levels':['one','two']}, game='game')['complete']
    strict = {'levels':['one','two'], 'training':{'no_life_loss':True}}
    result = completion.training(path, strict, game='game')
    assert not result['complete'] and 'trained policy lost a life' in result['problems']


def test_provisional_data_still_rejects_search_controller(tmp_path):
    path = make_training_evidence(tmp_path)
    manifest = json.loads(path.read_text())
    manifest['plays'][0]['controller'] = 'search'
    path.write_text(json.dumps(manifest))
    assert not completion.training(path, {'levels':[]}, require_win=False)['complete']


def test_unreceipted_claim_does_not_publish_policy_data(tmp_path):
    path = make_training_evidence(tmp_path)
    manifest = json.loads(path.read_text())
    manifest['plays'][0].pop('evaluation')
    path.write_text(json.dumps(manifest))
    assert not completion.training(path, {'levels':[]}, require_win=False)['complete']


def test_edited_checkpoint_receipt_summary_and_pads_are_rejected(tmp_path):
    for artifact in ('checkpoint', 'receipt', 'summary', 'pads'):
        root = tmp_path / artifact
        root.mkdir()
        path = make_training_evidence(root)
        manifest, _, receipt_path, receipt = artifacts(path)
        if artifact == 'checkpoint':
            (root / manifest['checkpoint']).write_bytes(b'edited')
        elif artifact == 'receipt':
            receipt['checkpoint_sha256'] = '0' * 64
            receipt_path.write_text(json.dumps(receipt))
        else:
            file = root / (receipt['summary']['path'] if artifact == 'summary' else receipt['inputs'][0]['path'])
            file.write_bytes(file.read_bytes() + b' ')
        assert not completion.training(path, {'levels':['one','two']})['complete'], artifact


def test_input_alignment_cannot_be_invented(tmp_path):
    path = make_training_evidence(tmp_path)
    manifest, play, _, _ = artifacts(path)
    trace = path.parent / play['trace']
    rows = read_rows(trace)
    rows[1]['buttons'] = ['DOWN']
    write_rows(trace, rows)
    assert not completion.training(path, {'levels':['one','two']})['complete']
    rows[1]['buttons'] = ['RIGHT']
    write_rows(trace, rows)
    manifest['plays'][0]['boot_frames'] = 1
    path.write_text(json.dumps(manifest))
    assert not completion.training(path, {'levels':['one','two']})['complete']


def test_reusing_one_actual_evaluation_is_not_reliability(tmp_path):
    path = make_training_evidence(tmp_path)
    manifest = json.loads(path.read_text())
    manifest['plays'][1] = dict(manifest['plays'][0])
    path.write_text(json.dumps(manifest))
    report = completion.training(path, {'levels':['one','two']})
    assert not report['complete']
    assert any('separately recorded' in problem for problem in report['problems'])


def test_proof_is_deterministic_and_detects_edited_native_measurements(tmp_path):
    path = make_training_evidence(tmp_path)
    contract = {'levels':['one','two']}
    first = completion.training(path, contract)
    assert first['complete'] and completion.training(path, contract)['proof'] == first['proof']
    assert completion.training(path, contract, require_win=False)['proof'] == first['proof']
    _, play, _, _ = artifacts(path)
    trace = path.parent / play['trace']
    rows = read_rows(trace)
    rows[1]['player_x'] = 99
    write_rows(trace, rows)
    changed = completion.training(path, contract)
    assert changed['complete'] and changed['proof'] != first['proof']


def test_wrong_game_and_no_win_are_not_final_learning(tmp_path):
    path = make_training_evidence(tmp_path)
    assert not completion.training(path, {'levels':['one','two']}, game='other-game')['complete']
    update_summary(path, lambda r: r.update(end='stall'))
    assert not completion.training(path, {'levels':['one','two']})['complete']


def published_losing_policy(tmp_path):
    from types import SimpleNamespace
    import cli
    from ledger import Ledger
    path = make_training_evidence(tmp_path)
    manifest, play, _, _ = artifacts(path)
    manifest['plays'] = [play]
    path.write_text(json.dumps(manifest))
    trace = path.parent / play['trace']
    rows = read_rows(trace)
    rows[-1].update(terminal=0, game_over=1, lives=0)
    write_rows(trace, rows)
    update_summary(path, lambda r: r.update(end='game_over', deaths=3))
    led = Ledger(tmp_path / 'reference/game/state.json')
    led.path.parent.mkdir(parents=True)
    led.create('game', 'recreate')
    capture_training_evidence(path, led.path.parent / 'evidence/oracle')
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game',
                           manifest=str(path), final=False)
    assert cli.cmd_policy_check(args)['valid']
    return path, led, args


def test_losing_provisional_policy_is_publishable_without_a_learning_pass(tmp_path):
    import cli
    path, led, args = published_losing_policy(tmp_path)
    assert led.read()['stages']['explore']['status'] == 'pending'
    assert cli.policy_readiness(args)['valid']
    assert not cli.policy_readiness(args, final=True)['valid']
    manifest = json.loads(path.read_text())
    manifest['plays'][0]['controller'] = 'search'
    path.write_text(json.dumps(manifest))
    assert not cli.cmd_policy_check(args)['valid']
    assert not cli.policy_readiness(args)['valid']


def test_private_capture_authenticates_losing_policy_prefix_and_rejects_forged_states(tmp_path):
    path = make_training_evidence(tmp_path)
    oracle_root = tmp_path / 'oracle'
    capture_training_evidence(path, oracle_root)
    manifest, play, _, _ = artifacts(path)
    manifest['plays'] = [play]
    path.write_text(json.dumps(manifest))
    trace = path.parent / play['trace']
    original = read_rows(trace)
    contract = {'levels':['one','two'], 'fields':{'player':{'player_x':0}}}
    write_rows(trace, original[:2])
    update_summary(path, lambda r: r.update(end='game_over', deaths=3))
    assert completion.training(path, contract, require_win=False, oracle_root=oracle_root)['complete']
    for field, value in [('player_x',99), ('level','invented'), ('lives',8), ('terminal',1)]:
        changed = [dict(row) for row in original[:2]]
        changed[1][field] = value
        write_rows(trace, changed)
        report = completion.training(path, contract, require_win=False, oracle_root=oracle_root)
        assert not report['complete'] and any('private oracle' in p for p in report['problems']), field
    write_rows(trace, original[:2])
    assert not completion.training(path, contract, require_win=False,
                                   oracle_root=tmp_path / 'missing-private-captures')['complete']


def test_private_policy_pin_rejects_changed_manifest_receipt_or_checkpoint(tmp_path):
    import cli
    for defect in ('manifest','receipt','checkpoint'):
        root = tmp_path / defect
        root.mkdir()
        path, _, args = published_losing_policy(root)
        manifest, _, receipt_path, receipt = artifacts(path)
        if defect == 'manifest':
            manifest['note'] = 'edited after acceptance'
            path.write_text(json.dumps(manifest))
        elif defect == 'receipt':
            receipt['evaluation_id'] = 'edited-after-acceptance'
            receipt_path.write_text(json.dumps(receipt))
        else:
            (root / manifest['checkpoint']).write_bytes(b'changed')
        assert not cli.policy_readiness(args)['valid'], defect


def test_builder_accepts_genuine_losing_policy_but_public_mode_cannot_bypass_proof(tmp_path):
    import sys
    from test_plugin import Ctx, load
    path, led, _ = published_losing_policy(tmp_path)
    root = tmp_path / 'build/game'
    assets = root / 'assets'
    assets.mkdir(parents=True)
    sprite = assets / 'sprite.png'
    sprite.write_bytes(b'observed sprite fixture')
    (assets / 'manifest.json').write_text(json.dumps({'files':[
        {'path':sprite.name,'source':'native frame','method':'observed-frame','sha256':sha256(sprite)}]}))
    # The private mode wins even if a caller downgrades this public descriptor.
    (root / '.oracle.json').write_text(json.dumps({'mode':'mechanics','socket':'unused-fixture.sock'}))
    context = Ctx({'reference_root':str(tmp_path / 'reference'), 'builder_root':str(tmp_path / 'build'),
                   'python':sys.executable})
    plugin = load().Plugin(context)
    plugin.oracle_hello = lambda *a, **k: {'ok':True}
    assert json.loads(plugin.builder_enter({'slug':'game'},task_id='builder'))['role'] == 'builder'
    state = led.read()
    state.pop('policy_evidence')
    state['stages']['explore'] = {'status':'passed','evidence':'a label is not proof'}
    led._write(state)
    reply = json.loads(plugin.builder_enter({'slug':'game'},task_id='new-builder'))
    assert 'error' in reply and 'trained-policy data' in reply['error']


@pytest.mark.parametrize('changed_checkpoint', [False, True])
def test_evaluator_receipt_hashes_actual_outputs_and_keeps_neutral_prefix(tmp_path, monkeypatch, changed_checkpoint):
    """Exercise the CLI receipt path without loading a model or running a GPU."""
    import ast
    import hashlib
    import sys
    import uuid
    from types import SimpleNamespace
    checkpoint = tmp_path / 'policy.pt'
    checkpoint.write_bytes(b'accepted model')
    original_hash = sha256(checkpoint)
    out = tmp_path / 'evaluation'
    out.mkdir()
    monkeypatch.setattr(sys, 'argv', ['evaluate.py', str(checkpoint), str(out), '--games', 'game'])
    model = SimpleNamespace(load_state_dict=lambda state: None)
    model.to = lambda dev: model

    def evaluate(*args, **kwargs):
        assert sha256(checkpoint) == original_hash
        results = [{'game':'game','deaths':0,'end':'won'}]
        (out / 'summary.json').write_text(json.dumps(results))
        (out / 'game.pads.bin').write_bytes(bytes(494 + 4) + bytes([128]))
        if changed_checkpoint:
            checkpoint.write_bytes(b'model replaced during evaluation')
        return results

    fake_torch = SimpleNamespace(device=lambda name: SimpleNamespace(type=name),
                                 load=lambda *a, **kw: {'cfg':{'core':1},'model':{}}, float32='float32')
    module = ast.parse((Path(__file__).parents[1] / 'engine/rl/evaluate.py').read_text())
    main = next(node for node in module.body if isinstance(node, ast.If))
    code = compile(ast.Module(body=main.body, type_ignores=[]), 'evaluate.py', 'exec')
    namespace = {'torch':fake_torch,'Policy':lambda **kw: model,'evaluate':evaluate,
                 'Path':Path,'hashlib':hashlib,'uuid':uuid,'json':json,'boot_pads':lambda game: bytes(494)}
    if changed_checkpoint:
        with pytest.raises(RuntimeError, match='checkpoint changed'):
            exec(code, namespace)
        assert not (out / 'evaluation-proof.json').exists()
        return
    exec(code, namespace)
    receipt = json.loads((out / 'evaluation-proof.json').read_text())
    assert receipt['checkpoint_sha256'] == original_hash
    assert receipt['controller'] == 'trained-policy' and receipt['evaluation_id']
    assert receipt['summary']['sha256'] == sha256(out / 'summary.json')
    assert receipt['inputs'] == [{'game':'game','path':'game.pads.bin',
                                  'sha256':sha256(out / 'game.pads.bin'),
                                  'boot_frames':494,'neutral_frames':4}]
