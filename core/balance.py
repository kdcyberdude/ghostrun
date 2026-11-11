"""Scripted-player balance test: hold each action from a fresh start and compare discounted returns.

If an action that makes almost no progress out-earns the one that makes the most, the reward teaches standing still.
usage: python balance.py <game> --steps 600
"""
from __future__ import annotations

import argparse
import json

from nesram import Nes
from reward import RewardTracker
from search import apply_action, load

GAMMA = 0.995


def play(g, action, steps):
    n = Nes(g.ROM)
    g.boot(n)
    tr = RewardTracker(g)
    tr.update(n.ram(), 0)
    total = 0.0
    for t in range(1, steps + 1):
        frames = apply_action(n, action)
        r, done, _ = tr.update(n.ram(), t, frames=frames)
        total += r * GAMMA ** t
        if done:
            break
    return {'action': repr(action), 'discounted_return': round(total, 4), 'level': tr.best_level,
            'progress': tr.best_progress or 0.0, 'deaths': tr.deaths, 'end': tr.end_reason, 'steps': t}


def judge(results):
    """Return a problem string, or None. Compares furthest-moving action with the best-paying one."""
    furthest = max(results, key=lambda r: (r['level'] or 0, r['progress']))
    richest = max(results, key=lambda r: r['discounted_return'])
    moved = furthest['progress'] > 0 or (furthest['level'] or 0) > 0
    if moved and richest is not furthest and (richest['level'] or 0) <= (furthest['level'] or 0) \
            and richest['progress'] < 0.1 * furthest['progress']:
        return f"{richest['action']} earns {richest['discounted_return']} without moving; " \
               f"{furthest['action']} moves furthest but earns {furthest['discounted_return']}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game')
    ap.add_argument('--steps', type=int, default=600)
    a = ap.parse_args()
    g = load(a.game)
    results = [play(g, action, a.steps) for action in g.ACTIONS]
    print(json.dumps({'results': results, 'problem': judge(results)}, indent=1))


if __name__ == '__main__':
    main()
