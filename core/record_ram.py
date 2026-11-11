"""Record a per-frame RAM trace of random play from a fresh start, for the Python-versus-CUDA reward parity test.

usage: python record_ram.py <game> OUT.ram.bin [--decisions 4000] [--seed 1]
"""
from __future__ import annotations

import argparse
import random

import numpy as np

from nesram import Nes
from search import load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game')
    ap.add_argument('out')
    ap.add_argument('--decisions', type=int, default=4000)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    g, rng, frames = load(a.game), random.Random(a.seed), []
    n = Nes(g.ROM)
    g.boot(n)
    action = rng.choice(g.ACTIONS)
    for _ in range(a.decisions):
        if rng.random() > 0.8:
            action = rng.choice(g.ACTIONS)
        steps = action if isinstance(action, list) else [(action, 8)]
        for buttons, count in steps:
            n.step(buttons, count, record=frames)
    np.stack(frames).tofile(a.out)
    print(f'{len(frames)} frames')


if __name__ == '__main__':
    main()
