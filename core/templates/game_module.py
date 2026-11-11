"""<Game title>. List every RAM address used, its meaning and how it was verified.

Reward-hacking risks: <what could be farmed or skipped, and how the shared reward handles it>
"""
import sys
import os
from pathlib import Path

from nesram import digits  # noqa: F401
from reward import Signals

ROM = str(Path(os.environ.get('NES_ROM_DIR') or Path(__file__).resolve().parents[1]) / 'game.nes')
ROM_SHA256 = '<sha256>'
ACTIONS = [('RIGHT',), ('RIGHT', 'A'), ('A',), ('LEFT',), ()]
PROGRESS_UNIT = 1000.0   # progress units in one full level
SCORE_UNIT = 100.0       # points in one typical scoring event
DEATH_FROM = 'lives'     # or 'dying'

INFO = dict(
    title='<title>', genre='<genre>', level='<what one level is>', levels=None,
    progress='<what progress measures>', death='<what counts as a death>', game_over='<what ends the game>',
    health=None, score=None, win='<what counts as finishing>', win_status='none', limits=[],
)


def boot(n):
    """Power-on to the first controllable frame of a fresh 1-player game. Poll RAM; never sleep a fixed time alone."""
    raise NotImplementedError


def observables(r):
    """Verified numeric gameplay observations: player/enemy positions and modes, score, lives,
    level, terminal and mechanic-specific counters. Required for recreation coverage.
    Discover through controlled play and RAM/screen correlation; no map/code dumps or ROM tables.
    """
    return {}


class Reader:
    def reset(self):
        pass

    def observe(self, r):
        return Signals(in_play=False, level=0, progress=0.0)
