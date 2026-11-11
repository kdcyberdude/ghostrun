"""Hermes plugin entry. Stays thin: each tool is one call to core/cli.py, which holds the logic and the durable state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

PLUGIN = 'ghostrun'
HERE = Path(__file__).resolve().parent
CLI = HERE / 'core' / 'cli.py'
TOOLSET = PLUGIN
SKILLS = HERE / 'skills'
DEFAULT_TIMEOUT = 3600

SLUG = {'type': 'string', 'description': 'Short lowercase id of the game, for example thwaite.'}


def S(**props):
    """An object schema in which 'slug' and every property without a default are required."""
    required = [k for k, v in props.items() if 'default' not in v]
    return {'type': 'object', 'properties': {k: {x: y for x, y in v.items() if x != 'default'} for k, v in props.items()},
            'required': required}


def text(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def number(description, **extra):
    return {'type': 'number', 'description': description, **extra}


# name: (command, description, properties, flag map). Flags map tool arguments to CLI options.
REFERENCE_TOOLS = {
    'ghostrun_init': ('init', 'Start a game: copy the ROM into the private reference folder and create its stage ledger. '
                      'Before the first call, load skill_view("ghostrun:pipeline") and follow it. '
                      'mode is mechanics (new art and levels) or faithful (needs rights).',
                      dict(slug=SLUG, rom=text('Path to a ROM you have the right to use.'),
                           mode=text('mechanics or faithful.', default='mechanics'),
                           rights=text("JSON such as {'basis':'open-license','license':'GPL-3.0','source':'<url>'}.", default=None)),
                      {'rom': '--rom', 'mode': '--mode', 'rights': '--rights'}),
    'ghostrun_reward_check': ('reward-check', 'Check every reward module against the contract.', dict(slug=SLUG), {}),
    'ghostrun_reward_audit': ('audit', 'Random play with contact sheets of every reward event.',
                              dict(slug=SLUG, episodes=number('Episodes.', default=12)), {'episodes': '--episodes'}),
    'ghostrun_reward_lint': ('lint', 'Flag impossible rewards, such as one step paying most of a level.', dict(slug=SLUG), {}),
    'ghostrun_reward_balance': ('balance', 'Scripted players: does standing still out-earn moving?', dict(slug=SLUG), {}),
    'ghostrun_reward_search': ('search', 'Go-Explore search guided only by the reward, to prove it points forward.',
                               dict(slug=SLUG, seconds=number('Time budget.', default=300)), {'seconds': '--seconds'}),
    'ghostrun_engine_setup': ('engine-setup', 'Prepare the CUDA NES environment for this game. Clones NeSLE at a pinned commit.',
                              dict(slug=SLUG, boot_frames=number('Frames from power-on to first control.')),
                              {'boot_frames': '--boot-frames'}),
    'ghostrun_engine_parity': ('parity', 'Prove the CUDA reward equals the Python reward, bit for bit.', dict(slug=SLUG), {}),
    'ghostrun_train_start': ('train-start', 'Start GPU training in the background. Refuses a GPU that is already in use.',
                             dict(slug=SLUG, args=text('Extra rl/train.py arguments.', default=None),
                                  share_gpu={'type': 'boolean', 'description': 'Train even though another process uses the GPU. Only if the user agreed.', 'default': None}),
                             {'args': '--args', 'share_gpu': '--share-gpu'}),
    'ghostrun_train_stop': ('train-stop', 'Stop training gracefully, writing a checkpoint first.', dict(slug=SLUG), {}),
    'ghostrun_train_check': ('watch', 'Check training health now: healthy, watch or act, with evidence. '
                             'On act, load skill_view("ghostrun:training-doctor").', dict(slug=SLUG), {}),
    'ghostrun_fix_begin': ('fix-begin', 'Open a reward fix for a finding. Limited by a budget.',
                           dict(slug=SLUG, finding=text('Finding code.'), hypothesis=text('Suspected cause.')),
                           {'finding': '--finding', 'hypothesis': '--hypothesis'}),
    'ghostrun_fix_validate': ('fix-validate', 'Run contract, audit, lint, balance and CUDA parity on the edited reward.', dict(slug=SLUG), {}),
    'ghostrun_fix_apply': ('fix-apply', 'Stop training and start a new run on the validated reward from the best measured weights.', dict(slug=SLUG), {}),
    'ghostrun_fix_review': ('fix-review', 'Judge an applied fix using test plays only.', dict(slug=SLUG), {}),
    'ghostrun_assets_import': ('import-assets', 'Faithful mode only: copy a prepared, licensed asset folder into the builder.',
                               dict(slug=SLUG, source=text('Folder with a manifest.json.')), {'source': '--source'}),
}
SHARED_TOOLS = {
    'ghostrun_status': ('status', 'Show the stage ledger for a game and the next stage. Call first in every session. '
                        'The pipeline is in skill_view("ghostrun:pipeline").', dict(slug=SLUG), {}),
    'ghostrun_stage_set': ('set', 'Record a stage result. A pass needs evidence and every earlier stage passed.',
                           dict(slug=SLUG, stage=text('Stage name.'), status=text('pending, running, passed, failed or blocked.'),
                                evidence=text('What proves it.', default=None), note=text('Note.', default=None)),
                           {'evidence': '--evidence', 'note': '--note'}),
    'ghostrun_isolation_check': ('isolation', 'Check that the builder folder has no route to the reference.', dict(slug=SLUG), {}),
    'ghostrun_compare': ('compare', 'Compare a rebuild trace to a reference trace. Reports the first divergence.',
                         dict(slug=SLUG, reference=text('Reference trace.'), rebuild=text('Rebuild trace.'),
                              tolerances=text('JSON tolerances file.')),
                         {'reference': '--reference', 'rebuild': '--rebuild', 'tolerances': '--tolerances'}),
    'ghostrun_gate': ('gate', 'Regression gate: PASS, REGRESSION or FAIL against the saved baseline.',
                      dict(slug=SLUG, reference=text('Reference trace.'), rebuild=text('Rebuild trace.'),
                           tolerances=text('JSON tolerances file.'),
                           save_baseline={'type': 'boolean', 'description': 'Save this result as the baseline. Only after an accepted change.', 'default': None}),
                      {'reference': '--reference', 'rebuild': '--rebuild', 'tolerances': '--tolerances', 'save_baseline': '--save-baseline'}),
}
POSITIONAL = {'set': ('stage', 'status')}

def clean_env():
    """The game runtime is a different Python: Hermes's own package paths must not leak into it."""
    return {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}


def build_argv(command, flags, args):
    """Turn tool arguments into the CLI's argument list."""
    argv = [command, args['slug'], *[str(args[k]) for k in POSITIONAL.get(command, ())]]
    for key, flag in flags.items():
        value = args.get(key)
        if isinstance(value, bool):
            argv += [flag] if value else []
        elif value is not None:
            argv += [flag, str(int(value) if isinstance(value, float) else value)]
    return argv


class Plugin:
    def __init__(self, ctx):
        self.ctx = ctx
        self.reference_tasks, self.builder_tasks = set(), set()
        self.watchers, self.oracles = {}, {}

    # ---- configuration ----
    def data_dir(self):
        try:
            from plugins.plugin_storage import plugin_data_dir
            return Path(plugin_data_dir(PLUGIN))
        except ImportError:
            return Path.home() / '.local' / 'share' / PLUGIN

    def setting(self, key, default):
        return self.ctx.get_config(key, default) or default

    def reference_root(self):
        return str(Path(self.setting('reference_root', self.data_dir() / 'reference')).expanduser())

    def builder_root(self):
        return str(Path(self.setting('builder_root', Path.home() / 'ghostrun-projects')).expanduser())

    def python(self):
        return str(self.setting('python', sys.executable))

    def base_argv(self):
        return [sys.executable, str(CLI), '--reference-root', self.reference_root(), '--builder-root', self.builder_root(),
                '--python', self.python()]

    def run_cli(self, argv, timeout=DEFAULT_TIMEOUT):
        try:
            p = subprocess.run([*self.base_argv(), *argv], capture_output=True, text=True, timeout=timeout, env=clean_env())
        except subprocess.TimeoutExpired:
            return json.dumps({'error': f'{argv[0]} timed out after {timeout} s'})
        return p.stdout.strip() or json.dumps({'error': p.stderr[-2000:] or 'no output'})

    # ---- tools ----
    def cli_handler(self, command, flags):
        def handler(args, **_):
            try:
                return self.run_cli(build_argv(command, flags, args))
            except (KeyError, OSError) as e:
                return json.dumps({'error': str(e)})
        return handler

    def reference_enter(self, args, task_id='', **_):
        if task_id in self.builder_tasks:
            return json.dumps({'error': 'a builder session cannot become a reference session'})
        self.reference_tasks.add(task_id)
        return json.dumps({'role': 'reference'})

    def builder_enter(self, args, task_id='', **_):
        self.reference_tasks.discard(task_id)
        self.builder_tasks.add(task_id)
        root = Path(self.builder_root()) / args['slug']
        return json.dumps({'role': 'builder', 'workspace': str(root), 'oracle': 'use ghostrun_oracle_call'})

    def socket_of(self, slug):
        info = Path(self.builder_root()) / slug / '.oracle.json'
        return json.loads(info.read_text())['socket']

    def oracle_start(self, args, **_):
        slug = args['slug']
        if slug in self.oracles and self.oracles[slug].poll() is None:
            return json.dumps({'running': True})
        argv = [self.python(), str(CLI), '--reference-root', self.reference_root(), '--builder-root', self.builder_root(),
                '--python', self.python(), 'oracle', slug, '--session', args.get('session') or 'default']
        if args.get('route'):
            argv += ['--route', args['route']]
        if args.get('policy'):
            argv += ['--policy', args['policy']]
        env = {**clean_env(), 'PYTHONPATH': os.pathsep.join([str(Path(self.reference_root()) / slug),
                                                             str(HERE / 'engine' / 'scripts' / 'reward10')])}
        self.oracles[slug] = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              start_new_session=True)
        return json.dumps({'started': True, 'pid': self.oracles[slug].pid})

    def oracle_stop(self, args, **_):
        proc = self.oracles.pop(args['slug'], None)
        if proc is None:
            return json.dumps({'error': 'no oracle started by this session'})
        proc.send_signal(signal.SIGTERM)
        return json.dumps({'stopped': True})

    def oracle_call(self, args, **_):
        sys.path.insert(0, str(HERE / 'core'))
        from oracle_client import OracleClient
        try:
            client = OracleClient(self.socket_of(args['slug']))
            try:
                reply = client.call(args['op'], **json.loads(args.get('fields') or '{}'))
            finally:
                client.close()
        except (OSError, RuntimeError, ValueError, KeyError) as e:
            return json.dumps({'error': str(e)})
        image = reply.pop('image_png_base64', None)
        if image:
            import base64
            folder = Path(self.builder_root()) / args['slug'] / 'oracle-frames'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{reply.get('frame', 0):08d}.png"
            path.write_bytes(base64.b64decode(image))
            reply['image_path'] = str(path)
        return json.dumps(reply)

    def watch_start(self, args, **_):
        slug, minutes = args['slug'], float(args.get('minutes') or 10)
        if slug in self.watchers:
            return json.dumps({'running': True})
        stop = threading.Event()
        thread = threading.Thread(target=self.watch_loop, args=(slug, minutes, stop), daemon=True, name=f'{PLUGIN}-{slug}')
        self.watchers[slug] = stop
        thread.start()
        return json.dumps({'watching': slug, 'every_minutes': minutes})

    def watch_stop(self, args, **_):
        stop = self.watchers.pop(args['slug'], None)
        if stop:
            stop.set()
        return json.dumps({'stopped': bool(stop)})

    def watch_loop(self, slug, minutes, stop):
        """Plain arithmetic until something is wrong, so a healthy run costs no tokens."""
        last = None
        while not stop.wait(minutes * 60):
            try:
                report = json.loads(self.run_cli(['watch', slug], timeout=300))
            except ValueError:
                continue
            codes = sorted(f['code'] for f in report.get('findings', []) if f['severity'] == 'act')
            if report.get('verdict') == 'act' and codes != last and not report.get('pending_fix'):
                self.ctx.inject_message(wake_message(slug, report), role='system')
            last = codes

    # ---- isolation ----
    def guard(self, tool_name, args, task_id='', **_):
        """Default deny: a session reaches the reference only after declaring itself a reference session."""
        if task_id in self.reference_tasks:
            return None
        if tool_name in REFERENCE_TOOLS or tool_name in ('ghostrun_oracle_start', 'ghostrun_oracle_stop'):
            return {'action': 'block', 'message': f'{tool_name} is for reference sessions only.'}
        body = json.dumps(args or {}, default=str).lower()
        if self.reference_root().lower() in body or '.nes' in body:
            return {'action': 'block', 'message': 'This session has no access to the reference game or its folder.'}
        return None

    # ---- slash command ----
    def status_command(self, raw_args, **_):
        slug = raw_args.strip()
        if not slug:
            return 'Usage: /ghostrun <game>'
        state = json.loads(self.run_cli(['status', slug], timeout=30))
        if 'error' in state:
            return state['error']
        lines = [f"{slug} ({state['mode']}), next: {state['next'] or 'done'}"]
        lines += [f"  {name:9} {stage['status']}" for name, stage in state['stages'].items()]
        return '\n'.join(lines)

    def unload(self):
        for stop in self.watchers.values():
            stop.set()
        self.watchers.clear()


def wake_message(slug, report):
    items = '\n'.join(f"- {f['code']}: {f['evidence']}. {f['next_step']}" for f in report['findings'] if f['severity'] == 'act')
    return (f'GhostRun training watcher, game {slug}, iteration {report.get("iteration")}, needs action.\n{items}\n'
            f'Load skill_view("{PLUGIN}:training-doctor") and follow it. Fixes used: {report.get("fixes_used")} of {report.get("fix_budget")}.')


def register(ctx):
    plugin = Plugin(ctx)
    for table in (REFERENCE_TOOLS, SHARED_TOOLS):
        for name, (command, description, props, flags) in table.items():
            ctx.register_tool(name=name, toolset=TOOLSET, handler=plugin.cli_handler(command, flags), description=description,
                              schema={'name': name, 'description': description, 'parameters': S(**props)})
    custom = {
        'ghostrun_reference_enter': (plugin.reference_enter, 'Declare this session a reference session (reward and training work). Follow skill_view("ghostrun:pipeline").', {}),
        'ghostrun_builder_enter': (plugin.builder_enter, 'Declare this session the builder. It then cannot reach the reference. '
                                   'Then load skill_view("ghostrun:rebuild-from-oracle") and follow it.', dict(slug=SLUG)),
        'ghostrun_oracle_start': (plugin.oracle_start, 'Start the black-box oracle for a game.',
                                  dict(slug=SLUG, session=text('Session name.', default=None),
                                       route=text('A search result to replay.', default=None),
                                       policy=text('Command of a trained player.', default=None))),
        'ghostrun_oracle_stop': (plugin.oracle_stop, 'Stop the oracle.', dict(slug=SLUG)),
        'ghostrun_oracle_call': (plugin.oracle_call, 'Send one request to the oracle: actions in, frames and declared numbers out.',
                                 dict(slug=SLUG, op=text('hello, reset, step, observe, checkpoint, restore or play.'),
                                      fields=text('JSON of the op fields, for example {"buttons":["RIGHT"],"frames":8}.', default=None))),
        'ghostrun_watch_start': (plugin.watch_start, 'Watch training in the background and wake the agent only when action is needed.',
                                 dict(slug=SLUG, minutes=number('Minutes between checks.', default=10))),
        'ghostrun_watch_stop': (plugin.watch_stop, 'Stop the background watcher.', dict(slug=SLUG)),
    }
    for name, (handler, description, props) in custom.items():
        ctx.register_tool(name=name, toolset=TOOLSET, handler=handler, description=description,
                          schema={'name': name, 'description': description, 'parameters': S(**props)})
    ctx.register_hook('pre_tool_call', plugin.guard)
    ctx.register_command(PLUGIN, plugin.status_command, description='Show a game\'s pipeline stages.', args_hint='<game>')
    for folder in sorted(SKILLS.iterdir()):
        if (folder / 'SKILL.md').exists():
            ctx.register_skill(folder.name, folder / 'SKILL.md')
    ctx.on_unload(plugin.unload)
