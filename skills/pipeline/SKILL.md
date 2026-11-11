---
name: pipeline
description: Run the whole GhostRun pipeline for one game, from ROM to tested Three.js rebuild. Use when the user wants to teach Hermes a game or rebuild one.
---

# GhostRun pipeline

Stages run in order and each needs evidence to pass: `intake → reward → verify → explore → oracle → build → compare → gate`. Call `ghostrun_status` at the start of every session and continue from `next`. Never rely on memory of earlier sessions.

## Before starting
Only use a game the user has the right to use. Ask which is true if it is unclear:
- **mechanics mode** (default): the rebuild has new characters, art, music, level layouts and a new name. The original only informs how things move and feel.
- **faithful mode**: reuses the game's own material. Needs a stated basis: the user owns it, or it has an open licence. Check the licence text yourself, including any clause about AI use.

Do not extract art, music or level data from a ROM. Do not use this pipeline to reproduce a commercial game's characters, art, music or levels.

## Stages
1. **intake**: `ghostrun_reference_enter`, then `ghostrun_init`.
2. **reward, verify**: `skill_view("ghostrun:reward-discovery")`.
3. **explore**: `skill_view("ghostrun:gpu-env-port")`, then `ghostrun_train_start` and `ghostrun_watch_start`. `skill_view("ghostrun:training-doctor")` handles anything the watcher raises. A search route from `ghostrun_reward_search` is acceptable when training is not wanted.
4. **oracle**: `ghostrun_oracle_start` with the trained player or the route.
5. **build, compare, gate**: delegate to a subagent with `delegate_task`. Its first call must be `ghostrun_builder_enter`, and it follows `skill_view("ghostrun:rebuild-from-oracle")`. Give it only the slug and the mode.
6. Optional: `skill_view("ghostrun:visual-upgrade")` for 2.5D or 3D.

## Working rules
- Make routine decisions yourself. Ask only about rights, cloud spending, or anything that cannot be undone.
- Use at most two subagents at once, each with independent files.
- Time-box a hypothesis to about 30 commands. A probe with no signal is a recorded negative result.
- Report plainly what is done, what is left and why. A passed gate means no regression, not that the rebuild is finished.
