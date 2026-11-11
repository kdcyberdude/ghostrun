# Reliability: what guarantees what

GhostRun makes claims at every stage: the reward is right, training resumed correctly, the builder never saw the game, the rebuild didn't get worse. This page lists what backs each claim, how it was measured, and where the guarantee stops.

## At a glance

| Claim | Backed by | Strength |
|---|---|---|
| GPU reward equals Python reward | Exact double parity, about 3.2M updates, 12 games | Exact, on the replayed traces |
| GPU environment equals its CPU build | `engine/rl/tests/gpu_check.py`, all 12 games | Bit for bit |
| Resume continues the same run | `engine/rl/tests/resume_cpu.sh` and the GPU check | Bit for bit |
| Exported player equals the trained model | `engine/rl/player/check_parity.py` | 0 mismatches over 102,636 frames |
| Builder never reached the game | Separate folders, oracle, hook, isolation scan | Strong against accidents, not a security boundary |
| Rebuild didn't regress | Trace compare and the regression gate | Exact against a pinned reference and tolerances |
| Rebuild is faithful | Per-frame trace metrics | Measured, not complete. See below |

## Reward parity

Python is the source of truth. The CUDA reader must equal it **as doubles**, with identical done flags, events, levels, deaths and end reasons.

- Checked on **about 3.2M reward updates** in all 12 games, replaying every saved RAM trace at strides 1, 4 and 8, plus 6,000-decision random-play traces.
- Constants are generated as exact hex floats. `-fmad=false` and `-ffp-contract=off` keep the compiler from changing results.
- That check ran on the host compile of the shared header. The GPU build is checked against the CPU build separately, bit for bit, by `gpu_check.py`.
- In the plugin, `ghostrun_engine_parity` runs the same comparison for any new or edited reader, and a reward fix can't be applied without it.

See [Rewards](REWARDS.md#python-is-the-truth-cuda-must-match-exactly).

## Exact resume

`resume_cpu.sh` trains 5 iterations straight, then 3, stops, resumes and runs to 5. It asserts that the iteration, model, optimizer, environments, observations, GRU state and return statistics are bit-identical. The GPU check repeats this on the GPU.

A live run was also resumed at 104.07M decisions with a first-update KL of 4e-6.

Why it matters: training runs for hours, gets stopped for reward fixes, and survives reboots. A resume that drifts would make every before-and-after comparison meaningless.

## Exported player parity

The player is exported for use outside PyTorch. `check_parity.py` plays the compiled player and the source model side by side in the CPU emulator, including turbo and controller dropout.

Measured: 8 full games, 25,659 decisions, 102,636 frames, **0 button mismatches**.

The environment was also checked against FCEUX, a different emulator, so a trained player can be watched there. All pad bytes for 324 moves reach FCEUX unchanged. Pixel colour numbers matched 100% in 8 games and at least 98.7% in all 12.

## Isolation

The builder must rebuild the game, not wrap it. Four layers:

| Layer | File | What it does |
|---|---|---|
| Folders | `core/isolation.py` | Reference and builder folders must not overlap |
| Oracle | `core/oracle.py` | Unix socket, one JSON request per line, at most 512 KiB. Allowed ops: `hello`, `reset`, `step`, `observe`, `checkpoint`, `restore`, `play`. Rejects unknown ops, unknown fields, unknown buttons and frame counts outside 1 to 240. Never returns the ROM, its path, RAM or savestates |
| Hook | `__init__.py`, `pre_tool_call` | Denies by default. A session reaches reference tools only after declaring itself a reference session. Builder sessions can't switch back. Any argument containing the reference path or `.nes` is blocked |
| Scan | `ghostrun_isolation_check` | Flags ROM, savestate and movie files, symlinks that leave the workspace, and source files that mention the reference path or a known emulator (FCEUX, Nestopia, Mesen, jsnes, RetroArch and others) |

**Limit:** the hook matches paths in tool arguments. A determined shell command could get around it. For a hard boundary, run the builder under Hermes's Docker terminal backend with only its workspace mounted, or as a separate OS user.

## Trace compare

`ghostrun_compare` reads two per-frame JSONL traces, keyed by frame.

- Tolerances are per field: `near` and `far`. A difference above `near` is an event, above `far` a large event.
- Only frames present in both are compared. Missing and extra frames are counted separately.
- It reports per-field counts and the **first divergence**, which is where a fix should start.
- There are no built-in tolerances. The rebuild project used 3 px and 8 px, and treated differences under about 3 px, one frame or animation phase as not noticeable to a player.

## The regression gate

`ghostrun_gate` compares a new trace comparison with a saved baseline.

| Result | When |
|---|---|
| FAIL | No baseline. The reference trace's SHA-256 differs from the baseline's. The tolerances differ. No frames compared |
| REGRESSION | Events, large events or missing frames went up |
| PASS | None of the above |

**Anti-tamper.** The cheap ways to pass a gate are to edit the reference trace or loosen the tolerances. Both change a hash recorded in the baseline, so both FAIL. The baseline lives under the reference folder (`<reference>/<game>/evidence/gate-baseline.json`), which builder sessions can't reach. Saving a new baseline is a separate, explicit step.

**What it doesn't cover:** the rebuild's own trace isn't hashed, because it's meant to change. And a PASS means no regression against the last baseline. It doesn't mean the game is right.

## Rebuild fidelity

Measured on the earlier research rebuild of the 32-level platformer, against a 79,824-frame native trace of a winning route through all 32 levels.

| Measure | Start | Later |
|---|---|---|
| Position events over 3 px | 5,477 | 1,283 |
| Position events over 8 px | 2,103 | 237 |
| Walking enemies within 2 px | 65.8% | 94.6% |
| Unit tests | 648 of 651 | 1,107 of 1,107 |

[Results](RESULTS.md) quotes an intermediate point, 1,471 and 270. The later gate run reached 1,283 and 237.

**Held-out play** is the honest number. The rebuild was also compared on 256 runs of the new policy that it wasn't tuned on:

| Sweep | Rows | Reported events | Of which measurement artefacts | Real events per 1,000 rows |
|---|---|---|---|---|
| r6 | 595,628 | 38,822 | 29,188 | 16.2 |
| r7 | 636,256 | 34,556 | 24,765 | 15.4 |

The start-of-day rate was 34.9 per 1,000 rows. The r6 number was not lower than the sweep before it, so part of the route gain was tuning to the route. A later sweep across all 32 levels and 8 moods showed no overall position gain.

**2.5D renderer.** A replay-equivalence check compares the headless simulation, the original 2D renderer and the 2.5D renderer over 2,600 frames, including audio events. It passes. Measured at 60.1 fps, p99 16.8 ms, at resolutions up to 4K on a shared RTX 5090. No human play-test at 4K yet.

## Tests

| Suite | Count | Needs |
|---|---|---|
| Plugin unit tests, `tests/` | 38 passing cases | CPU only |
| Hermes integration, `tests/integration/hermes_itest.py` | 28 tools, 63 checks in the recorded run | Hermes install |
| Reward and environment tests, `engine/rl/tests/` | 23 test functions plus parity and resume scripts | CPU; `gpu_check.py` needs a GPU |
| Reward contract | `python contract.py --check` | CPU |

## Known failure modes

Seen in real runs, with what now catches them:

| Failure | Caught by |
|---|---|
| A signed RAM byte read unsigned pays 20 levels in one step | Reward lint, `progress_overpaid` and `value_fit_collapse` in the watcher |
| A death penalty makes standing still the best play | Balance test, `stall_dominates` |
| Clear rates counted at game end, 80 minutes stale | Counting at the moment of the clear |
| Greedy play stalls while sampled play wins | The `training-doctor` skill compares greedy and sampled play |
| A watcher reports live jobs dead | Independent liveness check |
| Most reported rebuild differences are measurement artefacts | Separate artefacts before fixing. In one sweep, 29,188 of 38,822 |
| Trainer clock and fixed-cycle clock look identical until a replay fails | Seed the rebuild clock from the reference. One fix took a parity check from 0 of 27 to 27 of 27 |
| A `git merge` of a branch that tracked worktree symlinks deleted asset folders | The rebuild project's merge script now refuses such branches |

## Not validated

- **Hard isolation.** The hook is a guard rail. Only a container or a separate OS user is a boundary.
- **Broad game coverage.** Reward readers exist for 12 games. End-to-end rebuild was shown on one.
- **Win detection.** No game has a `verified` win detector. Four are provisional, one unverified.
- **GPU parity for every game edit.** Parity covers the traces it replays, not all game states.
- **The new model completing a game.** It has cleared levels during training, not the 32-level game from power-on.
- **A trained policy playing a rebuild.** Not measured.
- **Full fidelity.** Visible differences remain in the rebuild, so no full-fidelity claim is made.
- **Watcher thresholds on other games.** Tuned on one game and three runs.
- **The 4K renderer with a human player.** Not measured.
