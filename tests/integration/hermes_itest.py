"""End-to-end check of the installed plugin through real Hermes discovery and tool dispatch.

Needs: Hermes with this plugin linked and enabled, its settings pointing reference_root and builder_root at
TESTDIR/ref and TESTDIR/bld, and a runtime Python with stable-retro, numpy, Pillow, torch and pytest.
Uses a cartridge generated here, so no game file is needed. Runs on the CPU; compiles the CPU emulator.

usage (from the Hermes checkout): scripts/run-in-hermes-env python3 tests/integration/hermes_itest.py TESTDIR RUNTIME_PYTHON
"""
import json, os, shutil, subprocess, sys, time, hashlib, queue
from pathlib import Path
P=Path(__file__).resolve().parents[2]; T=Path(sys.argv[1]); T.mkdir(parents=True, exist_ok=True); PY=sys.argv[2]
from hermes_cli.plugins import discover_plugins, get_plugin_manager, get_plugin_command_handler
from model_tools import handle_function_call as call
from tools.registry import registry
discover_plugins(force=True)
results=[]
def check(name, ok, detail=''):
    results.append((name, bool(ok))); print(('PASS ' if ok else 'FAIL ')+name+('  '+str(detail)[:300] if (detail!='' and not ok) else ''),flush=True)
def tool(name,args,task):
    out=call(name,args,task_id=task); 
    try: return json.loads(out)
    except Exception: return {'raw':out}
names=[n for n in registry.get_all_tool_names() if n.startswith('ghostrun_')]
check('real registry has 28 tools',len(names)==28,names)
R='ref1'; B='bld1'; ref=T/'ref'; 
r=tool('ghostrun_status',{'slug':'none'},'x'); check('status of unknown game returns error',('error' in r),r)
rom=T/'t.nes'; subprocess.run([sys.executable,P/'tests/fixtures/make_test_rom.py',rom],check=True)
r=tool('ghostrun_init',{'slug':'tg','rom':str(rom)},'unassigned'); check('hook blocks reference tool for unassigned task','reference sessions' in json.dumps(r),r)
r=tool('ghostrun_reference_enter',{},R); check('reference_enter received task id',r.get('role')=='reference',r)
r=tool('ghostrun_init',{'slug':'tg','rom':str(rom)},R); check('init',r.get('next')=='reward',r)
r=tool('ghostrun_init',{'slug':'fa','rom':str(rom),'mode':'faithful'},R); check('faithful refused without rights','rights' in json.dumps(r),r)
digest=hashlib.sha256(rom.read_bytes()).hexdigest()
mod=ref/'tg/games/tg.py'; mod.write_text((P/'tests/fixtures/testgame.py').read_text().replace("'0' * 64",repr(digest)))
r=tool('ghostrun_reward_check',{'slug':'tg'},R); check('reward_check',r.get('exit_code')==0 and '1 games' in r.get('stdout',''),r)
r=tool('ghostrun_reward_audit',{'slug':'tg','episodes':2},R); check('reward_audit',r.get('exit_code')==0,r)
r=tool('ghostrun_reward_lint',{'slug':'tg'},R); check('reward_lint catches wrap',r.get('clean') is False and 'jumped' in json.dumps(r),r)
r=tool('ghostrun_reward_balance',{'slug':'tg'},R); check('reward_balance',r.get('exit_code')==0 and '"problem": null' in r.get('stdout',''),r)
r=tool('ghostrun_reward_search',{'slug':'tg','seconds':5},R); check('reward_search',r.get('exit_code')==0,r)
r=tool('ghostrun_stage_set',{'slug':'tg','stage':'verify','status':'passed','evidence':'e'},R); check('ledger refuses skipping a stage','has not passed' in json.dumps(r),r)
r=tool('ghostrun_stage_set',{'slug':'tg','stage':'reward','status':'passed','evidence':'module'},R); check('stage_set',r.get('status')=='passed',r)
out=get_plugin_command_handler('ghostrun')('tg'); check('/ghostrun command','reward' in out and 'passed' in out,out)
for s in ('pipeline','reward-discovery','gpu-env-port','training-doctor','rebuild-from-oracle','visual-upgrade'):
    r=tool('skill_view',{'name':f'ghostrun:{s}'},R); check(f'skill {s}',r.get('success') and len(r.get('content',''))>300,r)
# oracle and builder
r=tool('ghostrun_oracle_start',{'slug':'tg'},'unassigned'); check('hook blocks oracle_start for unassigned','reference sessions' in json.dumps(r),r)
r=tool('ghostrun_oracle_start',{'slug':'tg'},R); check('oracle_start',r.get('started'),r)
r=tool('ghostrun_builder_enter',{'slug':'tg'},B); check('builder_enter',r.get('role')=='builder',r)
for _ in range(100):
    r=tool('ghostrun_oracle_call',{'slug':'tg','op':'hello'},B)
    if r.get('ok'): break
    time.sleep(.2)
check('oracle hello via tool',r.get('ok'),r)
tool('ghostrun_oracle_call',{'slug':'tg','op':'reset'},B)
r=tool('ghostrun_oracle_call',{'slug':'tg','op':'step','fields':json.dumps({'buttons':['RIGHT'],'frames':20,'image':True})},B); check('oracle step moves and saves frame',r.get('observables')=={'x':20} and Path(r.get('image_path','/x')).exists(),r)
r=tool('ghostrun_oracle_call',{'slug':'tg','op':'ram'},B); check('oracle refuses ram','unknown op' in json.dumps(r),r)
r=tool('ghostrun_reference_enter',{},B); check('builder cannot become reference','error' in r,r)
for n,a in (('read_file',{'path':str(ref/'tg/game.nes')}),('terminal',{'command':'ls '+str(ref)}),('terminal',{'command':'find / -name "*.nes"'}),('ghostrun_train_start',{'slug':'tg'}),('ghostrun_oracle_stop',{'slug':'tg'})):
    r=call(n,a,task_id=B); check(f'hook blocks builder: {n} {list(a.values())[0][:30]}','no access' in r or 'reference sessions' in r,r)
tr=T/'bld/tg/traces'; tr.mkdir(parents=True,exist_ok=True)
(tr/'ref.jsonl').write_text('{"f":0,"x":0}\n{"f":1,"x":10}\n'); (tr/'good.jsonl').write_text('{"f":0,"x":0}\n{"f":1,"x":11}\n'); (tr/'bad.jsonl').write_text('{"f":0,"x":0}\n{"f":1,"x":40}\n'); (tr/'tol.json').write_text('{"x":{"near":3,"far":8}}')
A={'slug':'tg','reference':str(tr/'ref.jsonl'),'tolerances':str(tr/'tol.json')}
r=tool('ghostrun_compare',{**A,'rebuild':str(tr/'bad.jsonl')},B); check('compare first divergence',r.get('first_divergence',{}).get('frame')==1,r)
r=tool('ghostrun_gate',{**A,'rebuild':str(tr/'good.jsonl')},B); check('gate without baseline FAILs',r.get('verdict')=='FAIL',r)
r=tool('ghostrun_gate',{**A,'rebuild':str(tr/'good.jsonl'),'save_baseline':True},B); check('gate saves baseline','saved' in r,r)
r=tool('ghostrun_gate',{**A,'rebuild':str(tr/'good.jsonl')},B); check('gate PASS',r.get('verdict')=='PASS',r)
r=tool('ghostrun_gate',{**A,'rebuild':str(tr/'bad.jsonl')},B); check('gate REGRESSION',r.get('verdict')=='REGRESSION',r)
r=tool('ghostrun_isolation_check',{'slug':'tg'},B); check('isolation clean',r.get('isolated'),r)
(T/'bld/tg/x.nes').write_bytes(b'x'); r=tool('ghostrun_isolation_check',{'slug':'tg'},B); check('isolation catches ROM',r.get('isolated') is False,r); (T/'bld/tg/x.nes').unlink()
sock=json.loads((T/'bld/tg/.oracle.json').read_text())['socket']
r=tool('ghostrun_oracle_stop',{'slug':'tg'},R); check('oracle_stop',r.get('stopped'),r)
for _ in range(50):
    if not Path(sock).exists(): break
    time.sleep(.1)
check('oracle removed its socket',not Path(sock).exists())
r=tool('ghostrun_assets_import',{'slug':'tg','source':str(T)},R); check('assets refused in mechanics mode','mechanics' in json.dumps(r),r)
r=tool('ghostrun_init',{'slug':'ok','rom':str(rom),'mode':'faithful','rights':json.dumps({'basis':'open-license','license':'zlib','source':'u'})},R); check('faithful with rights',r.get('mode')=='faithful',r)
a=T/'assets'; shutil.rmtree(a, ignore_errors=True); a.mkdir(); r=tool('ghostrun_assets_import',{'slug':'ok','source':str(a)},R); check('assets need manifest','manifest' in json.dumps(r),r)
(a/'manifest.json').write_text('{}'); r=tool('ghostrun_assets_import',{'slug':'ok','source':str(a)},R); check('assets import',r.get('files')==1,r)
# engine
r=tool('ghostrun_engine_setup',{'slug':'tg','boot_frames':10},R); check('engine_setup',('engine' in r),r)
eng=ref/'tg/engine'; cuh=eng/'rl/csrc/reward10.cuh'; s=cuh.read_text()
s=s.replace('RL10_HD Signals observe(int game,','RL10_HD Signals observe_tg(const std::uint8_t* r) {\n    Signals s = blank();\n    s.in_play = true;\n    s.level = 0;\n    s.progress = static_cast<double>(u8(r, 0x10));\n    s.progress_valid = true;\n    return s;\n}\n\nRL10_HD Signals observe(int game,',1).replace('        default: return observe_punchout(r, e);','        case kGame_tg: return observe_tg(r);\n        default: return observe_punchout(r, e);',1); cuh.write_text(s)
r=tool('ghostrun_engine_parity',{'slug':'tg'},R); check('engine_parity on real port',r.get('parity'),r)
r=tool('ghostrun_train_start',{'slug':'tg'},R); busy=bool(subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True).stdout.strip()); check('train refuses busy GPU','GPU is in use' in json.dumps(r) if busy else True,r)
CPU='--device cpu --envs-per-game 1 --steps 8 --minibatch-envs 4 --epochs 1 --eval-every-minutes 0 --total-iters 3'
r=tool('ghostrun_train_start',{'slug':'tg','args':CPU},R); check('train_start real CPU run',r.get('pid'),r); run=Path(r.get('run','/x'))
for _ in range(400):
    if (run/'metrics.jsonl').exists() and len((run/'metrics.jsonl').read_text().splitlines())>=3: break
    if (run/'stdout.log').exists() and 'Traceback' in (run/'stdout.log').read_text(): break
    time.sleep(1)
n=len((run/'metrics.jsonl').read_text().splitlines()) if (run/'metrics.jsonl').exists() else 0; check('real trainer wrote metrics',n>=3,(run/'stdout.log').read_text()[-1500:])
for _ in range(120):
    pid=int((run/'pid').read_text())
    try:
        if Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]=='Z': break
    except OSError: break
    time.sleep(1)
r=tool('ghostrun_train_check',{'slug':'tg'},R); check('train_check after clean finish',r.get('iteration') is not None and 'trainer_stopped' not in json.dumps(r),r)
# watcher wakes agent through the real inject path
mgr=get_plugin_manager()
class Cli: _agent_running=False; _pending_input=queue.Queue(); _interrupt_queue=queue.Queue()
mgr._cli_ref=Cli
with open(run/'metrics.jsonl','a') as f: f.write(json.dumps({'it':99,'time':time.time(),'decisions':9,'pg':0.0,'v':1.0,'ent':1.0,'kl':float('nan'),'gnorm':1.0,'explained_var':.5,'sps':1.0,'games':{}})+'\n')
r=tool('ghostrun_watch_start',{'slug':'tg','minutes':0.02},R); check('watch_start',r.get('watching')=='tg',r)
msg=None
for _ in range(60):
    try: msg=Cli._pending_input.get(timeout=1); break
    except queue.Empty: pass
check('watcher injected wake message',msg and 'training-doctor' in msg and 'non_finite' in msg,msg)
r=tool('ghostrun_watch_stop',{'slug':'tg'},R); check('watch_stop',r.get('stopped'),r); mgr._cli_ref=None
# fix loop
r=tool('ghostrun_fix_validate',{'slug':'tg'},R); check('validate refused with no open fix','no open fix' in json.dumps(r),r)
r=tool('ghostrun_fix_begin',{'slug':'tg','finding':'non_finite','hypothesis':'wrap at 255'},R); check('fix_begin',r.get('open'),r)
mod.write_text(mod.read_text()+'# no-op change\n')
r=tool('ghostrun_fix_validate',{'slug':'tg'},R); check('validate fails while bug remains',r.get('passed') is False and r['checks']['lint']['ok'] is False,r)
r=tool('ghostrun_fix_apply',{'slug':'tg'},R); check('apply refused when not validated','not validated' in json.dumps(r),r)
mod.write_text(mod.read_text().replace("progress=float(r[0x10]))","progress=float(r[0x10]), progress_valid=int(r[0x10]) < 200)"))
s=cuh.read_text().replace('    s.progress = static_cast<double>(u8(r, 0x10));\n    s.progress_valid = true;','    s.progress = static_cast<double>(u8(r, 0x10));\n    s.progress_valid = u8(r, 0x10) < 200;',1); cuh.write_text(s)
r=tool('ghostrun_fix_validate',{'slug':'tg'},R); check('validate passes after real fix',r.get('passed'),r)
r=tool('ghostrun_fix_apply',{'slug':'tg'},R); check('fix_apply restarts as v2',r.get('version')==2,r); run2=Path(r.get('run','/x'))
for _ in range(300):
    if (run2/'metrics.jsonl').exists() and len((run2/'metrics.jsonl').read_text().splitlines())>=1: break
    if (run2/'stdout.log').exists() and 'Traceback' in (run2/'stdout.log').read_text(): break
    time.sleep(1)
check('v2 run trains',(run2/'metrics.jsonl').exists(),(run2/'stdout.log').read_text()[-1200:] if (run2/'stdout.log').exists() else '')
r=tool('ghostrun_fix_review',{'slug':'tg'},R); check('fix_review waits for test plays',r.get('verdict')=='wait',r)
r=tool('ghostrun_train_stop',{'slug':'tg'},R); check('train_stop',r.get('stopped'),r)

fails = [n for n, ok in results if not ok]
print(f'\n{len(results) - len(fails)}/{len(results)} passed')
print('FAILED:', fails)
sys.exit(1 if fails else 0)
