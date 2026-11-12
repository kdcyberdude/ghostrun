"""Regression coverage for the catalog review's execution and filesystem boundaries."""
import argparse
import json
import os
from pathlib import Path
import socket
import tempfile
import subprocess
import sys

import pytest
import cli
import oracle
from ghostrun_security import child_env, checkpoint_path, validate_slug
from train_ctl import Game
from test_plugin import Ctx, load


@pytest.mark.parametrize('slug', ['../escape', '/tmp/escape', 'x/y', "x');print('bad')#", '', 'a'*33, None, 'Mario'])
def test_invalid_slug_stops_every_tool_before_work(slug, tmp_path, monkeypatch):
    module = load()
    context = Ctx({'reference_root': str(tmp_path/'ref'), 'builder_root': str(tmp_path/'build')})
    module.register(context)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: pytest.fail('must not execute'))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not spawn'))
    for name, (schema, handler, _) in context.tools.items():
        if 'slug' in schema['parameters']['properties']:
            result = json.loads(handler({'slug': slug}))
            assert 'slug' in result.get('error', ''), (name, result)
    assert not (tmp_path/'ref').exists()
    assert not (tmp_path/'build').exists()


def test_cli_rejects_invalid_slug_before_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['cli.py', 'status', '../escape'])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1
    assert 'slug' in json.loads(capsys.readouterr().out)['error']


def test_checkpoint_is_confined_to_runs(tmp_path):
    runs = tmp_path/'g/runs'
    runs.mkdir(parents=True)
    valid = runs/'model.pt'; valid.write_bytes(b'fixture')
    assert checkpoint_path(tmp_path, 'g', valid) == valid.resolve()
    outside = tmp_path/'outside.pt'; outside.write_bytes(b'fixture')
    link = runs/'link.pt'; link.symlink_to(outside)
    for invalid in [outside, link, runs]:
        with pytest.raises(ValueError):
            checkpoint_path(tmp_path, 'g', invalid)


def test_oracle_rejects_legacy_command_even_with_live_server(tmp_path, monkeypatch):
    module = load(); plugin = module.Plugin(Ctx({'reference_root':str(tmp_path)}))
    monkeypatch.setattr(plugin, 'oracle_hello', lambda *a, **k: pytest.fail('reject before handshake'))
    assert 'error' in json.loads(plugin.oracle_start({'slug':'g','policy':'sh -c anything'}))
    assert 'error' in json.loads(plugin.oracle_start({'slug':'g','session':'../outside'}))


def test_child_environments_exclude_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sentinel-secret')
    monkeypatch.setenv('ANTHROPIC_API_KEY','sentinel-secret')
    monkeypatch.setenv('PYTHONPATH','untrusted-imports')
    monkeypatch.setenv('PYTHONHOME','untrusted-python')
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
    monkeypatch.setenv('RL_TEST_SETTING','yes')
    module = load()
    args = argparse.Namespace(reference_root=str(tmp_path),slug='g')
    for env in [child_env(), module.clean_env(), Game(tmp_path/'g','g').env(), cli.reward_env(args)]:
        assert 'sentinel-secret' not in env.values()
        assert 'PYTHONHOME' not in env
        assert env.get('PYTHONPATH') != 'untrusted-imports'
        assert env['CUDA_VISIBLE_DEVICES']=='0'
        assert env['RL_TEST_SETTING']=='yes'
    env = child_env()
    result = subprocess.check_output([sys.executable,'-c','import os;print(os.environ.get("OPENAI_API_KEY", "absent"))'],env=env,text=True)
    assert result.strip()=='absent'


def test_policy_launch_uses_fixed_script_and_clean_environment(tmp_path, monkeypatch):
    checkpoint=tmp_path/'g/runs/model.pt';checkpoint.parent.mkdir(parents=True);checkpoint.touch()
    captured={}
    def spawn(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return object()
    monkeypatch.setattr(oracle.subprocess,'Popen',spawn)
    monkeypatch.setattr(oracle.PolicyPlayer,'_call',lambda *a, **k: {'ok':True})
    monkeypatch.setenv('OPENAI_API_KEY','secret')
    oracle.PolicyPlayer(sys.executable,tmp_path,'g',checkpoint)
    argv=captured['argv']
    assert argv == [sys.executable,str(Path(oracle.__file__).resolve().parents[1]/'engine/rl/player/checkpoint.py'),
                    '--checkpoint',str(checkpoint.resolve()),'--game','g']
    assert 'OPENAI_API_KEY' not in captured['env']


def test_socket_is_private_at_bind(monkeypatch):
    class StopServer(Exception): pass
    original = oracle.socket.socket
    class Server:
        def bind(self, address):
            real = original(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                real.bind(address)
                assert Path(address).stat().st_mode & 0o777 == 0o600
            finally:
                real.close()
        def listen(self, count):
            raise StopServer()
    monkeypatch.setattr(oracle.socket, 'socket', lambda *a: Server())
    old = os.umask(0o022)
    try:
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='gr-test-') as directory:
            with pytest.raises(StopServer):
                oracle.serve(None, Path(directory) / 's')
        restored = os.umask(0o022)
        assert restored == 0o022
    finally:
        os.umask(old)
