# Results

GhostRun builds on earlier work that trained a player for a specific game and used its playthrough to guide a rebuild. The current project brings that workflow into a Hermes plugin and extends the training and exploration approach across games.

## Single-game foundation

The earlier demonstration-assisted PPO approach completed each of two NES games in **10 out of 10 evaluations from a deterministic fresh start**. These runs establish the starting point for GhostRun: a trained player can supply a complete route through a game. Robustness to varied starts and input noise remains part of the broader training work.

The reconstruction method was developed on a private research rebuild. Against its recorded reference route:

- Position differences above 3 pixels fell from **5,477 to 1,471**, a **73% reduction**.
- Position differences above 8 pixels fell from **2,103 to 270**, an **87% reduction**.
- An optional 2.5D renderer preserved the gameplay simulation over **2,600 comparison frames** and sustained **60 fps at resolutions up to 4K** on a shared RTX 5090.

These measurements describe the earlier research prototype and its recorded route. The plugin packages the reward, training, oracle and comparison tools for applying the same workflow to new games.

## Released Mario recordings

The [v2 recording release](https://github.com/kdcyberdude/ghostrun-lab/releases/tag/recordings-v2-20261111) includes all 32 selected level-start videos, exact action bytes, eight-mood selection tables and a per-level audit. The outcomes are **23 clears, 8 game overs and 1 capped attempt**. All 32 copied controller hashes and selection rankings were checked independently.

The fresh v1 capture separately visited all 32 levels in order, retaining 10,626 ticks / 79,824 legacy frame slices. Every action and duration matched its retained route. It reported terminal beside Princess before the ending text appeared; `won=false` is preserved in the [capture report](https://github.com/kdcyberdude/ghostrun-lab/blob/main/docs/V1_RECORDING.md). The [full recording archive](https://github.com/kdcyberdude/ghostrun-lab/releases/tag/recordings-v1-20261111) includes all per-level videos and original screenshots.

The v2 clips are separate saved-entrance attempts, not one uninterrupted campaign. The silent NeSLE preview videos omit boot/warmup and sometimes terminal frames included in their logs; matching video frame zero to action frame zero would be incorrect. The release documents the clock and initial-state requirements for comparisons.

## Training infrastructure

Local experiments on one RTX 5090 measured:

- **12 NES games** with reward readers checked against on-screen score and death events.
- **3.2 million reward steps** with exact agreement between the Python and GPU implementations.
- **9,000–10,000 training decisions per second** with a 6.33-million-parameter policy that acts from pixels.
- **8 full games** played by an exported player, checked over **102,636 frames**, with no button mismatches between the compiled player and the source model.

Reward-reader coverage means the training signals have been checked; completion and generalization are evaluated separately for each trained player.

## Plugin validation

The plugin was checked against **Hermes Agent v0.23.1**, including manifest validation and the catalog payload scan.

The CPU unit suite contains **38 passing tests** covering registration, the oracle, isolation, stage tracking, trace comparison, the regression gate, training control and the watcher.

The [Hermes integration harness](../tests/integration/hermes_itest.py) exercises all **28 tools** through real tool dispatch using a generated test cartridge. The recorded integration run passed **63 checks**, including reward validation, Python/C++ reward parity, CPU training, watcher notifications and a reward fix followed by a training restart. This validates plugin integration; the generated cartridge is separate from the game-training experiments above.

## Extending to more games

The active work is to make training and exploration useful across games and genres. Experiments include a shared policy, individual-game training, reward-guided exploration and automated reward repair. In the current pixel-only, from-scratch training line, a platformer reached the fourth world during training; full-game completion and multi-game generalization are still being evaluated.

For planning, **one additional overnight session (about 8–12 hours)** at the measured throughput would provide roughly **260–430 million additional training decisions** on one RTX 5090, before evaluation and checkpoint overhead. This is a compute-budget estimate, not a predicted completion rate.

See [Architecture](ARCHITECTURE.md), [GPU engine](GPU_ENGINE.md) and [Training watcher](TRAINING_WATCHER.md) for the implementation behind these results.
