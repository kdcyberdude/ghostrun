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

## Recreation loop and completion

A regression PASS only means the tested behaviour did not get worse. It never ends recreation by itself.

1. Write `evidence/recreation-status.md` before building: requested levels, a checklist of movement, collisions, enemies, scoring, power-ups, death/reset, transitions and win conditions, and the complete input routes that will exercise them. Mark missing coverage explicitly. If the configured target changes the maze or rules, report that mismatch; do not claim the original level was recreated.
2. Collect full per-frame reference playthroughs from reset to the requested ending, plus independent routes covering reversals, corners, collisions, deaths and recovery. Preserve the original traces. Small local fixtures help diagnose bugs but cannot replace complete routes.
3. Run those same inputs through the actual independent simulation from reset, without reseeding from reference positions, injecting expected events, replaying reference state or using a special test-only simulation. Compare all observable gameplay fields each frame. Missing fields and skipped intervals are coverage gaps, not matches.
4. Pick the earliest meaningful divergence, classify it (measurement, timing, movement, collision, enemy decision, randomness or rendering), probe one hypothesis, implement the smallest rule and add a regression test. Rerun the affected route and the full route suite after every accepted fix. Repeat until no known material mismatch remains. A failed 30-command hypothesis means choose another hypothesis; it does not mean abandon the recreation loop.
5. Check random behaviour through repeated identical-input reference runs. Determine whether reset/input timing reproduces a trajectory before labelling it random. Match observed decision triggers, allowed choices, timing and dependencies; never add arbitrary randomness to hide a deterministic error. If the seed/state cannot be controlled, compare repeated-run outcomes and transition frequencies with sample counts and uncertainty reported. Preserve deterministic replay in the remake with its own seed. Never claim exact trajectory agreement for uncontrolled randomness.
6. Inspect representative rendered sequences for visible errors after numeric checks. Tiny visual offsets and animation phase may be accepted when they do not change interactions. A small position or one-frame timing error that changes collisions, enemy choices or outcomes must be fixed.
7. Update `evidence/recreation-status.md` after each cycle with routes tested, coverage gaps, first remaining divergences, accepted visual differences, randomness evidence and the next experiment. On a context or delegation limit, return this checkpoint and resume the same loop in another builder session. On a user budget limit or external blocker, report incomplete; never convert the limit into a PASS.

Before claiming completion, run fresh held-out complete routes and `ghostrun_isolation_check`. The completion report must link the raw traces, comparison results, coverage checklist, randomness evidence, and rendered checks. All requested gameplay coverage must be exercised, with no unresolved material deterministic mismatch. Report statistical randomness validation separately. Do not claim exhaustive proof of every possible input sequence.

## Rules that came from expensive mistakes
- Numbers first. Pictures only for rendering questions.
- Get the clock right before tuning anything. Most early "physics" errors were input-phase or unit errors.
- Judge small differences by gameplay impact; only visually negligible differences without behavioural effects may be accepted.
- Test on held-out play as well as the probe you tuned on. A rule fitted to one sample usually breaks elsewhere.
- Separate measurement artefacts from real differences before counting them.
- Never edit the reference trace or loosen a tolerance to pass. The gate fails if you do.
- Write generic tools. One-off probes go in a scratch folder.
- Never commit symlinks to large folders. A merge once deleted real assets that way.

Run `ghostrun_isolation_check` before reporting. PASS means no regression against the last baseline; say what is still different.
