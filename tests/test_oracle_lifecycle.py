"""Exercise startup and ownership through the real Unix-socket handshake."""
import argparse
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

import cli
from compare import sha256
from oracle_client import OracleClient


ROOT = Path(__file__).resolve().parents[1]
SERVER = '''
import json, pathlib, socket, sys, time
args = sys.argv[1:]
root = pathlib.Path(args[args.index('--builder-root') + 1])
slug = args[args.index('oracle') + 1]
address = json.loads((root / slug / '.oracle.json').read_text())['socket']
time.sleep(.1)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(address)
server.listen()
while True:
    conn, _ = server.accept()
    with conn, conn.makefile('rw') as stream:
        for line in stream:
            request = json.loads(line)
            stream.write(json.dumps({'ok': True, 'width': 256, 'height': 240,
                                     'buttons': [], 'ops': ['hello'], 'fps': 60.0988}) + '\\n')
            stream.flush()
'''


@pytest.fixture
def setup(tmp_path):
    spec = importlib.util.spec_from_file_location('oracle_lifecycle_plugin', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = {'reference_root': str(tmp_path / 'ref'), 'builder_root': str(tmp_path / 'build'),
                'python': sys.executable}
    context = type('Context', (), {'get_config': lambda self, key, default: settings.get(key, default)})()
    plugin = module.Plugin(context)
    build = Path(settings['builder_root']) / 'g'
    build.mkdir(parents=True)
    helper = tmp_path / 'server.py'
    helper.write_text(SERVER)
    module.CLI = helper
    with tempfile.TemporaryDirectory(prefix='gr-oracle-', dir='/tmp') as short:
        endpoint = Path(short) / 'oracle.sock'
        (build / '.oracle.json').write_text(json.dumps({'socket': str(endpoint), 'mode': 'recreate'}))
        yield module, plugin, build, endpoint, helper
        for process in plugin.oracles.values():
            stop(process)


def stop(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=3)


def test_start_returns_only_after_live_hello(setup):
    module, plugin, _, endpoint, _ = setup
    module.ORACLE_START_TIMEOUT = 3
    reply = json.loads(plugin.oracle_start({'slug': 'g'}))
    assert reply.get('started') and reply.get('ready'), reply
    assert endpoint.exists()
    client = OracleClient(endpoint, timeout=1)
    try:
        assert client.call('hello')['width'] == 256
    finally:
        client.close()
    assert Path(reply['log']).is_relative_to(Path(plugin.reference_root()))


def test_dead_process_returns_its_private_diagnostic(setup):
    _, plugin, _, _, helper = setup
    helper.write_text("raise SystemExit('native backend failed to load fixture')\n")
    reply = json.loads(plugin.oracle_start({'slug': 'g'}))
    assert 'error' in reply and not reply.get('started'), reply
    assert 'native backend failed to load fixture' in reply.get('details', '')
    assert reply.get('exit_code') != 0
    log = Path(reply['log'])
    assert log.is_relative_to(Path(plugin.reference_root()))
    assert 'native backend failed' in log.read_text()


def test_timeout_reaps_only_the_process_started_by_this_call(setup, monkeypatch):
    module, plugin, _, _, helper = setup
    helper.write_text('import time\ntime.sleep(100)\n')
    module.ORACLE_START_TIMEOUT = .15
    original = subprocess.Popen
    spawned = []
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        spawned.append(process)
        return process
    monkeypatch.setattr(module.subprocess, 'Popen', capture)
    began = time.monotonic()
    reply = json.loads(plugin.oracle_start({'slug': 'g'}))
    assert 'error' in reply and not reply.get('ready'), reply
    assert time.monotonic() - began < 2
    assert len(spawned) == 1 and spawned[0].poll() is not None


def test_reuses_healthy_external_server_without_taking_ownership(setup, monkeypatch):
    module, plugin, _, _, helper = setup
    argv = [sys.executable, str(helper), '--builder-root', plugin.builder_root(), 'oracle', 'g']
    process = subprocess.Popen(argv)
    try:
        deadline = time.monotonic() + 3
        while True:
            try:
                plugin.oracle_hello('g', timeout=.1)
                break
            except (OSError, RuntimeError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        def forbidden(*args, **kwargs):
            pytest.fail('a healthy external oracle must not be replaced')
        monkeypatch.setattr(module.subprocess, 'Popen', forbidden)
        reply = json.loads(plugin.oracle_start({'slug': 'g'}))
        assert reply.get('running') and reply.get('ready') and reply.get('managed') is False, reply
        plugin.unload()
        assert process.poll() is None
    finally:
        stop(process)


def test_unhealthy_owned_process_is_not_duplicated(setup, monkeypatch):
    module, plugin, _, _, helper = setup
    helper.write_text('import time\ntime.sleep(100)\n')
    process = subprocess.Popen([sys.executable, str(helper)])
    plugin.oracles['g'] = process
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not duplicate a live process'))
    reply = json.loads(plugin.oracle_start({'slug': 'g'}))
    assert 'error' in reply and not reply.get('ready'), reply
    assert process.poll() is None


def test_builder_cannot_start_with_valid_assets_and_dead_oracle(setup):
    _, plugin, build, _, _ = setup
    assets = build / 'assets'
    assets.mkdir()
    sprite = assets / 'sprite.png'
    sprite.write_bytes(b'observed sprite fixture')
    (assets / 'manifest.json').write_text(json.dumps({'files': [dict(
        path='sprite.png', method='authored', source='test fixture', sha256=sha256(sprite))]}))
    reply = json.loads(plugin.builder_enter({'slug': 'g'}, task_id='builder'))
    assert 'error' in reply and 'oracle' in reply['error'].lower(), reply
    assert 'builder' not in plugin.builder_tasks


def test_private_endpoint_survives_different_runtime_temporary_directory(tmp_path, monkeypatch):
    first, second = tmp_path / 'first-temp', tmp_path / 'second-temp'
    first.mkdir()
    second.mkdir()
    rom = tmp_path / 'test.nes'
    rom.write_bytes(b'NES\x1a' + bytes(64))
    args = argparse.Namespace(reference_root=str(tmp_path / 'ref'), builder_root=str(tmp_path / 'build'),
                              slug='g', rom=str(rom), mode='recreate', rights=None)
    monkeypatch.setattr(cli.tempfile, 'gettempdir', lambda: str(first))
    cli.cmd_init(args)
    descriptor = Path(args.builder_root) / 'g/.oracle.json'
    expected = json.loads(descriptor.read_text())['socket']
    monkeypatch.setattr(cli.tempfile, 'gettempdir', lambda: str(second))
    assert str(cli.socket_path(args)) == expected
    pin = Path(args.reference_root) / 'g/oracle-endpoint.json'
    assert json.loads(pin.read_text())['socket'] == expected


def test_oracle_client_times_out_when_connected_server_never_replies(setup):
    _, _, _, endpoint, _ = setup
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen()
    release = threading.Event()
    def hold_connection():
        connection, _ = listener.accept()
        with connection:
            release.wait(2)
    thread = threading.Thread(target=hold_connection, daemon=True)
    thread.start()
    client = OracleClient(endpoint, timeout=.05)
    try:
        with pytest.raises(TimeoutError):
            client.call('hello')
    finally:
        release.set()
        client.close()
        listener.close()
        thread.join(timeout=1)
