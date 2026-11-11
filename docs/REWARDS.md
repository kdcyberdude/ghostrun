# Rewards: discovered from RAM, proven against the screen

A player needs a reward, and a wrong reward wastes days of GPU. GhostRun has the agent work out the reward from the game's memory, then prove every signal against what's on screen before any training starts.

## One reward, many games

The reward is called **reward10**. It's the same for every game. A game module only translates 2 KB of RAM into a fixed set of signals.

| Signal | Meaning |
|---|---|
| `in_play` | Real gameplay, not title, menu, demo or pause |
| `level`, `progress` | Which level, and how far through it |
| `dying`, `lives` | Death edge or lives counter |
| `health` | 0 to 1, if the game has a bar |
| `score` | If the game has one |
| `game_over`, `won` | Episode ends |

A new game is about 100 lines: a `boot()` to the first controllable frame, a `Reader`, two scale constants and an `INFO` description. The platformer's module, the reference for the others, is 83 lines.

## The contract

Shared values from `engine/scripts/reward10/reward.py`:

| Term | Value | Rule |
|---|---|---|
| Progress | +1.0 per level of progress | New high-water progress in the current level only. `PROGRESS_UNIT` = one level |
| Next level | +1.0 | Only the next level in order. A skip, such as a warp, ends the episode with no bonus |
| Death | −0.1 | Was −1.0. That made crouching the best strategy |
| Damage | −0.25 per full health bar | |
| Score | +0.02 per `SCORE_UNIT` | Capped at 0.1 per step and 0.2 per level |
| Win | +5.0 | Episode ends |
| Stall | −0.1 | The episode ends after 120 s of game time with no progress, new level or death |
| Waiting | −1.8 spread over the stall limit | About −0.001 per decision in the platformer |

There's no reward outside real gameplay. Start and Select are blocked after boot unless a game lists what they do, because pausing just before a death dodged the penalty in four of the games.

`python contract.py` checks every module and regenerates `reward_spec.json`, the exact reward of every game as JSON. A test fails if the spec is stale.

### The score budget

Score is a tiebreaker. Respawning enemies, end-of-level tallies and punches could otherwise outweigh progress. The per-level budget resets on a new level, not on death, so dying can't refill it.

Measured on the best saved runs before and after the budget:

| Game | Score share of return, before | After |
|---|---|---|
| Boxing (Punch-Out!!) | 46.6% | 13.5% |
| 32-level platformer | 33.2% | 8.3% |
| Contra | 18.7% | 9.8% |
| Gradius | 7.1% | 6.9% |

## How a reader is discovered

The `reward-discovery` skill drives this loop:

1. Look for existing address notes with a matching ROM hash. Treat them as candidates only.
2. Script `boot()` and confirm the first controllable frame with a screenshot.
3. Record RAM every frame during random play. Diff around events: which byte changes on the frame of a death, a pickup, a level change?
4. Confirm each meaning with `poke` and the screen. Set a counter to 37, read 37 on the HUD.
5. Write the module with an address docstring and its known reward-hacking risks.

Every byte is suspect. The bugs that got through were a signed page counter read unsigned, stale progress during transitions, a win flag that fired at every castle, scroll that stops at bosses, a counter that saturates, and pause.

## How it's proven

All of these must pass before training. Each tool is a plugin tool, so the agent runs it and the ledger records the result.

| Check | Tool | Passes when |
|---|---|---|
| Contract | `ghostrun_reward_check` | Module has every field, types are right |
| Random audit | `ghostrun_reward_audit` | 12 random episodes to game over. Detected deaths equal lives lost in every episode. Contact sheets show BEFORE, AT and +12 frames for every event |
| Score | by eye, on the contact sheets | Decoded score equals the HUD digits |
| Lint | `ghostrun_reward_lint` | No step pays more than half a level, no level jumps over one, no falling score, no lives jump |
| Balance | `ghostrun_reward_balance` | Holding each action from a fresh start: nothing that barely moves out-earns the action that moves furthest |
| Search | `ghostrun_reward_search` | Go-Explore guided only by the reward reaches the end of the first level, and the level event fires at the right moment on screen |

Search reach proves the reward points forward. It doesn't predict what a policy will learn.

## Tools

| Tool | File | Catches |
|---|---|---|
| Audit | `engine/scripts/reward10/audit.py` | Missed deaths, such as pit deaths a first version missed, and false ones, such as overheats counted as crashes |
| Lint | `core/reward_lint.py` | Signed or wrapping bytes. The unsigned page counter paid about 20 levels in one step |
| Balance | `core/balance.py` | Rewards that teach standing still. Found the crouching bug in minutes, after 21M decisions had been wasted |
| Search | `engine/scripts/reward10/search.py` | Rewards that don't lead forward |

## Python is the truth, CUDA must match exactly

Training computes the reward on the GPU, inside the environment. The CUDA reader in `engine/rl/csrc/reward10.cuh` is a line-by-line port of the Python one.

- Constants are generated from Python by `gen_reward_consts.py` as exact hex floats, so they can't drift.
- Both compute in doubles. `-fmad=false` and `-ffp-contract=off` stop the compiler fusing operations.
- Parity means **equal as doubles**, not close: same rewards, done flags, events, levels, deaths and end reasons.
- Checked on about **3.2M reward updates** across the 12 games, replaying saved RAM traces at strides of 1, 4 and 8.
- `ghostrun_engine_parity` repeats this for a new game: it records RAM with `core/record_ram.py` and compares Python against C++.

## The 12 games

Status of the win detector follows the contract: **verified** = seen in a genuine run, **provisional** = seen only with help (a RAM poke or another emulator), **unverified** = written but never observed, **none** = no detector.

| Game | Genre | Levels | Progress signal | Death | Audit (12 episodes) | Score vs HUD | Search reached | Win |
|---|---|---|---|---|---|---|---|---|
| 32-level platformer | platformer | 32 | pixels moved right | life lost | 36 deaths = 36 lives | match | 4-3 via a warp, 0 deaths | provisional |
| Castlevania | platformer | 19 | new 32 px cells, plus boss damage | health 0, pit, water, time | 4 = 4 in every episode | match | level 3 (0-based), 0 deaths | none |
| Contra | run-and-gun | 8 | scroll, rooms, wall-core damage | life lost | 3 = 3 in every episode | match | stage 2 | none |
| Excitebike | racing | 6 | track distance | crash | 117 crashes, 12 game overs | no score; race time matches | qualified 14 of 14 seeds | provisional |
| Final Mission | shooter | 5 | auto-scroll, plus boss damage | life reaches 0 | 1 death then game over, every episode | no in-game HUD | stage 3, 0 deaths | none |
| Gradius | shooter | 7 | auto-scroll counter | ship hit | 48 lives, all match | match (poke test) | stage 5 boss, 0 deaths | none |
| Kage | action platformer | 15 | camera along the stage route | health 0 | death and game over every episode | no score | stage 2 | provisional |
| Pac-Man | maze | endless | dots and energizers eaten | caught | 36 deaths, all match | match | maze 2; a longer search cleared 23 mazes | none |
| Punch-Out!! | boxing | 14 | damage dealt | knocked down | KO loss in 12 of 12 | match | first fight won in 13 of 13 seeds | unverified |
| Tecmo Bowl | football | 11 | own points and drive yards | opponent scores | 167 opponent scores, 12 game overs | match | touchdown in 9 of 14 seeds | provisional |
| Tetris | puzzle | endless | lines cleared | top-out | 12 top-outs, all match | match | 1 line; a placement bot reached level 2 | none |
| Zelda | action-adventure | 9 | new rooms, cells, items, hearts | Link dies | death on the exact step hearts hit 0, 12 of 12 | match (poke test) | 34 rooms, 287 cells | none |

Each module's docstring lists every address and its known risks. Some limits a trainer should know:

- Contra and Gradius bosses after the first have no damage term, so reward is flat during them.
- Excitebike pays distance, not speed. A search finished race 5 in 1:49.95; 1:14.00 was needed.
- Pac-Man's round counter stops at 22, so from maze 24 on nothing is paid.
- Punch-Out!! chip damage keeps paying, so a long decision loss can out-earn a quick KO.
- Tecmo Bowl defense earns nothing, so its stall limit is 300 s.
- Zelda is non-linear. The search never found the sword by itself.

Source: `engine/scripts/reward10/reward_spec.json` and the per-game evidence summaries in the research repository.

## When a reward is wrong during training

Some bugs only show when the policy first reaches a part of the game nobody tested. The [training watcher](TRAINING_WATCHER.md) detects their signatures. The agent then opens a fix, edits both the Python and CUDA readers, and must pass contract, audit, lint, balance and parity again. The validation is tied to the file's hash.

**At most 3 automatic fixes per game** (`MAX_FIXES` in `core/train_ctl.py`). After that the watcher reports to a person instead of patching again.
