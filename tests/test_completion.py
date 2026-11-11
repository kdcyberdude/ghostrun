"""Reject incomplete recreation evidence even when a regression baseline passes."""
import json
from types import SimpleNamespace

import pytest

import cli
import completion
import gate
from compare import compare, load
from ledger import Ledger, LedgerError


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def evidence(tmp_path):
    manifest = {
        'levels': ['one'],
        'cases': ['clear', 'heldout', 'death-recovery'],
        'fields': {
            'player': {'player_x': 2, 'player_y': 2},
            'enemies': {'enemy_x': 2, 'enemy_y': 2, 'enemy_mode': 0},
            'rules': {'score': 0, 'power_active': 0},
            'outcome': {'lives': 0, 'terminal': 0},
        },
        'randomness': 'reproduced-from-reset',
        'unresolved': [],
        'routes': [],
    }
    for kind, button in [('clear', 'RIGHT'), ('heldout', 'LEFT'), ('death-recovery', 'UP')]:
        rows = [
            {'f': f, 'buttons': [] if f == 0 else [button], 'player_x': f * 2, 'player_y': 0,
             'enemy_x': 10 + f, 'enemy_y': 4, 'enemy_mode': 0, 'score': f * 10,
             'power_active': 0, 'lives': 2 if kind == 'death-recovery' and f >= 1 else 3,
             'terminal': int(kind != 'death-recovery' and f == 3)}
            for f in range(4)
        ]
        route = {'level': 'one', 'kind': kind}
        for role in ('reference', 'rebuild', 'repeat'):
            name = f'{kind}.{role}.jsonl'
            write_rows(tmp_path / name, rows)
            route[role] = name
        manifest['routes'].append(route)
    path = tmp_path / 'completion.json'
    path.write_text(json.dumps(manifest))
    return path


def change_manifest(path, edit):
    manifest = json.loads(path.read_text())
    edit(manifest)
    path.write_text(json.dumps(manifest))


def change_trace(path, role, edit, route=0):
    manifest = json.loads(path.read_text())
    trace = path.parent / manifest['routes'][route][role]
    rows = read_rows(trace)
    edit(rows)
    write_rows(trace, rows)


def test_complete_routes_pass_with_repeat_and_measured_death_recovery(evidence):
    report = completion.check(evidence)
    assert report['complete'] is True
    assert report['problems'] == []
    assert len(report['routes']) == 3
    assert all(r['reference_sha256'] == r['rebuild_sha256'] == r['repeat_sha256']
               for r in report['routes'])


@pytest.mark.parametrize('role', ['reference', 'rebuild', 'repeat'])
def test_missing_enemy_measurement_rejected(evidence, role):
    change_trace(evidence, role, lambda rows: rows[2].pop('enemy_x'))
    assert not completion.check(evidence)['complete']


def test_missing_enemy_group_rejected(evidence):
    change_manifest(evidence, lambda manifest: manifest['fields'].pop('enemies'))
    report = completion.check(evidence)
    assert not report['complete']
    assert 'missing gameplay field group: enemies' in report['problems']


@pytest.mark.parametrize('role', ['reference', 'rebuild', 'repeat'])
def test_trace_frame_hole_rejected(evidence, role):
    change_trace(evidence, role, lambda rows: rows.pop(1))
    assert not completion.check(evidence)['complete']


def test_duplicate_frames_rejected_instead_of_silently_overwritten(evidence):
    change_trace(evidence, 'rebuild', lambda rows: rows.append(rows[-1].copy()))
    with pytest.raises(ValueError, match='duplicate trace frames'):
        completion.check(evidence)


@pytest.mark.parametrize('role', ['rebuild', 'repeat'])
def test_different_inputs_rejected_even_when_positions_match(evidence, role):
    change_trace(evidence, role, lambda rows: rows[1].update(buttons=['DOWN']))
    report = completion.check(evidence)
    assert not report['complete']
    assert any('input mismatch' in p for p in report['problems'])


def test_missing_reset_inputs_rejected(evidence):
    change_trace(evidence, 'reference', lambda rows: rows[0].pop('buttons'))
    assert not completion.check(evidence)['complete']


@pytest.mark.parametrize('kind', ['clear', 'heldout', 'death-recovery'])
def test_required_route_coverage_cannot_be_omitted(evidence, kind):
    change_manifest(evidence, lambda manifest: manifest.update(
        routes=[r for r in manifest['routes'] if r['kind'] != kind]))
    report = completion.check(evidence)
    assert not report['complete']
    assert f'missing {kind} route for level one' in report['problems']


def test_every_requested_level_needs_routes(evidence):
    change_manifest(evidence, lambda manifest: manifest['levels'].append('two'))
    assert not completion.check(evidence)['complete']


def test_heldout_reusing_reference_is_not_independent_coverage(evidence):
    def reuse(manifest):
        manifest['routes'][1].update({k: manifest['routes'][0][k]
                                     for k in ('reference', 'rebuild', 'repeat')})
    change_manifest(evidence, reuse)
    report = completion.check(evidence)
    assert not report['complete']
    assert 'routes must use distinct reference traces' in report['problems']


@pytest.mark.parametrize('kind_index', [0, 1])
def test_clear_route_must_reach_terminal(evidence, kind_index):
    for role in ('reference', 'rebuild', 'repeat'):
        change_trace(evidence, role, lambda rows: rows[-1].update(terminal=0), route=kind_index)
    assert not completion.check(evidence)['complete']


def test_death_recovery_route_must_measure_a_death(evidence):
    for role in ('reference', 'rebuild', 'repeat'):
        change_trace(evidence, role, lambda rows: [r.update(lives=3) for r in rows], route=2)
    assert not completion.check(evidence)['complete']


def test_death_without_surviving_movement_is_not_recovery(evidence):
    for role in ('reference', 'rebuild', 'repeat'):
        change_trace(evidence, role, lambda rows: [r.update(player_x=2) for r in rows[1:]], route=2)
    assert not completion.check(evidence)['complete']


def test_rebuild_difference_above_predeclared_bound_rejected(evidence):
    change_trace(evidence, 'rebuild', lambda rows: rows[2].update(player_x=7))
    report = completion.check(evidence)
    assert not report['complete']
    assert report['routes'][0]['comparison']['first_divergence']['frame'] == 2


def test_repeat_requires_exact_determinism_even_with_spatial_tolerance(evidence):
    change_trace(evidence, 'repeat', lambda rows: rows[2].update(player_x=5))
    report = completion.check(evidence)
    assert not report['complete']
    assert report['routes'][0]['repeat']['events'] == 1


@pytest.mark.parametrize('field', ['score', 'lives', 'terminal'])
def test_discrete_gameplay_outcomes_cannot_have_pixel_tolerances(evidence, field):
    def loosen(manifest):
        group = 'rules' if field == 'score' else 'outcome'
        manifest['fields'][group][field] = 1
    change_manifest(evidence, loosen)
    assert not completion.check(evidence)['complete']


@pytest.mark.parametrize('limit', [-1, 4, float('inf'), float('nan')])
def test_unbounded_or_nonfinite_tolerance_rejected(evidence, limit):
    change_manifest(evidence, lambda manifest: manifest['fields']['player'].update(player_x=limit))
    assert not completion.check(evidence)['complete']


def test_unresolved_mechanic_blocks_completion(evidence):
    change_manifest(evidence, lambda manifest: manifest.update(unresolved=['enemy release timing']))
    assert not completion.check(evidence)['complete']


def test_uncontrolled_randomness_cannot_claim_exact_trajectory_match(evidence):
    change_manifest(evidence, lambda manifest: manifest.update(randomness='unknown'))
    assert not completion.check(evidence)['complete']


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), 'unknown'])
def test_sparse_or_invalid_measurements_fail_even_if_saved_as_baseline(tmp_path, value):
    ref, new = tmp_path / 'ref.jsonl', tmp_path / 'new.jsonl'
    write_rows(ref, [{'f': 0, 'x': 1}])
    row = {'f': 0}
    if value is not None:
        row['x'] = value
    write_rows(new, [row])
    tolerances = {'x': {'near': 0, 'far': 0}}
    baseline = tmp_path / 'baseline.json'
    gate.save_baseline(ref, new, tolerances, baseline)
    report = gate.run(ref, new, tolerances, baseline)
    assert report['verdict'] == 'FAIL'
    counts = compare(ref, new, tolerances)
    assert counts['missing_fields'] + counts['invalid_values'] == 1


def test_default_init_uses_recreate_and_includes_final_delivery_stage(tmp_path):
    rom = tmp_path / 'input.nes'
    rom.write_bytes(b'NES\x1a' + bytes(64))
    args = cli.parser().parse_args(['--reference-root', str(tmp_path / 'ref'),
                                  '--builder-root', str(tmp_path / 'build'),
                                  'init', 'game', '--rom', str(rom)])
    result = cli.cmd_init(args)
    assert result['mode'] == 'recreate'
    state = Ledger(tmp_path / 'ref/game/state.json').read()
    assert state['mode'] == 'recreate' and 'visual3d' in state['stages']
    assert state['rights'] is None


def ready_gate_ledger(tmp_path, evidence):
    led = Ledger(tmp_path / 'reference/game/state.json')
    led.path.parent.mkdir(parents=True)
    led.create('game', 'recreate')
    manifest = json.loads(evidence.read_text())
    contract = {key: manifest[key] for key in ('levels', 'fields', 'cases')}
    contract.update(full_game=True, scope_basis='Controlled reference runs cover all levels and the ending.')
    contract_path = tmp_path / 'contract.json'
    contract_path.write_text(json.dumps(contract))
    for stage in led.read()['stages']:
        if stage == 'gate':
            break
        if stage == 'verify':
            cli.cmd_set(SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game',
                                        stage=stage, status='passed', evidence=str(contract_path), note=None))
        else:
            led.set(stage, 'passed', 'measured evidence')
    oracle_log = led.path.parent / 'evidence/oracle/session/trace.jsonl'
    oracle_log.parent.mkdir(parents=True)
    raw = []
    for route in manifest['routes']:
        for role in ('reference', 'repeat'):
            raw.extend({**row, 'frames': int(row['f'] != 0)}
                       for row in read_rows(evidence.parent / route[role]))
    write_rows(oracle_log, raw)
    return led


def test_recreate_gate_cannot_pass_on_prose_or_regression_report(tmp_path, evidence):
    led = ready_gate_ledger(tmp_path, evidence)
    regression = tmp_path / 'regression.json'
    regression.write_text(json.dumps({'verdict': 'PASS', 'result': {'events': 0}}))
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', stage='gate',
                           status='passed', evidence=str(regression), note=None)
    with pytest.raises(LedgerError, match='recreation incomplete'):
        cli.cmd_set(args)
    assert led.read()['stages']['gate']['status'] == 'pending'
    args.evidence = str(evidence)
    assert cli.cmd_set(args)['status'] == 'passed'
    assert led.next_stage() == 'visual3d'


@pytest.fixture
def delivery(evidence, monkeypatch):
    root = evidence.parent
    manifest = {'recreation': evidence.name, 'route_reference': 'clear.reference.jsonl'}
    for role in ('simulation', 'render2d', 'render3d'):
        manifest[role] = f'{role}.jsonl'
        write_rows(root / manifest[role], [
            {'f': f, 'buttons': [] if f == 0 else ['RIGHT'], 'terminal': int(f == 3),
             'state_hash': f'hash-{f}', 'audio_events': [] if f == 0 else ['pickup']}
            for f in range(4)
        ])
    for role in ('assets3d', 'build2d', 'build3d', 'video2d', 'video3d'):
        manifest[role] = f'{role}.artifact'
        (root / manifest[role]).write_bytes(b'nonempty artifact')
    path = root / 'delivery.json'
    path.write_text(json.dumps(manifest))
    calls = []

    def probe(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'streams': [{'codec_type': 'video'}], 'format': {'duration': '4.0'}}))
    monkeypatch.setattr('subprocess.run', probe)
    return path, manifest, calls


def test_delivery_checks_parity_artifacts_and_probes_both_videos(delivery):
    path, manifest, calls = delivery
    assert completion.delivery(path)['complete']
    assert [call[-1] for call in calls] == [str(path.parent / manifest[k]) for k in ('video2d', 'video3d')]
    assert all(call[0] == 'ffprobe' for call in calls)


@pytest.mark.parametrize('field,value', [('state_hash', 'wrong-state'), ('audio_events', ['wrong-sound'])])
def test_delivery_rejects_renderer_state_or_audio_mismatch(delivery, field, value):
    path, manifest, _ = delivery
    trace = path.parent / manifest['render3d']
    rows = read_rows(trace)
    rows[1][field] = value
    write_rows(trace, rows)
    assert not completion.delivery(path)['complete']


@pytest.mark.parametrize('artifact', ['assets3d', 'build2d', 'build3d'])
def test_delivery_rejects_missing_or_empty_artifacts(delivery, artifact):
    path, manifest, _ = delivery
    (path.parent / manifest[artifact]).write_bytes(b'')
    report = completion.delivery(path)
    assert not report['complete']
    assert f'missing artifact: {artifact}' in report['problems']


def test_delivery_rejects_missing_parity_fields_even_when_all_targets_equal(delivery):
    path, manifest, _ = delivery
    for role in ('simulation', 'render2d', 'render3d'):
        write_rows(path.parent / manifest[role], [{'f': 0}])
    assert not completion.delivery(path)['complete']


@pytest.mark.parametrize('data,code', [
    ({'streams': [], 'format': {'duration': '2'}}, 0),
    ({'streams': [{'codec_type': 'video'}], 'format': {'duration': '0'}}, 0),
    ({'streams': [{'codec_type': 'video'}], 'format': {'duration': 'NaN'}}, 0),
    ({'streams': [{'codec_type': 'video'}], 'format': {'duration': 'Infinity'}}, 0),
    ({'streams': [{'codec_type': 'video'}], 'format': {'duration': '2'}}, 1),
])
def test_delivery_rejects_invalid_recording(delivery, monkeypatch, data, code):
    path, _, _ = delivery
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(returncode=code, stdout=json.dumps(data)))
    report = completion.delivery(path)
    assert not report['complete']
    assert 'invalid video: video2d' in report['problems']
    assert 'invalid video: video3d' in report['problems']


@pytest.mark.parametrize('frame', [1.0, True, '1', -1])
def test_trace_loader_rejects_noninteger_boolean_or_negative_frames(tmp_path, frame):
    path = tmp_path / 'bad-frame.jsonl'
    write_rows(path, [{'f': 0, 'x': 0}, {'f': frame, 'x': 1}])
    with pytest.raises(ValueError):
        load(path)


def test_delivery_cannot_substitute_a_short_identical_parity_clip(delivery):
    path, manifest, _ = delivery
    for role in ('simulation', 'render2d', 'render3d'):
        write_rows(path.parent / manifest[role], [
            {'f': 0, 'buttons': [], 'terminal': 1, 'state_hash': 'same', 'audio_events': []}
        ])
    assert not completion.delivery(path)['complete']


def test_delivery_cannot_substitute_identical_but_unrelated_inputs(delivery):
    path, manifest, _ = delivery
    for role in ('simulation', 'render2d', 'render3d'):
        trace = path.parent / manifest[role]
        rows = read_rows(trace)
        rows[2]['buttons'] = ['DOWN']
        write_rows(trace, rows)
    assert not completion.delivery(path)['complete']


def test_delivery_requires_terminal_ending_on_all_render_targets(delivery):
    path, manifest, _ = delivery
    for role in ('simulation', 'render2d', 'render3d'):
        trace = path.parent / manifest[role]
        rows = read_rows(trace)
        rows[-1]['terminal'] = 0
        write_rows(trace, rows)
    assert not completion.delivery(path)['complete']


@pytest.mark.parametrize('field,value', [('state_hash', ''), ('audio_events', 'pickup')])
def test_delivery_rejects_empty_state_hash_or_nonlist_audio_on_all_targets(delivery, field, value):
    path, manifest, _ = delivery
    for role in ('simulation', 'render2d', 'render3d'):
        trace = path.parent / manifest[role]
        rows = read_rows(trace)
        rows[1][field] = value
        write_rows(trace, rows)
    assert not completion.delivery(path)['complete']


def test_delivery_route_reference_must_be_a_completed_clear_or_heldout_route(delivery):
    path, manifest, _ = delivery
    manifest['route_reference'] = 'death-recovery.reference.jsonl'
    path.write_text(json.dumps(manifest))
    assert not completion.delivery(path)['complete']


def test_delivery_route_reference_cannot_be_an_unlisted_copy(delivery):
    path, manifest, _ = delivery
    duplicate = path.parent / 'unlisted.reference.jsonl'
    duplicate.write_bytes((path.parent / manifest['route_reference']).read_bytes())
    manifest['route_reference'] = duplicate.name
    path.write_text(json.dumps(manifest))
    assert not completion.delivery(path)['complete']


@pytest.mark.parametrize('change', ['omit-enemy-field', 'loosen-position-bound', 'omit-route-case', 'shrink-level-scope'])
def test_gate_rejects_manifest_that_shrinks_or_loosens_pinned_reference_contract(tmp_path, evidence, change):
    led = ready_gate_ledger(tmp_path, evidence)
    pinned = led.read()['contract']
    if change == 'omit-enemy-field':
        change_manifest(evidence, lambda m: m['fields']['enemies'].pop('enemy_mode'))
    elif change == 'loosen-position-bound':
        change_manifest(evidence, lambda m: m['fields']['player'].update(player_x=3))
    elif change == 'omit-route-case':
        change_manifest(evidence, lambda m: m.update(cases=['clear', 'heldout']))
    else:
        state = led.read()
        state['contract']['levels'].append('two')
        led._write(state)
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', stage='gate',
                           status='passed', evidence=str(evidence), note=None)
    with pytest.raises(LedgerError, match='pinned reference contract'):
        cli.cmd_set(args)
    assert led.read()['stages']['gate']['status'] == 'pending'
    assert pinned['fields']['player']['player_x'] == 2


def test_gate_rejects_legacy_style_ledger_without_pinned_reference_contract(tmp_path, evidence):
    led = ready_gate_ledger(tmp_path, evidence)
    state = led.read()
    state.pop('contract')
    led._write(state)
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', stage='gate',
                           status='passed', evidence=str(evidence), note=None)
    with pytest.raises(LedgerError, match='verify must pin'):
        cli.cmd_set(args)
    assert led.read()['stages']['gate']['status'] == 'pending'


def test_noncharacter_game_can_complete_without_enemy_or_life_fields(evidence):
    manifest = json.loads(evidence.read_text())
    manifest['fields'] = {
        'player': {'piece_x': 0, 'piece_y': 0},
        'enemies': {},
        'rules': {'lines': 0},
        'outcome': {'terminal': 0},
    }
    manifest['not_applicable'] = {'enemies': 'Repeated controlled play shows falling pieces and no enemy entities.'}
    manifest['cases'] = ['clear', 'heldout']
    manifest['routes'] = [r for r in manifest['routes'] if r['kind'] in manifest['cases']]
    for route in manifest['routes']:
        for role in ('reference', 'rebuild', 'repeat'):
            trace = evidence.parent / route[role]
            write_rows(trace, [
                {'f': row['f'], 'buttons': row['buttons'], 'piece_x': row['player_x'],
                 'piece_y': row['player_y'], 'lines': row['f'], 'terminal': row['terminal']}
                for row in read_rows(trace)
            ])
    evidence.write_text(json.dumps(manifest))
    contract = {key: manifest[key] for key in ('fields', 'levels', 'cases', 'not_applicable')}
    contract.update(full_game=True, scope_basis='Finite challenge ending reached after the required line count.')
    report = completion.check(evidence, contract)
    assert report['complete']
    assert len(report['routes']) == 2


@pytest.fixture
def training_evidence(tmp_path):
    from compare import sha256
    checkpoint = tmp_path / 'policy.pt'
    checkpoint.write_bytes(b'test-trained-checkpoint')
    manifest = {'checkpoint': checkpoint.name, 'checkpoint_sha256': sha256(checkpoint), 'plays': []}
    for i, button in enumerate(('RIGHT', 'LEFT')):
        trace = tmp_path / f'policy-play-{i}.jsonl'
        write_rows(trace, [
            {'f': f, 'level': 'one' if f < 2 else 'two', 'buttons': [] if f == 0 else [button],
             'terminal': int(f == 3)}
            for f in range(4)
        ])
        manifest['plays'].append({'controller': 'trained-policy', 'trace': trace.name})
    path = tmp_path / 'training-evaluation.json'
    path.write_text(json.dumps(manifest))
    return path


def test_training_requires_two_complete_trained_policy_plays(training_evidence):
    report = completion.training(training_evidence, {'levels': ['one', 'two']})
    assert report == {'complete': True, 'problems': [], 'plays': 2}


@pytest.mark.parametrize('controller', ['search', 'replay'])
def test_training_cannot_be_satisfied_by_search_or_replay(training_evidence, controller):
    change_manifest(training_evidence, lambda m: m['plays'][0].update(controller=controller))
    report = completion.training(training_evidence, {'levels': ['one', 'two']})
    assert not report['complete']
    assert any('trained-policy' in p for p in report['problems'])


def test_training_rejects_single_policy_evaluation(training_evidence):
    change_manifest(training_evidence, lambda m: m['plays'].pop())
    report = completion.training(training_evidence, {'levels': ['one', 'two']})
    assert not report['complete']
    assert 'need at least two completed trained-policy evaluations' in report['problems']


def test_training_checks_checkpoint_identity(training_evidence):
    change_manifest(training_evidence, lambda m: m.update(checkpoint_sha256='0' * 64))
    report = completion.training(training_evidence, {'levels': ['one', 'two']})
    assert not report['complete']
    assert 'trained checkpoint hash mismatch' in report['problems']


def test_training_requires_every_declared_level(training_evidence):
    report = completion.training(training_evidence, {'levels': ['one', 'two', 'three']})
    assert not report['complete']
    assert 'trained policy did not visit every declared level/rule regime' in report['problems']


@pytest.mark.parametrize('defect', ['frame-gap', 'no-ending', 'no-inputs'])
def test_training_rejects_incomplete_policy_traces(training_evidence, defect):
    manifest = json.loads(training_evidence.read_text())
    trace = training_evidence.parent / manifest['plays'][0]['trace']
    rows = read_rows(trace)
    if defect == 'frame-gap':
        rows.pop(1)
    elif defect == 'no-ending':
        rows[-1]['terminal'] = 0
    else:
        rows[1].pop('buttons')
    write_rows(trace, rows)
    assert not completion.training(training_evidence, {'levels': ['one', 'two']})['complete']


def test_explore_stage_refuses_search_then_accepts_completed_policy_evaluations(tmp_path, evidence, training_evidence):
    manifest = json.loads(evidence.read_text())
    contract = {key: manifest[key] for key in ('fields', 'cases')}
    contract.update(full_game=True, scope_basis='Both observed stages end in a measured final terminal.',
                    levels=['one', 'two'])
    contract_path = tmp_path / 'training-contract.json'
    contract_path.write_text(json.dumps(contract))
    led = Ledger(tmp_path / 'training-reference/game/state.json')
    led.path.parent.mkdir(parents=True)
    led.create('game', 'recreate')
    led.set('intake', 'passed', 'ROM intake')
    led.set('reward', 'passed', 'Reward evidence')
    args = SimpleNamespace(reference_root=str(tmp_path / 'training-reference'), slug='game',
                           stage='verify', status='passed', evidence=str(contract_path), note=None)
    cli.cmd_set(args)
    valid = training_evidence.read_text()
    change_manifest(training_evidence, lambda m: m['plays'][0].update(controller='search'))
    args.stage, args.evidence = 'explore', str(training_evidence)
    with pytest.raises(LedgerError, match='policy training incomplete'):
        cli.cmd_set(args)
    assert led.read()['stages']['explore']['status'] == 'pending'
    training_evidence.write_text(valid)
    assert cli.cmd_set(args)['status'] == 'passed'
    assert led.read()['stages']['explore']['evidence'] == str(training_evidence)



def test_completion_tool_authenticates_complete_public_routes_against_private_oracle(tmp_path, evidence):
    ready_gate_ledger(tmp_path, evidence)
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', manifest=str(evidence))
    assert cli.cmd_completion(args)['complete']


@pytest.mark.parametrize('defect', ['no-log', 'different-private-values', 'spoofed-public-values'])
def test_matching_public_traces_cannot_pass_without_authentic_private_measurements(tmp_path, evidence, defect):
    led = ready_gate_ledger(tmp_path, evidence)
    oracle_log = led.path.parent / 'evidence/oracle/session/trace.jsonl'
    if defect == 'no-log':
        oracle_log.unlink()
    elif defect == 'different-private-values':
        rows = read_rows(oracle_log)
        for row in rows:
            row['enemy_x'] += 1
        write_rows(oracle_log, rows)
    else:
        manifest = json.loads(evidence.read_text())
        for route in manifest['routes']:
            for role in ('reference', 'rebuild', 'repeat'):
                trace = evidence.parent / route[role]
                rows = read_rows(trace)
                for row in rows:
                    row['enemy_x'] += 100
                write_rows(trace, rows)
    assert completion.check(evidence)['complete']
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', manifest=str(evidence),
                           stage='gate', status='passed', evidence=str(evidence), note=None)
    report = cli.cmd_completion(args)
    assert not report['complete']
    assert any('not a recorded private oracle playthrough' in p for p in report['problems'])
    with pytest.raises(LedgerError, match='not a recorded private oracle playthrough'):
        cli.cmd_set(args)
    assert led.read()['stages']['gate']['status'] == 'pending'


def test_visual_delivery_reauthenticates_reference_before_passing(tmp_path, evidence, delivery):
    led = ready_gate_ledger(tmp_path, evidence)
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', stage='gate',
                           status='passed', evidence=str(evidence), note=None)
    cli.cmd_set(args)
    (led.path.parent / 'evidence/oracle/session/trace.jsonl').unlink()
    args.stage, args.evidence = 'visual3d', str(delivery[0])
    with pytest.raises(LedgerError, match='not a recorded private oracle playthrough'):
        cli.cmd_set(args)
    assert led.read()['stages']['visual3d']['status'] == 'pending'


def test_private_reference_authentication_requires_actual_repeated_native_runs(tmp_path, evidence):
    led = ready_gate_ledger(tmp_path, evidence)
    manifest = json.loads(evidence.read_text())
    oracle_log = led.path.parent / 'evidence/oracle/session/trace.jsonl'
    write_rows(oracle_log, [
        row for route in manifest['routes']
        for row in read_rows(evidence.parent / route['reference'])
    ])
    args = SimpleNamespace(reference_root=str(tmp_path / 'reference'), slug='game', manifest=str(evidence))
    assert not cli.cmd_completion(args)['complete']
