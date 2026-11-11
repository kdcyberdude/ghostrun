---
name: gpu-env-port
description: Add a game to the CUDA NES training environment, with a reward port proved equal to Python. Use before GPU training a new game.
---

# GPU environment port

The trainer runs thousands of NES consoles on the GPU with the reward computed there, so nothing is copied to the host per step. The Python reader stays the source of truth.

1. `ghostrun_engine_setup` with `boot_frames`. This makes a per-game engine copy and fetches the emulator at its pinned commit.
2. Check the game's mapper is supported. If not, the stage is blocked until the mapper is added to the emulator; say so rather than working around it.
3. In the engine copy, add `observe_<slug>` to `rl/csrc/reward10.cuh` and a `case` in its `switch`. Port line by line in double arithmetic, in Python's evaluation order. Constants come from `gen_reward_consts.py`; never retype them.
4. Record RAM traces for the game and run `ghostrun_engine_parity`. Rewards must be equal as doubles, with identical done flags, events and end reasons. There is no tolerance.
5. Short GPU smoke run. Confirm decisions per second and that the first episodes end for sensible reasons.

Keep RAM out of actor inputs: the policy sees pixels and its own past controls only.

The GPU has one owner at a time. `ghostrun_train_start` refuses a busy GPU; do not use `share_gpu` to get past another job unless the user says so.
