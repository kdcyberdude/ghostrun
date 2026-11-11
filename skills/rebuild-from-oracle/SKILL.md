---
name: rebuild-from-oracle
description: Build an independent Three.js game by observing a black-box oracle, measured against numeric traces. Use only in a builder session.
---

# Rebuild from the oracle

You are the builder. Your first call must be `ghostrun_builder_enter`. You see only your workspace and `ghostrun_oracle_call`: actions in, frames and declared numbers out. Never look for the ROM, the reference folder or an emulator, and never put an emulator or a replay behind the canvas. The game must be a real, independent simulation.

Read the project configuration with `ghostrun_status` and follow the requested reconstruction target. Prepared assets arrive in `assets/`; retain any accompanying notices.

## Spine first, before gameplay
1. Reference wrapper: a small script over `ghostrun_oracle_call` that runs a probe and writes a per-frame JSONL trace.
2. Simulation separate from rendering, with a headless step function and the same trace format.
3. Replay-compare with `ghostrun_compare`, tolerances declared before you look at results.
4. Regression gate with `ghostrun_gate`.

## Loop
Pick the difference a player would notice most. Find its **first divergent frame**. Form one hypothesis, time-box it to about 30 commands, change one thing, add a test that fails without the fix, then run the gate.

## Rules that came from expensive mistakes
- Numbers first. Pictures only for rendering questions.
- Get the clock right before tuning anything. Most early "physics" errors were input-phase or unit errors.
- Skip differences under about 3 px, single-frame differences and animation phase.
- Test on held-out play as well as the probe you tuned on. A rule fitted to one sample usually breaks elsewhere.
- Separate measurement artefacts from real differences before counting them.
- Never edit the reference trace or loosen a tolerance to pass. The gate fails if you do.
- Write generic tools. One-off probes go in a scratch folder.
- Never commit symlinks to large folders. A merge once deleted real assets that way.

Run `ghostrun_isolation_check` before reporting. PASS means no regression against the last baseline; say what is still different.
