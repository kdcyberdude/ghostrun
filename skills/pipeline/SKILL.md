---
name: pipeline
description: Run the whole GhostRun pipeline for one game, from ROM to tested Three.js rebuild. Use when the user wants to teach Hermes a game or rebuild one.
---

# GhostRun pipeline

Stages run in order and each needs evidence to pass: `intake → reward → verify → explore → oracle → assets → build → compare → gate → visual3d`. Call `ghostrun_status` at the start of every session and continue from `next`. Never rely on memory of earlier sessions.

## Before starting
Use the game path and reconstruction target supplied by the user. Initialize with default `recreate` mode. This preserves the observed levels, rules and progression; do not invent a new maze or silently narrow the requested game to its first level. Use `mechanics` only for an explicitly requested remix. Read docs/RECREATION.md for evidence formats and completion checks. Begin terminal recording at launch and preserve it across continuations.

## Stages
1. **intake**: `ghostrun_reference_enter`, then `ghostrun_init`.
2. **reward, verify**: `skill_view("ghostrun:reward-discovery")`. Pin the measured full-game scope/field/case contract by passing verify with its JSON path as evidence, following docs/RECREATION.md; do not claim only the first level is the whole game.
3. **explore**: `skill_view("ghostrun:gpu-env-port")`, then `ghostrun_train_start` and `ghostrun_watch_start`. `skill_view("ghostrun:training-doctor")` handles anything the watcher raises. Training is required for the default recreate request: evaluate saved policies, diagnose failures and resume within the user budget. Search can aid reward validation and reference exploration, but cannot substitute for training or prove that the learned policy cleared the game.
4. **oracle**: verify per-frame player and all enemy positions/modes, scoring, lives, progression and mechanic-specific observables through controlled reference experiments. Missing observations return to the reference agent for measurement. Then `ghostrun_oracle_start` with the trained player or the route.
5. **assets**: on the reference side, prepare matching 2D sprite/tile/animation and audio assets from observed frames/audio or independently reconstruct them. Measure level geometry through play and images, never extract ROM maps/tables/code. Put all assets in a staging kit with provenance and SHA-256 entries as described in docs/RECREATION.md. Use `ghostrun_assets_import` to copy it into the builder’s `assets/`, then pass the assets stage. The builder must start with this kit in place.
6. **build, compare, gate**: start a fresh builder context using `delegate_task` or an independently launched builder session. Set its working directory to the workspace returned by `ghostrun_builder_enter`. Changing directories in the reference conversation is not context isolation. Its first call must be `ghostrun_builder_enter`, and it follows `skill_view("ghostrun:rebuild-from-oracle")`. Give it only the slug, the requested reconstruction target and the completion requirements from `rebuild-from-oracle`. On return, inspect its recreation-status report and evidence. If meaningful differences or missing full-route coverage remain, resume the builder with the next experiment; repeat autonomously within the user’s budget. Run `ghostrun_recreation_check` on complete-route evidence. For recreate mode, pass the `gate` stage with that manifest path as evidence; the tool rejects incomplete measurements. A regression PASS alone cannot complete these stages.
7. If the requested target includes 2.5D or 3D, run `skill_view("ghostrun:visual-upgrade")` only after the recreation completion requirements are met and the gate passes, then create its assets. The default recreate workflow includes both targets and videos. Pass `visual3d` with the delivery manifest from docs/RECREATION.md after independently launching and inspecting both builds.

## Working rules
- Make routine decisions yourself. Ask about cloud spending or anything that cannot be undone.
- Use GhostRun's tools for long or GPU work. For unattended command execution, follow the user-configured Hermes profile in docs/UNATTENDED.md. Do not route a denied command through a tool to evade a guard.
- Use at most two subagents at once, each with independent files.
- Time-box a hypothesis to about 30 commands. A probe with no signal is a recorded negative result.
- Report plainly what is done, what is left and why. A passed gate means no regression, not that the rebuild is finished.

For independent divergences, use at most two builders with separate worktrees and explicit file ownership. Each returns its first divergence, native evidence, minimal rule, regression test and branch. Integrate one change at a time and rerun the entire recorded route suite after each merge; reject regressions. Never parallelize two fixes to the same timing dependency.

While GPU training runs, prepare matching assets and collect reference measurements in parallel where independent, without passing stages out of order. For an explicit 2D-only target, finish verified 2D delivery and mark visual3d skipped with the 2D delivery manifest; do no 3D work.
