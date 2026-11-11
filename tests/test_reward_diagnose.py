from types import SimpleNamespace

import numpy as np
import pytest

from reward_diagnose import diagnose
from reward import Signals, idle_per_frame


class Reader:
    def reset(self):
        pass

    def observe(self, ram):
        return Signals(True, 0, float(ram[0]), lives=3)


def game():
    return SimpleNamespace(Reader=Reader, PROGRESS_UNIT=192, SCORE_UNIT=10, DEATH_FROM='lives',
                           observables=lambda r: {'player_x': int(r[1]), 'player_y': 0})


def test_audit_exposes_equal_cost_for_motion_and_stationary_nonpickup_steps():
    rows = np.zeros((25, 2048), dtype=np.uint8)
    rows[8:, 1] = 1
    report = diagnose(game(), rows, stride=8)
    travel, waiting = report['groups']['travel-without-progress'], report['groups']['stationary-without-progress']
    assert travel['updates'] == 1 and waiting['updates'] == 2
    assert travel['reward'] == pytest.approx(idle_per_frame(game()) * 8)
    assert waiting['reward'] / 2 == pytest.approx(travel['reward'])


def test_audit_uses_training_cadence_not_every_frame_as_a_decision():
    rows = np.zeros((25, 2048), dtype=np.uint8)
    rows[1:, 0] = 1
    report = diagnose(game(), rows, stride=8)
    assert sum(g['updates'] for g in report['groups'].values()) == 3
    assert report['groups']['task-progress']['updates'] == 1
