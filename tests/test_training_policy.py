"""Production must use the supplied recipe and prove its own throughput."""
import ast
import json
from pathlib import Path

import pytest

import train_ctl as tc
import training_policy as p
from test_train_ctl import game

GPU = {'uuid':'gpu-test', 'name':'NVIDIA GeForce RTX 5090', 'memory_mib':32607}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    ref, g = game(tmp_path)
    monkeypatch.setattr(p, 'hardware', lambda: dict(GPU))
    monkeypatch.setattr(tc, 'gpu_other_users', lambda *_: [])
    calls = []
    def launch(game, state, python, args, restart_from=None, training_policy=None):
        run = game.run_dir(state['version'])
        run.mkdir(parents=True, exist_ok=True)
        state.update(run=str(run), args=args, pid=None, training_policy=training_policy)
        game.save(state)
        (run/'training-policy.json').write_text(json.dumps(training_policy))
        (run/'stdout.log').write_text('')
        calls.append((args,restart_from,training_policy))
        return {'run':str(run),'version':state['version'],'training_policy':training_policy}
    monkeypatch.setattr(tc, 'launch', launch)
    return ref, g, calls


def finish(run, speeds=(1000,9200,9400), memory=20):
    run = Path(run)
    (run/'metrics.jsonl').write_text(''.join(json.dumps({'it':i+1,'sps':s,'mem_gb':memory})+'\n' for i,s in enumerate(speeds)))
    (run/'ckpt_rank0_latest.pt').write_bytes(b'owned checkpoint')
    (run/'CLEAN_EXIT').write_text(str(len(speeds)))


def test_frozen_mario_recipe_is_explicit_and_matches_the_engine():
    settings, changed = p.parse([])
    assert (settings['core'],settings['moods'],settings['envs_per_game'],settings['compile']) == (512,8,8192,1)
    assert (settings['steps'],settings['minibatch_envs'],settings['gamma'],settings['lam']) == (64,32,.995,.98)
    assert settings['div_coef'] == .001 and settings['ret_beta'] == .98
    assert changed == {}
    tree = ast.parse((tc.ENGINE/'rl/train.py').read_text())
    config = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Config')
    assert set(settings) <= {n.target.id for n in config.body if isinstance(n,ast.AnnAssign)}
    assert p.digest(tc.ENGINE/'rl/model.py') == p.BASELINE['model_sha256']
    assert 'only_levels' not in settings and 'games' not in settings


@pytest.mark.parametrize('args', [
    ['--core','0'], ['--envs-per-game','0'], ['--run','elsewhere'],
    ['--restart-from','old.pt'], ['--games','another'], ['--envs','128'], ['--lr','nan']])
def test_invalid_numeric_and_ownership_overrides_are_rejected(args):
    with pytest.raises(p.PolicyError):
        p.parse(args)


def test_explicit_custom_recipe_is_allowed_and_disclosed_without_approval(runtime):
    ref,g,_=runtime
    result=tc.start(ref,'g','python3',['--core','256','--moods','0','--steps','16'],
                    recipe_note='User explicitly requested this smaller experiment.')
    plan=result['training_policy']
    assert plan['recipe']=='custom' and plan['settings']['core']==256
    assert plan['adjustments']['moods']=={'baseline':8,'requested':0}
    assert 'Explain the differences' in plan['notice'] and 'User explicitly' in plan['recipe_note']
    finish(result['run'])
    continued=tc.start(ref,'g','python3',['--core','256','--moods','0','--steps','16','--time-limit','1200'])
    assert continued['training_policy']['phase']=='production'
    assert continued['training_policy']['recipe_note']==plan['recipe_note']
    resumed=tc.start(ref,'g','python3',[])
    assert resumed['training_policy']['recipe']=='custom' and resumed['version']==continued['version']
    assert resumed['training_policy']['settings']['core']==256


def test_default_start_is_bounded_then_real_metrics_qualify_same_configuration(runtime):
    ref,g,calls = runtime
    first = tc.start(ref,'g','python3',['--time-limit','1200'])
    plan = first['training_policy']
    assert plan['phase']=='preflight' and plan['settings']['core']==512 and plan['settings']['moods']==8
    assert plan['settings']['total_iters']==3 and plan['settings']['time_limit']==180
    assert '--envs-per-game' in calls[-1][0] and '8192' in calls[-1][0]
    finish(first['run'])
    second = tc.start(ref,'g','python3',['--time-limit','1200'])
    assert second['version']==first['version']
    assert second['training_policy']['phase']=='production'
    assert second['training_policy']['settings']['time_limit']==1200
    assert second['training_policy']['settings']['total_iters']==0
    assert second['training_policy']['throughput']['steady_decisions_per_second']==9300
    assert calls[-1][1] is None  # Exact resume keeps the optimizer, not a weights-only restart.


def test_metrics_are_required_not_just_a_claim_or_checkpoint(runtime):
    ref,g,_ = runtime
    first = tc.start(ref,'g','python3',[])
    finish(first['run'], speeds=(0,9200))
    assert tc.start(ref,'g','python3',[])['training_policy']['phase']=='preflight'
    finish(first['run'], speeds=(1000,float('nan'),9400))
    retried=tc.start(ref,'g','python3',[])
    assert retried['version']==2 and retried['training_policy']['phase']=='preflight'
    assert 'valid measured throughput' in retried['reason']


@pytest.mark.parametrize('extra', [{'games':{'g':{'n':1,'level_mean':0,'level_max':0,'ret':0,'len':1,'ends':{'fault':1}}}}, {'kl':float('nan')}])
def test_failed_environment_or_nonfinite_learning_does_not_qualify(runtime,extra):
    ref,g,_=runtime
    first=tc.start(ref,'g','python3',[]);finish(first['run'])
    path=Path(first['run'])/'metrics.jsonl'
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    rows[1].update(extra)
    path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    assert 'preflight_failed' in [f['code'] for f in tc.check(ref,'g')['findings']]
    retry=tc.start(ref,'g','python3',[])
    assert retry['version']==2 and retry['training_policy']['phase']=='preflight'
    assert retry['restarted_from'] is None
    assert path.exists() and not (Path(retry['run'])/'metrics.jsonl').exists()
    assert tc.start(ref,'g','python3',[])['training_policy']['phase']=='preflight'


def test_preflight_from_other_hardware_cannot_qualify(runtime,monkeypatch):
    ref,g,_=runtime
    first=tc.start(ref,'g','python3',[])
    finish(first['run'])
    monkeypatch.setattr(p,'hardware',lambda:{**GPU,'uuid':'different'})
    second=tc.start(ref,'g','python3',[])
    assert second['version']==2 and second['training_policy']['phase']=='preflight'
    assert Path(first['run'])!=Path(second['run'])
    assert not (Path(second['run'])/'metrics.jsonl').exists()
    assert tc.start(ref,'g','python3',[])['training_policy']['phase']=='preflight'


def test_uncheckpointed_preflight_retry_retains_its_original_restart_weights(runtime,monkeypatch):
    ref,g,calls=runtime
    first=tc.start(ref,'g','python3',[]);finish(first['run'])
    monkeypatch.setattr(p,'hardware',lambda:{**GPU,'uuid':'different'})
    changed=tc.start(ref,'g','python3',[])
    source=Path(first['run'])/'ckpt_rank0_latest.pt'
    assert calls[-1][1]==source
    assert not (Path(changed['run'])/'ckpt_rank0_latest.pt').exists()
    retried=tc.start(ref,'g','python3',[])
    assert retried['version']==changed['version']
    assert Path(calls[-1][1])==source
    assert retried['training_policy']['restart_from']==str(source)


def test_small_smoke_model_never_becomes_production_or_seeds_baseline(runtime):
    ref,g,calls=runtime
    smoke=tc.start(ref,'g','python3',['--device','cpu','--core','64','--moods','0','--steps','8','--total-iters','9999'],smoke=True)
    assert smoke['training_policy']['phase']=='smoke'
    assert smoke['training_policy']['settings']['total_iters']==3
    finish(smoke['run'],speeds=(1000,10000,10000))
    old=Path(smoke['run'])/'ckpt_rank0_latest.pt'
    baseline=tc.start(ref,'g','python3',[])
    assert baseline['version']==2 and baseline['training_policy']['phase']=='preflight'
    assert calls[-1][1] is None and old.read_bytes()==b'owned checkpoint'


def test_measured_resource_adjustment_is_recorded_and_retested(runtime,tmp_path):
    ref,g,calls=runtime
    first=tc.start(ref,'g','python3',[])
    run=Path(first['run'])
    finish(run,memory=20)
    (run/'stdout.log').write_text('torch.OutOfMemoryError: CUDA out of memory')
    adjusted=tc.start(ref,'g','python3',['--envs-per-game','4096'],adjustment_evidence=str(run))
    assert adjusted['version']==2 and calls[-1][1]==run/'ckpt_rank0_latest.pt'
    assert adjusted['training_policy']['phase']=='preflight'
    assert adjusted['training_policy']['settings']['steps']==64
    assert adjusted['training_policy']['adjustment_evidence']['out_of_memory']
    assert adjusted['training_policy']['adjustments']['envs_per_game']=={'baseline':8192,'requested':4096}
    finish(adjusted['run'])
    assert tc.start(ref,'g','python3',['--envs-per-game','4096'])['training_policy']['phase']=='production'


def test_custom_model_source_is_disclosed_and_cannot_reuse_old_throughput(runtime):
    ref,g,calls=runtime
    first=tc.start(ref,'g','python3',[]);finish(first['run'])
    (g.engine/'rl/model.py').write_text('different architecture')
    changed=tc.start(ref,'g','python3',[],recipe_note='Requested alternative model source')
    assert changed['version']==2 and changed['training_policy']['phase']=='preflight'
    assert 'model_source' in changed['training_policy']['adjustments']
    assert calls[-1][1] is None


def test_legacy_checkpoint_is_preserved_but_not_loaded_into_new_architecture(runtime):
    ref,g,calls=runtime
    run=g.run_dir(3);run.mkdir(parents=True)
    old=run/'ckpt_rank0_latest.pt';old.write_bytes(b'old core256 weights')
    state=g.state;state.update(version=3,run=str(run),args=['--core','256'],fixes_used=1);g.save(state)
    result=tc.start(ref,'g','python3',[])
    assert result['version']==4 and calls[-1][1] is None
    assert old.read_bytes()==b'old core256 weights' and g.state['fixes_used']==1
    assert g.state['history'][0]['run']==str(run)


def test_live_owned_run_is_never_stopped_or_reconfigured(runtime,monkeypatch):
    ref,g,calls=runtime
    state=g.state;state.update(pid=12345);g.save(state)
    monkeypatch.setattr(tc.watch,'alive',lambda _:True)
    before=g.state_path.read_bytes()
    with pytest.raises(tc.TrainError,match='already running'):
        tc.start(ref,'g','python3',[])
    assert not calls and g.state_path.read_bytes()==before


def test_preflight_ready_wakes_agent_to_continue_under_the_original_requested_budget(runtime):
    ref,g,_=runtime
    first=tc.start(ref,'g','python3',['--time-limit','1200'])
    finish(first['run'])
    result=tc.check(ref,'g')
    assert result['verdict']=='act' and 'preflight_ready' in [f['code'] for f in result['findings']]
    assert result['throughput']['steady_decisions_per_second']==9300


def test_actual_baseline_parameter_count_on_cpu(monkeypatch):
    torch=pytest.importorskip('torch')
    import importlib.util
    monkeypatch.syspath_prepend(str(tc.ENGINE/'rl'))
    spec=importlib.util.spec_from_file_location('baseline_policy_model',tc.ENGINE/'rl/model.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.Policy(core=512,moods=8)
    assert sum(x.numel() for x in model.parameters())==p.BASELINE['parameters']


@pytest.mark.parametrize('promote',[False,True])
def test_reward_fix_keeps_requested_budget_and_weights_while_remeasuring(runtime,promote):
    ref,g,calls=runtime
    first=tc.start(ref,'g','python3',['--time-limit','1200'])
    finish(first['run'])
    if promote:
        tc.start(ref,'g','python3',['--time-limit','1200'])
    tc.fix_begin(ref,'g','decoder','measured edge')
    g.module.write_text('A = 2\n')
    state=g.state;state['pending_fix']['validated']=tc.sha(g.module);g.save(state)
    fixed=tc.fix_apply(ref,'g','python3')
    plan=fixed['training_policy']
    requested,_=p.parse(plan['requested_args'])
    assert requested['time_limit']==1200 and requested['total_iters']==0
    assert plan['settings']['time_limit']==180 and plan['settings']['total_iters']==3
    assert calls[-1][1]==Path(first['run'])/'ckpt_rank0_latest.pt'
    assert plan['restart_from']==str(Path(first['run'])/'ckpt_rank0_latest.pt')
