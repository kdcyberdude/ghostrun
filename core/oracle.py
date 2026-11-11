"""Black-box oracle: the only route from the builder to the reference game.

The server runs on the reference side and speaks one JSON object per line over a Unix socket. Replies carry frames,
applied controls and declared observables. They never carry the ROM, its path, RAM or savestate bytes.

Ops: hello | reset | step{buttons,frames,image?} | observe{image?} | checkpoint{name} | restore{name} | play{ticks,image?}
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys

MAX_LINE = 1 << 19
BUTTONS = ('UP', 'DOWN', 'LEFT', 'RIGHT', 'A', 'B', 'START', 'SELECT')
FIELDS = {
    'hello': set(), 'reset': set(), 'step': {'buttons', 'frames', 'image', 'per_frame'}, 'observe': {'image'},
    'checkpoint': {'name'}, 'restore': {'name'}, 'play': {'ticks', 'image'},
}
MAX_FRAMES = 240


class OracleError(ValueError):
    pass


def png_bytes(screen):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(screen).save(buf, 'PNG')
    return buf.getvalue()


class NesBackend:
    """The real game, driven through core/reward10/nesram.py and a game module."""

    def __init__(self, game):
        from nesram import Nes
        self.game, self.nes = game, Nes(game.ROM)
        self.power_on = self.nes.save()

    def reset(self):
        self.nes.load(self.power_on)
        self.game.boot(self.nes)
        self.boot_frames = self.nes.frame

    def step(self, buttons, frames):
        self.nes.step(tuple(buttons), frames)

    def screen(self):
        return self.nes.screen()

    def observables(self):
        fn = getattr(self.game, 'observables', None)
        return fn(self.nes.ram()) if fn else {}

    def save(self):
        return self.nes.save()

    def load(self, snap):
        self.nes.load(snap)


class ReplayPlayer:
    """Plays a recorded route: a list of (buttons, frames) decisions."""

    def __init__(self, decisions):
        self.decisions, self.i = list(decisions), 0

    def reset(self, screen_png):
        self.i = 0

    def next(self, screen_png):
        if self.i >= len(self.decisions):
            return None
        d, self.i = self.decisions[self.i], self.i + 1
        return d


class PolicyPlayer:
    """A trained player process using the pixel-policy protocol (hello, reset, advance): pixels in, buttons out."""

    def __init__(self, argv):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.pending = None
        self._call(op='hello')

    def _call(self, **req):
        self.p.stdin.write(json.dumps(req) + '\n')
        self.p.stdin.flush()
        reply = json.loads(self.p.stdout.readline())
        if not reply.get('ok', False):
            raise OracleError(f"policy refused: {reply.get('error')}")
        return reply

    def _take(self, reply):
        self.pending = reply
        names = [b.upper() for b in reply.get('buttons', []) if b.upper() in BUTTONS]
        return names, reply['frames']

    def reset(self, screen_png):
        self._started = False
        self._take(self._call(op='reset', image_png_base64=base64.b64encode(screen_png).decode()))

    def next(self, screen_png):
        if self.pending is None:
            return None
        if getattr(self, '_started', False):
            p = self.pending
            self._take(self._call(op='advance', tick=p['tick'], applied_mask=p['mask'], frames_advanced=p['frames'],
                                  image_png_base64=base64.b64encode(screen_png).decode()))
        self._started = True
        return [b.upper() for b in self.pending.get('buttons', []) if b.upper() in BUTTONS], self.pending['frames']


class Oracle:
    def __init__(self, backend, session_dir, player=None):
        self.backend, self.player, self.snaps, self.frame = backend, player, {}, 0
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.trace = open(self.dir / 'trace.jsonl', 'a', buffering=1)

    def _record(self, buttons, frames):
        self.trace.write(json.dumps({'f': self.frame, 'buttons': list(buttons), 'frames': frames,
                                     **self.backend.observables()}) + '\n')

    def _reply(self, image, **extra):
        screen = self.backend.screen()
        data = png_bytes(screen)
        out = {'ok': True, 'frame': self.frame, 'frame_sha256': hashlib.sha256(data).hexdigest(),
               'observables': self.backend.observables(), **extra}
        if image:
            folder = self.dir / 'frames'
            folder.mkdir(exist_ok=True)
            snapshot = folder / f'{self.frame}-{out["frame_sha256"]}.png'
            snapshot.write_bytes(data)
            snapshot.with_suffix('.json').write_text(json.dumps({'f': self.frame, 'observables': out['observables']}))
            out['image_png_base64'] = base64.b64encode(data).decode()
        return out

    def _advance(self, buttons, frames):
        for _ in range(frames):
            self.backend.step(buttons, 1)
            self.frame += 1
            self._record(buttons, 1)

    def handle(self, req):
        op = req.get('op')
        if op not in FIELDS:
            raise OracleError(f'unknown op {op!r}')
        extra = set(req) - FIELDS[op] - {'op'}
        if extra:
            raise OracleError(f'unknown fields {sorted(extra)}')
        if op == 'hello':
            screen = self.backend.screen()
            return {'ok': True, 'buttons': list(BUTTONS), 'fps': 60.0988, 'width': int(screen.shape[1]),
                    'height': int(screen.shape[0]), 'ops': sorted(FIELDS), 'max_frames': MAX_FRAMES,
                    'player': self.player is not None}
        if op == 'reset':
            self.backend.reset()
            self.frame = 0
            self._record([], 0)
            if self.player:
                self.player.reset(png_bytes(self.backend.screen()))
            return self._reply(True, boot_frames=getattr(self.backend, 'boot_frames', 0))
        if op == 'observe':
            return self._reply(bool(req.get('image')))
        if op == 'step':
            buttons, frames = req.get('buttons', []), req.get('frames', 1)
            if not set(buttons) <= set(BUTTONS):
                raise OracleError(f'unknown buttons {sorted(set(buttons) - set(BUTTONS))}')
            if not (isinstance(frames, int) and 1 <= frames <= MAX_FRAMES):
                raise OracleError(f'frames must be 1..{MAX_FRAMES}')
            if req.get('per_frame'):
                rows = []
                for _ in range(frames):
                    self._advance(buttons, 1)
                    rows.append({'f': self.frame, 'buttons': list(buttons), **self.backend.observables()})
                return self._reply(bool(req.get('image')), applied=buttons, trace=rows)
            self._advance(buttons, frames)
            return self._reply(bool(req.get('image')), applied=buttons)
        if op == 'checkpoint':
            self.snaps[req['name']] = (self.backend.save(), self.frame)
            return {'ok': True, 'name': req['name'], 'frame': self.frame}
        if op == 'restore':
            if req['name'] not in self.snaps:
                raise OracleError(f"no checkpoint {req['name']!r}")
            snap, self.frame = self.snaps[req['name']]
            self.backend.load(snap)
            return self._reply(False)
        if self.player is None:
            raise OracleError('no player is attached')
        moves = []
        for _ in range(req.get('ticks', 1)):
            decision = self.player.next(png_bytes(self.backend.screen()))
            if decision is None:
                break
            self._advance(*decision)
            moves.append({'buttons': list(decision[0]), 'frames': decision[1], 'frame': self.frame})
        return self._reply(bool(req.get('image')), moves=moves, finished=len(moves) < req.get('ticks', 1))


def serve(oracle, sock_path):
    """Answer one client at a time until stopped. The socket file is removed on exit, so no client finds a dead one."""
    path = Path(sock_path)
    path.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path))
    path.chmod(0o600)
    srv.listen(1)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        while True:
            conn, _ = srv.accept()
            with conn, conn.makefile('rw', encoding='utf-8', newline='\n') as f:
                while line := f.readline(MAX_LINE + 1):
                    try:
                        if len(line) > MAX_LINE:
                            raise OracleError('request too long')
                        reply = oracle.handle(json.loads(line))
                    except (OracleError, json.JSONDecodeError, KeyError, TypeError) as e:
                        reply = {'ok': False, 'error': str(e)}
                    f.write(json.dumps(reply) + '\n')
                    f.flush()
    finally:
        srv.close()
        path.unlink(missing_ok=True)
