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
5. Use `ghostrun_train_start` with the user's remaining `--time-limit`. For a new game the default recommendation is the tested Mario recipe from `core/training-baseline.json`: core 512, 8 moods, 6.33M parameters, 8,192 consoles, 64-step sequences, and the saved learning/performance settings. Reward discovery is separate. Weak learning alone is not a reason to silently shrink the model or leave smoke settings in production.
6. Explicit user preferences take precedence. Other configurations are allowed: pass the requested arguments and a `recipe_note` explaining the request or experiment. Tell the user what differs from the tested recipe and why; no approval step is added. Resource adjustments should follow measured hardware capacity where possible. Supply optional `adjustment_evidence` naming an owned run to retain its memory/failure measurements. Every difference and reason is recorded.
7. The first start uses a three-iteration preflight with a 180-second trainer limit. Wait for `ghostrun_train_check` to report real throughput and a clean exit. Then call `ghostrun_train_start` with the original requested args and remaining time budget. It resumes the same model, optimizer and environment for production. A different model's benchmark is not qualifying evidence. Changed settings, model source or GPU need their own measurement window. Investigate unexpectedly low speed before continuing; throughput alone does not prove learning. Incompatible legacy checkpoints stay preserved while a separate run starts.

For a deliberately tiny CPU/GPU diagnostic, pass `smoke=true`. The tool labels and bounds it; its checkpoint and speed cannot qualify production. Use an explicit custom recipe for a requested alternative learning setup. After a reward fix, the selected recipe is retained and a fresh bounded preflight is required.

Keep RAM out of actor inputs: the policy sees pixels and its own past controls only.

The GPU has one owner at a time. `ghostrun_train_start` refuses a busy GPU; do not use `share_gpu` to get past another job unless the user says so.
