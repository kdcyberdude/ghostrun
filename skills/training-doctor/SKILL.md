---
name: training-doctor
description: Diagnose a training problem raised by the GhostRun watcher and fix the reward autonomously, within a budget. Use when the watcher wakes the agent or training looks wrong.
---

# Training doctor

The watcher raised a finding. Find the real cause before changing anything. Most findings are not reward bugs.

## Diagnose
1. `ghostrun_train_check` for current findings and how many fixes remain.
2. Look at behaviour, not curves. Open the videos and summaries of recent test plays in the run's `eval/` and `videos/`.
3. Compare two frozen models, from before and after the change. Compare greedy with sampled play.
4. Read the actual button streams. A policy frozen by one held button looks like an entropy problem and is not.
5. For a suspected reward bug, replay the episode and find the exact step that paid too much.

| Finding | Check first |
|---|---|
| `value_fit_collapse`, `progress_overpaid` | one step paying far more than a level: a signed or wrapping byte |
| `stall_dominates` | run `ghostrun_reward_balance`: is waiting the best-paying play? |
| `level_regression`, `test_play_regression` | what changed at the onset: a new level reached, a curriculum change |
| `emulator_fault` | mapper support; not a reward issue |
| `trainer_stopped`, `trainer_silent` | end of `stdout.log`. Confirm liveness separately before believing it |
| `no_test_play_gain` | often needs more time. Only act with evidence |

## Fix, only for a proven reward bug
1. `ghostrun_fix_begin` with the finding and hypothesis.
2. Edit the reader **and** its CUDA port. Keep it generic: never hard-code a level, route or position.
3. `ghostrun_fix_validate`. Every check must pass. Open the contact sheets.
4. `ghostrun_fix_apply`. Training restarts in a new run from the best measured weights, with fresh optimizer and return statistics.
5. After three test plays, `ghostrun_fix_review`. If `worse`, restore the previous reward from `reward_versions/` and report it.

## Stop and report instead when
- the fix budget is used up;
- the cause is not the reward (trainer, model, environment): report it with evidence;
- a change would alter what the game asks of the player.

Reward and throughput going up never prove the player got better. Only test plays do.
