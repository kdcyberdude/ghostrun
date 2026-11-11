"""Reference-side reward usefulness audit on captured RAM; never actor input.

Run with the configured game Python and REWARD10_GAMES_ROOT:
python core/reward_diagnose.py GAME captured_ram.npy --stride 8
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

import numpy as np

REWARD = Path(__file__).resolve().parents[1] / 'engine/scripts/reward10'
sys.path.insert(0, str(REWARD))
sys.path.insert(0, os.environ.get('REWARD10_GAMES_ROOT', str(REWARD)))
from reward import RewardTracker, idle_per_frame  # noqa: E402
from compare import sha256  # noqa: E402


def diagnose(game, rows, stride=8):
    if stride < 1 or rows.ndim != 2 or rows.shape[1] != 2048 or rows.dtype != np.uint8 or len(rows) < stride + 1:
        raise ValueError('need per-frame 2048-byte RAM rows and a positive decision stride')
    tracker = RewardTracker(game)
    tracker.update(rows[0], 0, frames=0)
    observe = getattr(game, 'observables', lambda _: {})
    previous = observe(rows[0])
    groups = {}
    for f in range(stride, len(rows), stride):
        before = tracker.prev
        reward, done, events = tracker.update(rows[f], f, frames=stride)
        now = tracker.prev
        observed = observe(rows[f])
        if not before.in_play or not now.in_play:
            category = 'transition'
        elif now.progress > before.progress or now.level > before.level:
            category = 'task-progress'
        elif all(k in previous and k in observed for k in ('player_x', 'player_y')):
            category = 'travel-without-progress' if any(previous[k] != observed[k] for k in ('player_x', 'player_y')) else 'stationary-without-progress'
        else:
            category = 'no-progress-motion-unmeasured'
        item = groups.setdefault(category, {'updates': 0, 'reward': 0.0, 'deaths': 0})
        item['updates'] += 1
        item['reward'] += reward
        item['deaths'] += sum(name == 'death' for name, _ in events)
        previous = observed
        if done:
            break
    return {'stride': stride, 'groups': groups, 'idle_charge_per_no_progress_update': idle_per_frame(game) * stride,
            'limit': 'Coordinate changes indicate observed motion, not useful intent. Compare fixed trajectories and real policy outcomes before changing reward.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game')
    parser.add_argument('trace')
    parser.add_argument('--stride', type=int, default=8)
    args = parser.parse_args()
    game = importlib.import_module(f'games.{args.game}')
    report = diagnose(game, np.load(args.trace, allow_pickle=False), args.stride)
    print(json.dumps({**report, 'trace_sha256': sha256(args.trace)}, indent=2))


if __name__ == '__main__':
    main()
