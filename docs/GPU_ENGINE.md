# GPU environment

Most RL on retro games runs emulators on the CPU and copies frames to the GPU. GhostRun runs the consoles **on the GPU**, computes the reward there too, and feeds the policy without a per-step trip to the host.

## Distribution and setup

GhostRun includes the GPU rollout environment, reward implementation, policy and trainer under `engine/`. The emulator is based on NeSLE, with the mapper and renderer extensions supplied in `engine/third_party/nesle-extensions.patch`.

`ghostrun_engine_setup` fetches upstream revision `0b04d8b9b6a93eea6758b06519206d8f13f6db78`, applies the patch and builds the host library. The rollout environment is compiled locally when used. This makes the current environment reproducible without a separate emulator fork. For convenience, the patched tree is also published at [kdcyberdude/NeSLE](https://github.com/kdcyberdude/NeSLE), branch `ghostrun`.

The ROM is selected when a game workspace is initialized. Emulator setup and game inputs are separate steps.

## What's in it

| Part | File | Notes |
|---|---|---|
| NES on CUDA | [NeSLE](https://github.com/hbofz/NeSLE), pinned, plus `engine/third_party/nesle-extensions.patch` | The patch adds CNROM, MMC1, MMC2, MMC3, a per-scanline renderer and DMC timing (there's no sound output). Upstream supports mappers 0, 2, 34 and 94 |
| Environment | `engine/rl/csrc/`, `engine/rl/rlenv.py` | Thousands of consoles in parallel |
| Reward on GPU | `engine/rl/csrc/reward10.cuh` | Line-by-line port of the Python reward |
| Generated constants | `engine/rl/scripts/gen_reward_consts.py` | Written from Python as exact hex floats, so the port can't drift |
| Policy | `engine/rl/model.py` | 6.33M parameters, pixels and past controls only |
| Trainer | `engine/rl/train.py` | Recurrent PPO, exact resume, background test plays |
| Exploration | `engine/rl/novelty.py`, `diversity.py`, `level_plan.py` | Curiosity, varied play styles, failure-weighted level starts |
| Export | `engine/rl/player/` | ONNX export and packaging, checked for parity |

## Policy

Four 240×224 frames go through a learned stem and an Impoola CNN with global average pooling, then two SimBa blocks and a GRU of 512. Ordered masked heads pick the d-pad, A, B, Start and Select. The value head is HL-Gauss over per-game normalised returns.

No RAM, game id or reward reaches the actor.

## Measured speed

One RTX 5090 (32 GB): about 9,000 to 10,000 decisions per second, 20 to 30% MFU. The card's power cap was the limit.

## Correctness

- Python is the source of truth. The CUDA reward must equal it **as doubles**, with identical done flags, events and end reasons. This was checked on 3.2M reward steps across the original 12 games.
- Resume is exact: environments, RNG, optimizer and counters.
- `-fmad=false` and `-ffp-contract=off` stop the compiler changing floating-point results.

## Adding a game

1. `ghostrun_engine_setup` copies the engine for this game and fetches NeSLE at its pinned commit.
2. Port the reader into `reward10.cuh`, following the `gpu-env-port` skill.
3. `ghostrun_engine_parity` records RAM from the game and compares Python against C++.

Step 2 is agent work. A new game isn't automatic until its reader is ported and parity passes.

## Requirements

Linux, an NVIDIA GPU, `nvcc`, a C++20 compiler, PyTorch. One training job owns the GPU at a time.
