"""Generated test cartridge. $10 counts frames with Right held and wraps at 255."""
import os
from pathlib import Path

from reward import Signals

ROM = str(Path(os.environ.get('NES_ROM_DIR') or Path(__file__).resolve().parents[1]) / 'game.nes')
ROM_SHA256 = '0' * 64
ACTIONS = [('RIGHT',), ()]
PROGRESS_UNIT = 100.0
SCORE_UNIT = 100.0
DEATH_FROM = 'lives'
STALL_SECONDS = 5.0
INFO = dict(title='Test', genre='test', level='one', levels=1, progress='RAM $10', death='none', game_over='none',
            health=None, score=None, win='none', win_status='none', limits=[])


def boot(n):
    n.step((), 10)


def observables(r):
    return {'x': int(r[0x10])}


class Reader:
    def reset(self):
        pass

    def observe(self, r):
        return Signals(in_play=True, level=0, progress=float(r[0x10]))
