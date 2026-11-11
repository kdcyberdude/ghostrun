"""Loads the plugin against a stand-in for the Hermes context and checks what it registers."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class Ctx:
    def __init__(self, settings=None):
        self.tools, self.hooks, self.skills, self.commands, self.unload = {}, {}, {}, {}, []
        self.settings, self.injected = settings or {}, []

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = (schema, handler, kw)

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_skill(self, name, path):
        self.skills[name] = path

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler

    def on_unload(self, callback):
        self.unload.append(callback)

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def inject_message(self, content, role='user'):
        self.injected.append((content, role))
        return True


def load():
    spec = importlib.util.spec_from_file_location('ghostrun_plugin', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ctx(tmp_path):
    c = Ctx({'reference_root': str(tmp_path / 'ref'), 'builder_root': str(tmp_path / 'build')})
    load().register(c)
    return c


def test_manifest_matches_registrations(ctx):
    manifest = yaml.safe_load((ROOT / 'plugin.yaml').read_text())
    assert set(manifest['provides_tools']) == set(ctx.tools)
    assert set(manifest['provides_hooks']) == set(ctx.hooks)


def test_schemas_and_skills(ctx):
    for name, (schema, _, _) in ctx.tools.items():
        assert schema['name'] == name and schema['parameters']['type'] == 'object'
        assert set(schema['parameters']['required']) <= set(schema['parameters']['properties'])
    assert set(ctx.skills) == {'pipeline', 'reward-discovery', 'gpu-env-port', 'training-doctor', 'rebuild-from-oracle', 'visual-upgrade'}
    for path in ctx.skills.values():
        front = yaml.safe_load(path.read_text().split('---')[1])
        assert front['name'] == path.parent.name and front['description']


def test_full_cli_round_trip(ctx, tmp_path):
    rom = tmp_path / 'g.nes'
    rom.write_bytes(b'NES\x1a' + bytes(64))
    guard = ctx.hooks['pre_tool_call']
    assert guard('ghostrun_init', {'slug': 'g', 'rom': str(rom)}, task_id='t')['action'] == 'block'
    ctx.tools['ghostrun_reference_enter'][1]({}, task_id='t')
    assert guard('ghostrun_init', {'slug': 'g', 'rom': str(rom)}, task_id='t') is None
    out = json.loads(ctx.tools['ghostrun_init'][1]({'slug': 'g', 'rom': str(rom)}))
    assert out['next'] == 'reward'
    assert 'reward' in ctx.commands['ghostrun']('g')
    assert json.loads(ctx.tools['ghostrun_isolation_check'][1]({'slug': 'g'}))['isolated']


def test_faithful_refused_without_rights(ctx, tmp_path):
    rom = tmp_path / 'g.nes'
    rom.write_bytes(b'x')
    out = json.loads(ctx.tools['ghostrun_init'][1]({'slug': 'g', 'rom': str(rom), 'mode': 'faithful'}))
    assert 'rights' in out['error']


def test_builder_is_locked_out(ctx, tmp_path):
    guard = ctx.hooks['pre_tool_call']
    ctx.tools['ghostrun_builder_enter'][1]({'slug': 'g'}, task_id='b')
    assert 'error' in json.loads(ctx.tools['ghostrun_reference_enter'][1]({}, task_id='b'))
    ref = ctx.settings['reference_root']
    assert guard('read_file', {'path': f'{ref}/g/game.nes'}, task_id='b')['action'] == 'block'
    assert guard('terminal', {'command': 'find / -name "*.NES"'}, task_id='b')['action'] == 'block'
    assert guard('ghostrun_train_start', {'slug': 'g'}, task_id='b')['action'] == 'block'
    assert guard('ghostrun_oracle_call', {'slug': 'g', 'op': 'hello'}, task_id='b') is None
    assert guard('read_file', {'path': 'src/game.ts'}, task_id='b') is None


def test_wake_message_only_on_new_action(ctx, tmp_path):
    module = load()
    plugin = module.Plugin(ctx)
    reports = iter([
        {'verdict': 'healthy', 'findings': []},
        {'verdict': 'act', 'iteration': 9, 'fixes_used': 0, 'fix_budget': 3,
         'findings': [{'code': 'x', 'severity': 'act', 'evidence': 'e', 'next_step': 'n'}]},
        {'verdict': 'act', 'iteration': 10, 'fixes_used': 0, 'fix_budget': 3,
         'findings': [{'code': 'x', 'severity': 'act', 'evidence': 'e', 'next_step': 'n'}]},
    ])

    class Stop:
        n = 0

        def wait(self, _):
            Stop.n += 1
            return Stop.n > 3

    plugin.run_cli = lambda *a, **k: json.dumps(next(reports))
    plugin.watch_loop('g', 1, Stop())
    assert len(ctx.injected) == 1 and 'training-doctor' in ctx.injected[0][0]


def test_reference_context_cannot_become_builder(ctx):
    ctx.tools['ghostrun_reference_enter'][1]({}, task_id='reference')
    reply = json.loads(ctx.tools['ghostrun_builder_enter'][1]({'slug': 'g'}, task_id='reference'))
    assert 'fresh builder session' in reply['error']


def test_recreate_builder_waits_for_assets(ctx, tmp_path):
    rom = tmp_path / 'g.nes'
    rom.write_bytes(b'NES\x1a' + bytes(64))
    init = json.loads(ctx.tools['ghostrun_init'][1]({'slug': 'g', 'rom': str(rom)}))
    assert init['mode'] == 'recreate'
    reply = json.loads(ctx.tools['ghostrun_builder_enter'][1]({'slug': 'g'}, task_id='builder'))
    assert 'prepare assets' in reply['error']


def test_cli_uses_configured_game_runtime(tmp_path):
    module = load()
    plugin = module.Plugin(Ctx({'python': '/configured/game/python'}))
    argv = plugin.base_argv()
    assert argv[0] == '/configured/game/python'
    assert argv[argv.index('--python') + 1] == '/configured/game/python'
