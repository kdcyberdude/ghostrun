---
name: reward-discovery
description: Work out a NES game's RAM and write a verified reward reader. Use for the reward and verify stages, or when adding a game.
---

# Reward discovery

Goal: a module at `games/<slug>.py` that turns RAM into `Signals`. The shared reward in `reward.py` never changes per game. Read the files listed in `read_first` from `ghostrun_init` before writing anything.

## Loop
1. Look for existing address notes, such as a stable-retro `data.json` with a matching ROM hash or prior black-box measurement notes. Treat them as unverified candidates.
2. Script `boot()`: poll RAM until the first controllable frame. Confirm with a screenshot.
3. Record RAM on every frame during random play, then diff around events: which byte changes on the frame of a death, a pickup or a level change?
4. Confirm each meaning with `poke` and the screen, for example set a counter to 37 and read 37 on the HUD.
5. Write the module with an address docstring and known reward-hacking risks.

## Treat every byte as suspect
- **Signed or wrapping values.** A page counter read unsigned once paid about 20 levels in one step and was found two days later in training. Check what happens below 0 and at 255.
- **Stale progress** during transitions: set `progress_valid` False.
- **Win flags that fire early.** One fired at every castle, not only the last.
- **Scroll that stops** at bosses: add a damage or phase term, or progress freezes.
- **Counters that saturate.**
- **Pause**: Start can dodge a death penalty, so Start and Select are blocked after boot by default.

## Acceptance, all required
1. `ghostrun_reward_check` passes.
2. `ghostrun_reward_audit`: detected deaths equal lives lost in all 12 episodes. Open the contact sheets and check them.
3. Decoded score matches the HUD.
4. `ghostrun_reward_lint` is clean.
5. `ghostrun_reward_balance` reports no problem. Standing still must not out-earn moving.
6. `ghostrun_reward_search` reaches the end of the first level and the level event fires on screen.

Record each signal as verified, provisional or unverified, and be honest in `INFO['win_status']`. Search reach is proof the reward points forward. It is not evidence of what a policy will learn.

Before passing verify for recreation, implement and screen-check `observables()` for player position, every enemy position/mode, score, lives, level, ending and relevant timers/counters. Record unknowns and continue controlled probes; a reward reader alone is insufficient for frame-by-frame recreation. Preserve full requested-game scope; do not redefine first-level completion as a whole-game win.
