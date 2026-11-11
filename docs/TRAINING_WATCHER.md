# Training watcher and self-repair

Reward functions miss cases, however carefully they're written. Some bugs only appear when the policy first reaches a part of the game nobody tested. GhostRun watches for that while training runs, and can debug and repair the reward without stopping the whole project.

## How it runs

`ghostrun_watch_start` starts a background thread. Every few minutes it reads the trainer's own files and does plain arithmetic, so a healthy run **costs no model tokens**. It wakes the agent only when the verdict is `act` and the findings are new.

In the Hermes CLI this works as is. To be woken through the messaging gateway, set `plugins.entries.ghostrun.allow_gateway_injection: true`.

## What it detects

Each detector comes from a failure in real training runs.

| Finding | Signal | The real failure behind it |
|---|---|---|
| `value_fit_collapse` | explained variance drops at least 0.15 from a high of 0.9+ | one step paid about 20 levels and wrecked the value function |
| `progress_overpaid` | a test play's progress pay exceeds its level by more than 2 | same bug, seen in a test play |
| `stall_dominates` | over half of episodes end by stalling | idling was the safest play |
| `level_regression` | mean level falls below 75% of its best | late collapse in training |
| `test_play_regression` | median test-play level falls by 2 or more | ability swinging between checkpoints |
| `emulator_fault` | any episode faulted | unsupported or broken environment |
| `non_finite` | NaN or Inf in losses | numeric failure |
| `trainer_stopped`, `trainer_silent` | process gone, or no metrics for 30 minutes | jobs that died, and a watcher that wrongly reported live jobs dead |
| `entropy_collapse` | entropy below 10% of its start | policy stuck on one input |
| `no_test_play_gain` | later test plays no better than earlier ones | hours of high throughput with no learning |
| `throughput_drop` | speed below 60% of its best | another process sharing the machine |

## Tested on real history

These detectors were replayed against the metrics of real training runs, cut off at earlier points as if they were live.

| Run, cut off at | Result | What really happened |
|---|---|---|
| Iterations 1800, 1900 | quiet | training was healthy |
| Iteration 2000 | `value_fit_collapse` | bug first appeared around iteration 1860 |
| Iteration 2612 | also `level_regression`, `test_play_regression` | when the bug was actually found, by hand |
| Earlier, iteration 1500 | `test_play_regression` | a real swing: all test plays stuck on the first level |
| 12-game run | `stall_dominates` in 4 games | that run never learned |
| Short early run | quiet | no problem at that point |

So on this run the watcher would have raised the alarm about 600 iterations before a person found the bug.

**How far to trust this:** the thresholds were chosen with this history in view, on one game and three runs. They're a starting point, and other games may need different ones.

## The repair loop

1. **Diagnose.** The `training-doctor` skill looks at behaviour first: test-play videos, frozen models from before and after, greedy against sampled play, and actual button streams. Most findings aren't reward bugs.
2. **Open a fix** with the finding and a hypothesis.
3. **Edit** the Python reader and its CUDA port.
4. **Validate.** Contract, 12-episode audit, lint, balance test, and Python-versus-CUDA parity must all pass. The result is tied to the file's hash, so editing afterwards voids it.
5. **Apply.** Training stops at a checkpoint. A new run starts from the **best measured** weights, with a fresh optimizer and return statistics, because those were learned under the wrong reward.
6. **Review.** After three test plays, the fix is judged by test plays alone. If it's worse, the previous reward is restored and the problem is reported.

## Guardrails

- At most 3 automatic fixes per game. After that it goes to a person.
- Only runs the plugin started can be stopped or restarted. Anything else on the machine is left alone.
- A busy GPU is refused.
- Each reward version has its own run folder, so curves from different rewards never mix.
- Reward and throughput going up never count as success. Only test plays do.
